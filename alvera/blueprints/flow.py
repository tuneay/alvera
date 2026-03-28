"""
Alvera Flow — Keşif & Öneri Katmanı
PRISM Algoritması: Personalized Relevance & Interest Score Model

Faz 1: QualityScore + FreshnessScore + SocialProofScore + basit RelevanceScore
AI kullanımı: Groq LLAMA 3.1-8b sadece /flow/why/<post_id> için (düşük frekanslı)
"""
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, render_template, request, session
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_, desc

from extensions import db
from models import (
    Follow, OnboardingData, Post, PostComment, PostFlowScore,
    PostLike, PostView, PostYanka, SavedPost, User,
    FlowSignal, UserInterestProfile, VideoView,
)

flow_bp = Blueprint('flow', __name__, url_prefix='/flow')

# ─────────────────────────────────────────────────────────────
#  PRISM Ağırlıkları
# ─────────────────────────────────────────────────────────────
W_RELEVANCE   = 0.35
W_QUALITY     = 0.25
W_SOCIAL      = 0.20
W_FRESHNESS   = 0.15
W_DIVERSITY   = 0.05

QUALITY_CAP   = 20.0
SOCIAL_CAP    = 10.0

HALF_LIFE = {
    'video':   6,
    'code':    12,
    'project': 12,
    'text':    24,
    'article': 48,
    'poll':    18,
    'image':   20,
}

# Sinyal ağırlıkları (FlowSignal.value hesaplaması için)
SIGNAL_WEIGHTS = {
    'like':          10,
    'yanka':         15,
    'save':          20,
    'comment':       12,
    'less_like_this':-25,
    'follow':        30,
    'profile_visit':  8,
    'view_short':     3,
    'view_long':      6,
    'skip':          -2,
    'expand':         5,
}

PER_PAGE = 15  # Her sayfada kaç gönderi

# ─────────────────────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────

def _safe_log(n: float) -> float:
    return math.log(1 + max(0, n))


def _quality_score(post: Post) -> float:
    """Takipçi sayısına normalize edilmiş etkileşim skoru."""
    author = post.author
    follower_n = _safe_log(author.follower_count()) if author else 1.0
    follower_n = max(follower_n, 1.0)

    engagement = (
        post.like_count    * 1.0 +
        post.comment_count * 1.2 +
        post.yanka_count   * 1.5 +
        post.saves.count() * 2.0
    )
    return min(1.0, engagement / (QUALITY_CAP * follower_n))


def _freshness_score(post: Post) -> float:
    """Yarı-ömür bazlı zamansal çürüme skoru."""
    half_life_h = HALF_LIFE.get(post.post_type, 24)
    now = datetime.now(timezone.utc)
    created = post.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_hours = max(0, (now - created).total_seconds() / 3600)
    base = 0.5 ** (age_hours / half_life_h)

    # Trend boost: PostFlowScore.trend_velocity varsa ekle
    flow_score = post.flow_score
    if flow_score:
        base += flow_score.trend_velocity * 0.2
    return min(1.0, base)


def _social_proof_score(post: Post, user: User) -> float:
    """Takip ettiğin kişilerden kaçı bu gönderiye reaksiyon verdi?"""
    following_ids = [f.following_id for f in
                     Follow.query.filter_by(follower_id=user.id).all()]
    if not following_ids:
        return 0.0

    liked_count = PostLike.query.filter(
        PostLike.post_id == post.id,
        PostLike.user_id.in_(following_ids)
    ).count()

    yankaed_count = PostYanka.query.filter(
        PostYanka.post_id == post.id,
        PostYanka.user_id.in_(following_ids)
    ).count()

    saved_count = SavedPost.query.filter(
        SavedPost.post_id == post.id,
        SavedPost.user_id.in_(following_ids)
    ).count()

    social = liked_count * 2 + yankaed_count * 3 + saved_count * 4
    return min(1.0, social / SOCIAL_CAP)


def _relevance_score(post: Post, user: User) -> float:
    """
    Kullanıcının ilgi profili ile içerik eşleşmesi.
    Faz 1: OnboardingData kategori eşleşmesi + FlowSignal geçmişi + UserInterestProfile tag örtüşmesi
    """
    score = 0.0

    # 1) Meslek kategorisi eşleşmesi
    user_onb = OnboardingData.query.filter_by(user_id=user.id).first()
    post_author_onb = OnboardingData.query.filter_by(user_id=post.user_id).first()
    if user_onb and post_author_onb:
        if user_onb.profession_category == post_author_onb.profession_category:
            score += 0.3

    # 2) Kullanıcının content type tercih geçmişi
    profile = UserInterestProfile.query.filter_by(user_id=user.id).first()
    if profile:
        mix = profile.mix
        type_pref = mix.get(post.post_type, 0)
        score += type_pref * 0.3

        # 3) Semantik tag örtüşmesi
        interests = profile.interests
        flow_score = post.flow_score
        if flow_score and interests:
            post_tags = set(flow_score.tags)
            interest_keys = set(interests.keys())
            if post_tags and interest_keys:
                overlap = len(post_tags & interest_keys)
                tag_score = overlap / max(len(post_tags), 1)
                # Ağırlıklı overlap (yüksek skorlu taglara öncelik ver)
                weighted_overlap = sum(
                    interests.get(t, 0) for t in post_tags & interest_keys
                ) / max(len(post_tags), 1)
                score += (tag_score * 0.2 + weighted_overlap * 0.2)

    return min(1.0, score)


def _diversity_bonus(post: Post, session_types: list) -> float:
    """Son 10 görüntülenen gönderiden farklılık bonusu."""
    recent_10 = session_types[-10:] if len(session_types) > 10 else session_types
    if not recent_10:
        return 0.15  # Hiç görüntüleme yok → maksimum çeşitlilik bonusu
    freq = Counter(recent_10)
    if post.post_type not in recent_10:
        return 0.15
    elif freq[post.post_type] <= 2:
        return 0.08
    return 0.0


def _prism_score(post: Post, user: User, session_types: list) -> float:
    """Ana PRISM puanlama fonksiyonu."""
    r = _relevance_score(post, user)
    q = _quality_score(post)
    s = _social_proof_score(post, user)
    f = _freshness_score(post)
    d = _diversity_bonus(post, session_types)

    return (
        W_RELEVANCE * r +
        W_QUALITY   * q +
        W_SOCIAL    * s +
        W_FRESHNESS * f +
        W_DIVERSITY * d
    )


# ─────────────────────────────────────────────────────────────
#  ADAY HAVUZU OLUŞTURMA
# ─────────────────────────────────────────────────────────────

def _build_candidate_pool(user: User, filter_type: str = 'all',
                           filter_source: str = 'all') -> list[Post]:
    """
    3 havuzdan aday gönderi toplar.
    Havuz A — Sosyal çevre (max 200)
    Havuz B — Trend (max 150)
    Havuz C — Meslek kategorisi (max 100)
    """
    now = datetime.now(timezone.utc)
    seen_ids = set()
    candidates = []

    following_ids = [f.following_id for f in
                     Follow.query.filter_by(follower_id=user.id).all()]

    # ── Daha az göster filtresi ──────────────────────────────
    less_like_user_ids = set()
    less_like_type_ids = set()
    cutoff_48h = now - timedelta(hours=48)
    suppressed = FlowSignal.query.filter(
        FlowSignal.user_id == user.id,
        FlowSignal.signal_type == 'less_like_this',
        FlowSignal.created_at >= cutoff_48h,
    ).all()
    for sig in suppressed:
        p = Post.query.get(sig.post_id)
        if p:
            less_like_user_ids.add(p.user_id)

    def _add(posts):
        for p in posts:
            if p.id not in seen_ids and p.user_id != user.id:
                if p.user_id not in less_like_user_ids:
                    if filter_type == 'all' or p.post_type == filter_type:
                        seen_ids.add(p.id)
                        candidates.append(p)

    # ── Havuz A — Sosyal Çevre ───────────────────────────────
    if filter_source in ('all', 'social'):
        if following_ids:
            week_ago = now - timedelta(days=7)
            pool_a = Post.query.filter(
                Post.user_id.in_(following_ids),
                Post.created_at >= week_ago,
                Post.source == 'social',   # Site güncellemeleri PRISM'e dahil edilmez
            ).order_by(Post.created_at.desc()).limit(200).all()
            _add(pool_a)

    # ── Havuz B — Trend ──────────────────────────────────────
    if filter_source in ('all', 'explore'):
        two_days_ago = now - timedelta(hours=48)
        # Etkileşim hızına göre sırala (like + comment + yanka subquery)
        pool_b = (
            db.session.query(Post)
            .outerjoin(PostLike, PostLike.post_id == Post.id)
            .outerjoin(PostYanka, PostYanka.post_id == Post.id)
            .filter(
                Post.created_at >= two_days_ago,
                Post.source == 'social',   # Site güncellemeleri trend havuzuna girmez
            )
            .group_by(Post.id)
            .order_by(
                desc(func.count(PostLike.id) + func.count(PostYanka.id))
            )
            .limit(150)
            .all()
        )
        _add(pool_b)

    # ── Havuz C — Meslek Kategorisi ──────────────────────────
    if filter_source in ('all', 'professional'):
        user_onb = OnboardingData.query.filter_by(user_id=user.id).first()
        if user_onb and user_onb.profession_category:
            # Aynı meslek kategorisindeki kullanıcıların gönderileri
            same_cat_users = db.session.query(OnboardingData.user_id).filter(
                OnboardingData.profession_category == user_onb.profession_category,
                OnboardingData.user_id != user.id,
            ).all()
            same_cat_ids = [r[0] for r in same_cat_users]
            if same_cat_ids:
                week_ago = now - timedelta(days=7)
                pool_c = Post.query.filter(
                    Post.user_id.in_(same_cat_ids),
                    Post.created_at >= week_ago,
                    Post.source == 'social',   # Site güncellemeleri meslek havuzuna girmez
                ).order_by(Post.created_at.desc()).limit(100).all()
                _add(pool_c)

    return candidates


# ─────────────────────────────────────────────────────────────
#  GUARDRAILS
# ─────────────────────────────────────────────────────────────

def _apply_guardrails(ranked: list[Post]) -> list[Post]:
    """
    Kural 1: Aynı yazardan max 2 arka arkaya
    Kural 2: Her 10'dan en az 2'si farklı kategoriden
    """
    result = []
    author_streak = {}

    for post in ranked:
        # Kural 1 — Streak kontrolü
        streak = author_streak.get(post.user_id, 0)
        if streak >= 2:
            continue
        result.append(post)
        # Streak güncelle
        for uid in list(author_streak.keys()):
            if uid != post.user_id:
                author_streak[uid] = 0
        author_streak[post.user_id] = streak + 1

    return result


# ─────────────────────────────────────────────────────────────
#  KULLANICI İLGİ PROFİLİ GÜNCELLEME
# ─────────────────────────────────────────────────────────────

def _update_interest_profile(user: User):
    """
    Kullanıcının son FlowSignal verilerinden ilgi profili günceller.
    Her 10 sinyalde bir çağrılır.
    """
    from collections import defaultdict

    profile = UserInterestProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        profile = UserInterestProfile(user_id=user.id)
        db.session.add(profile)

    # Son 30 günlük sinyaller
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    signals = FlowSignal.query.filter(
        FlowSignal.user_id == user.id,
        FlowSignal.created_at >= cutoff,
    ).all()

    # Content type mix hesapla
    type_weights = defaultdict(float)
    tag_weights = defaultdict(float)

    for sig in signals:
        post = Post.query.get(sig.post_id)
        if not post:
            continue
        w = SIGNAL_WEIGHTS.get(sig.signal_type, 0)
        if w > 0:
            type_weights[post.post_type] += w
            # Semantic tags varsa ekle
            if post.flow_score and post.flow_score.tags:
                for tag in post.flow_score.tags:
                    tag_weights[tag] += w * 0.5

    # Normalize
    total_type = sum(type_weights.values()) or 1.0
    content_mix = {k: round(v / total_type, 3) for k, v in type_weights.items()}

    total_tag = sum(tag_weights.values()) or 1.0
    # Top 30 tag tut
    top_tags = sorted(tag_weights.items(), key=lambda x: -x[1])[:30]
    interests = {k: round(v / total_tag, 3) for k, v in top_tags}

    profile.mix = content_mix
    profile.interests = interests
    profile.last_updated = datetime.now(timezone.utc)
    profile.signal_count = len(signals)
    db.session.commit()


# ─────────────────────────────────────────────────────────────
#  TREND VELOCITY HESAPLAMA
# ─────────────────────────────────────────────────────────────

def _compute_trend_velocity(post: Post) -> float:
    """Son 2 saatteki etkileşim artış hızı."""
    now = datetime.now(timezone.utc)
    two_h_ago = now - timedelta(hours=2)
    four_h_ago = now - timedelta(hours=4)

    recent = PostLike.query.filter(
        PostLike.post_id == post.id,
        PostLike.created_at >= two_h_ago
    ).count() + PostYanka.query.filter(
        PostYanka.post_id == post.id,
        PostYanka.created_at >= two_h_ago
    ).count()

    prev = PostLike.query.filter(
        PostLike.post_id == post.id,
        PostLike.created_at >= four_h_ago,
        PostLike.created_at < two_h_ago
    ).count() + PostYanka.query.filter(
        PostYanka.post_id == post.id,
        PostYanka.created_at >= four_h_ago,
        PostYanka.created_at < two_h_ago
    ).count()

    if prev == 0:
        return min(1.0, recent * 0.1)
    return min(1.0, (recent - prev) / max(prev, 1))


# ─────────────────────────────────────────────────────────────
#  TRENDING TOPICS
# ─────────────────────────────────────────────────────────────

def _get_trending_topics(limit: int = 8) -> list[dict]:
    """PostFlowScore.semantic_tags'dan bu haftanın yükselen konularını çıkar."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    scores = (
        db.session.query(PostFlowScore)
        .join(Post, Post.id == PostFlowScore.post_id)
        .filter(Post.created_at >= week_ago)
        .all()
    )

    tag_counts = Counter()
    for score in scores:
        for tag in score.tags:
            tag_counts[tag] += 1

    return [
        {'tag': tag, 'count': count}
        for tag, count in tag_counts.most_common(limit)
    ]


# ─────────────────────────────────────────────────────────────
#  ÖNERILEN KİŞİLER
# ─────────────────────────────────────────────────────────────

def _get_suggested_people(user: User, limit: int = 5) -> list[User]:
    """Flow için önerilen kişiler: meslek kategorisi eşleşenleri ve popüler profiller."""
    following_ids = {f.following_id for f in
                     Follow.query.filter_by(follower_id=user.id).all()}
    following_ids.add(user.id)

    user_onb = OnboardingData.query.filter_by(user_id=user.id).first()
    suggestions = []

    if user_onb and user_onb.profession_category:
        same_cat = (
            db.session.query(User)
            .join(OnboardingData, OnboardingData.user_id == User.id)
            .filter(
                OnboardingData.profession_category == user_onb.profession_category,
                User.id.notin_(following_ids),
            )
            .limit(limit * 2)
            .all()
        )
        # Takipçi sayısına göre sırala
        same_cat.sort(key=lambda u: u.follower_count(), reverse=True)
        suggestions.extend(same_cat[:limit])

    # Yeterli değilse genel popüler kullanıcıları doldur
    if len(suggestions) < limit:
        needed = limit - len(suggestions)
        existing_ids = following_ids | {u.id for u in suggestions}
        popular = (
            db.session.query(User)
            .filter(User.id.notin_(existing_ids))
            .limit(needed * 3)
            .all()
        )
        popular.sort(key=lambda u: u.follower_count(), reverse=True)
        suggestions.extend(popular[:needed])

    return suggestions[:limit]


# ─────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────

@flow_bp.route('/')
@login_required
def index():
    """Flow ana sayfası."""
    filter_type   = request.args.get('type', 'all')
    filter_source = request.args.get('source', 'all')

    # Session'daki görüntüleme tipi geçmişi (diversity bonus için)
    session_types = session.get('flow_seen_types', [])

    # Aday havuzu oluştur
    candidates = _build_candidate_pool(
        current_user,
        filter_type=filter_type,
        filter_source=filter_source,
    )

    # PRISM ile puanla
    scored = []
    for post in candidates:
        score = _prism_score(post, current_user, session_types)
        scored.append((score, post))

    scored.sort(key=lambda x: -x[0])

    # Guardrails uygula
    ranked_posts = _apply_guardrails([p for _, p in scored])

    # Sayfalama
    page = request.args.get('page', 1, type=int)
    total = len(ranked_posts)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    page_posts = ranked_posts[start:end]

    # Ekstra veriler
    trending_topics  = _get_trending_topics(limit=8)
    suggested_people = _get_suggested_people(current_user, limit=5)

    user_onb = OnboardingData.query.filter_by(user_id=current_user.id).first()

    return render_template(
        'flow.html',
        posts            = page_posts,
        total            = total,
        page             = page,
        per_page         = PER_PAGE,
        has_more         = end < total,
        filter_type      = filter_type,
        filter_source    = filter_source,
        trending_topics  = trending_topics,
        suggested_people = suggested_people,
        user_onb         = user_onb,
    )


@flow_bp.route('/posts')
@login_required
def get_posts():
    """AJAX: PRISM skorlu gönderi listesi (JSON)."""
    filter_type   = request.args.get('type', 'all')
    filter_source = request.args.get('source', 'all')
    page          = request.args.get('page', 1, type=int)

    session_types = session.get('flow_seen_types', [])

    candidates = _build_candidate_pool(
        current_user,
        filter_type=filter_type,
        filter_source=filter_source,
    )

    scored = []
    for post in candidates:
        score = _prism_score(post, current_user, session_types)
        scored.append((score, post))
    scored.sort(key=lambda x: -x[0])
    ranked = _apply_guardrails([p for _, p in scored])

    total = len(ranked)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    page_posts = ranked[start:end]

    data = []
    for post in page_posts:
        author = post.author
        data.append({
            'id':           post.id,
            'slug':         post.slug,
            'post_type':    post.post_type,
            'content':      post.content[:300],
            'code_language':post.code_language,
            'media':        post.media_list,
            'like_count':   post.like_count,
            'comment_count':post.comment_count,
            'yanka_count':  post.yanka_count,
            'view_count':   post.view_count,
            'created_at':   post.created_at.isoformat(),
            'is_liked':     post.is_liked_by(current_user),
            'is_saved':     post.is_saved_by(current_user),
            'author': {
                'id':       author.id,
                'name':     author.full_name or author.email.split('@')[0],
                'username': author.email.split('@')[0],
                'avatar':   (author.site.avatar_file if author.site else None),
            } if author else {},
        })

    return jsonify({
        'posts':    data,
        'page':     page,
        'has_more': end < total,
        'total':    total,
    })


@flow_bp.route('/signal', methods=['POST'])
@login_required
def record_signal():
    """
    Batch sinyal yazma. Body: [{post_id, signal_type, context}, ...]
    Debounced — JS her 10 saniyede bir gönderir.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        return jsonify({'ok': False, 'error': 'list expected'}), 400

    new_count = 0
    for item in payload[:50]:  # max 50 sinyal per batch
        post_id     = item.get('post_id')
        signal_type = item.get('signal_type', '')
        ctx         = item.get('context', 'flow')

        if not post_id or signal_type not in SIGNAL_WEIGHTS:
            continue
        post = Post.query.get(post_id)
        if not post:
            continue

        value = float(SIGNAL_WEIGHTS.get(signal_type, 0))
        sig = FlowSignal(
            user_id=current_user.id,
            post_id=post_id,
            signal_type=signal_type,
            value=value,
            context=ctx,
        )
        db.session.add(sig)
        new_count += 1

        # Session'daki tip geçmişini güncelle (diversity bonus için)
        if signal_type in ('view_short', 'view_long'):
            seen = session.get('flow_seen_types', [])
            seen.append(post.post_type)
            session['flow_seen_types'] = seen[-20:]  # Son 20'yi tut

    db.session.commit()

    # Her 10 yeni sinyalde interest profile güncelle
    profile = UserInterestProfile.query.filter_by(user_id=current_user.id).first()
    if profile:
        profile.signal_count = (profile.signal_count or 0) + new_count
        if profile.signal_count % 10 < new_count:
            _update_interest_profile(current_user)
    else:
        if new_count >= 5:
            _update_interest_profile(current_user)
        else:
            new_profile = UserInterestProfile(
                user_id=current_user.id,
                signal_count=new_count,
            )
            db.session.add(new_profile)
            db.session.commit()

    return jsonify({'ok': True, 'recorded': new_count})


@flow_bp.route('/why/<int:post_id>')
@login_required
def why_this(post_id: int):
    """
    AI açıklama: Bu içerik neden gösteriliyor?
    Groq LLAMA 3.1-8b kullanır (hafif model, düşük maliyet).
    """
    post = Post.query.get_or_404(post_id)

    reasons = []

    # 1) Sosyal çevre kontrolü
    following_ids = {f.following_id for f in
                     Follow.query.filter_by(follower_id=current_user.id).all()}

    if post.user_id in following_ids:
        author = post.author
        reasons.append(f"@{(author.full_name or author.email.split('@')[0])}'i takip ediyorsun")

    # 2) Sosyal onay
    liked_by = PostLike.query.filter(
        PostLike.post_id == post.id,
        PostLike.user_id.in_(following_ids)
    ).count()
    if liked_by > 0:
        reasons.append(f"Takip ettiğin {liked_by} kişi bu gönderiyi beğendi")

    # 3) Meslek kategorisi eşleşmesi
    user_onb = OnboardingData.query.filter_by(user_id=current_user.id).first()
    post_author_onb = OnboardingData.query.filter_by(user_id=post.user_id).first()
    if user_onb and post_author_onb:
        if user_onb.profession_category == post_author_onb.profession_category:
            reasons.append("Seninle aynı alanda profesyoneller paylaşıyor")

    # 4) İlgi etiketleri
    profile = UserInterestProfile.query.filter_by(user_id=current_user.id).first()
    if profile and post.flow_score:
        interests = profile.interests
        post_tags = post.flow_score.tags
        matches = [t for t in post_tags if t in interests][:3]
        if matches:
            reasons.append(f"İlgi alanların: {', '.join(matches)}")

    # Groq ile kısa açıklama (sadece reasons listesi boşsa veya daha güzel bir dil istiyorsak)
    ai_explanation = None
    if os.environ.get('GROQ_API_KEY') and not reasons:
        try:
            from groq import Groq
            client = Groq(api_key=os.environ['GROQ_API_KEY'])
            content_preview = post.content[:200] if post.content else ''
            prompt = (
                f"Bir kullanıcıya şu gönderiyi neden önerdiğini tek cümleyle Türkçe açıkla. "
                f"Gönderi tipi: {post.post_type}. "
                f"İçerik: {content_preview}. "
                f"Kullanıcının meslek alanı: {user_onb.profession_category if user_onb else 'bilinmiyor'}. "
                f"Cevap 'Bu içerik sana gösterildi çünkü...' şeklinde başlasın. Sadece 1 cümle."
            )
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.5,
            )
            ai_explanation = resp.choices[0].message.content.strip()
        except Exception:
            pass

    if not reasons and not ai_explanation:
        reasons = ["Keşfet algoritması bu içeriği senin için seçti"]

    return jsonify({
        'reasons':        reasons,
        'ai_explanation': ai_explanation,
        'post_id':        post_id,
    })


@flow_bp.route('/less-like', methods=['POST'])
@login_required
def less_like_this():
    """'Daha az göster' — 48 saat boyunca bu yazar ve tip bastırılır."""
    data    = request.get_json(silent=True) or {}
    post_id = data.get('post_id')
    if not post_id:
        return jsonify({'ok': False}), 400

    post = Post.query.get_or_404(post_id)
    sig = FlowSignal(
        user_id=current_user.id,
        post_id=post_id,
        signal_type='less_like_this',
        value=SIGNAL_WEIGHTS['less_like_this'],
        context='flow',
    )
    db.session.add(sig)
    db.session.commit()
    return jsonify({'ok': True})


@flow_bp.route('/trending-topics')
@login_required
def trending_topics():
    """Yükselen konular widget verisi."""
    topics = _get_trending_topics(limit=10)
    return jsonify({'topics': topics})


def tag_post_internal(post_id: int) -> dict:
    """
    İçerik tagger — Flask context dışından (thread) çağrılabilir.
    Yeni post oluşturulduğunda feed.py tarafından arka planda tetiklenir.
    """
    from app import create_app
    _app = create_app()
    with _app.app_context():
        return _run_tagger(post_id)


def _run_tagger(post_id: int) -> dict:
    """Asıl tagger mantığı — app context içinde çalışır."""
    post = Post.query.get(post_id)
    if not post:
        return {'ok': False}

    existing = PostFlowScore.query.filter_by(post_id=post_id).first()
    now = datetime.now(timezone.utc)
    if existing and existing.expires_at and existing.expires_at > now:
        return {'ok': True, 'cached': True, 'tags': existing.tags}

    tags = []
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key and post.content:
        try:
            from groq import Groq
            import re
            client = Groq(api_key=groq_key)
            prompt = (
                f"Bu içeriğin semantik etiketlerini Türkçe ve İngilizce olarak JSON listesi "
                f"olarak ver. Maksimum 8 etiket. Sadece JSON array döndür, başka hiçbir şey yazma. "
                f"Örnek: [\"python\", \"backend\", \"yazılım\"]\n\n"
                f"İçerik tipi: {post.post_type}\n"
                f"İçerik: {post.content[:500]}"
            )
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100, temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip()
            m = re.search(r'\[.*?\]', raw, re.DOTALL)
            if m:
                tags = json.loads(m.group())[:8]
        except Exception:
            tags = []

    if not tags:
        content_lower = post.content.lower() if post.content else ''
        keyword_map = {
            'python': 'python', 'javascript': 'javascript', 'js': 'javascript',
            'react': 'react', 'vue': 'vue', 'angular': 'angular',
            'tasarım': 'tasarım', 'design': 'design', 'figma': 'figma',
            'girişim': 'girişimcilik', 'startup': 'startup',
            'yapay zeka': 'yapay-zeka', 'ai': 'yapay-zeka', 'ml': 'machine-learning',
            'backend': 'backend', 'frontend': 'frontend',
            'müzik': 'müzik', 'fotoğraf': 'fotoğraf', 'video': 'video',
            'spor': 'spor', 'sağlık': 'sağlık', 'eğitim': 'eğitim',
        }
        for kw, tag in keyword_map.items():
            if kw in content_lower and tag not in tags:
                tags.append(tag)
        tags = tags[:8]

    quality  = _quality_score(post)
    velocity = _compute_trend_velocity(post)

    if existing:
        existing.quality_score  = quality
        existing.trend_velocity = velocity
        existing.semantic_tags  = json.dumps(tags, ensure_ascii=False)
        existing.computed_at    = now
        existing.expires_at     = now + timedelta(hours=2)
    else:
        db.session.add(PostFlowScore(
            post_id=post_id,
            quality_score=quality,
            trend_velocity=velocity,
            semantic_tags=json.dumps(tags, ensure_ascii=False),
            computed_at=now,
            expires_at=now + timedelta(hours=2),
        ))
    db.session.commit()
    return {'ok': True, 'tags': tags}


@flow_bp.route('/tag-post/<int:post_id>', methods=['POST'])
@login_required
def tag_post(post_id: int):
    """
    İçerik tagger: Groq LLAMA 3.3-70b ile semantic_tags üret.
    Cron veya post oluşturulduğunda tetiklenir.
    """
    post = Post.query.get_or_404(post_id)

    # Mevcut skor varsa ve 2 saatten yeni ise atla
    existing = PostFlowScore.query.filter_by(post_id=post_id).first()
    now = datetime.now(timezone.utc)
    if existing and existing.expires_at and existing.expires_at > now:
        return jsonify({'ok': True, 'cached': True, 'tags': existing.tags})

    tags = []
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key and post.content:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            content_preview = post.content[:500]
            prompt = (
                f"Bu içeriğin semantik etiketlerini Türkçe ve İngilizce olarak JSON listesi "
                f"olarak ver. Maksimum 8 etiket. Sadece JSON array döndür, başka hiçbir şey yazma. "
                f"Örnek: [\"python\", \"backend\", \"yazılım\"]\n\n"
                f"İçerik tipi: {post.post_type}\n"
                f"İçerik: {content_preview}"
            )
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip()
            # JSON parse
            import re
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                tags = json.loads(match.group())[:8]
        except Exception:
            tags = []

    # Kural bazlı tag oluşturma (Groq yoksa veya başarısızsa)
    if not tags:
        content_lower = post.content.lower() if post.content else ''
        keyword_map = {
            'python': 'python', 'javascript': 'javascript', 'js': 'javascript',
            'react': 'react', 'vue': 'vue', 'angular': 'angular',
            'tasarım': 'tasarım', 'design': 'design', 'figma': 'figma',
            'girişim': 'girişimcilik', 'startup': 'startup',
            'yapay zeka': 'yapay-zeka', 'ai': 'yapay-zeka', 'ml': 'machine-learning',
            'backend': 'backend', 'frontend': 'frontend',
            'müzik': 'müzik', 'fotoğraf': 'fotoğraf', 'video': 'video',
            'spor': 'spor', 'sağlık': 'sağlık', 'eğitim': 'eğitim',
        }
        for keyword, tag in keyword_map.items():
            if keyword in content_lower and tag not in tags:
                tags.append(tag)
        tags = tags[:8]

    # PostFlowScore kaydet/güncelle
    quality = _quality_score(post)
    velocity = _compute_trend_velocity(post)

    if existing:
        existing.quality_score  = quality
        existing.trend_velocity = velocity
        existing.semantic_tags  = json.dumps(tags, ensure_ascii=False)
        existing.computed_at    = now
        existing.expires_at     = now + timedelta(hours=2)
    else:
        new_score = PostFlowScore(
            post_id=post_id,
            quality_score=quality,
            trend_velocity=velocity,
            semantic_tags=json.dumps(tags, ensure_ascii=False),
            computed_at=now,
            expires_at=now + timedelta(hours=2),
        )
        db.session.add(new_score)

    db.session.commit()
    return jsonify({'ok': True, 'tags': tags, 'quality': quality})


@flow_bp.route('/update-interest', methods=['POST'])
@login_required
def update_interest():
    """Kullanıcının ilgi profilini manuel olarak güncelle."""
    _update_interest_profile(current_user)
    profile = UserInterestProfile.query.filter_by(user_id=current_user.id).first()
    return jsonify({
        'ok': True,
        'interests': profile.interests if profile else {},
        'content_mix': profile.mix if profile else {},
    })


# ─────────────────────────────────────────────────────────────
#  LENS — Tam Ekran Video Modu
# ─────────────────────────────────────────────────────────────
LENS_PER_PAGE = 10   # Her yükleme turu max video sayısı

@flow_bp.route('/lens')
@login_required
def lens():
    """Lens: PRISM skorlu video-only dikey snap scroll."""
    session_types = session.get('flow_seen_types', [])

    # Sadece video içerikler için aday havuzu
    candidates = _build_candidate_pool(
        current_user,
        filter_type='video',
        filter_source='all',
    )

    # PRISM ile puanla
    scored = []
    for post in candidates:
        score = _prism_score(post, current_user, session_types)
        scored.append((score, post))
    scored.sort(key=lambda x: -x[0])

    ranked = _apply_guardrails([p for _, p in scored])

    page     = request.args.get('page', 1, type=int)
    total    = len(ranked)
    start    = (page - 1) * LENS_PER_PAGE
    end      = start + LENS_PER_PAGE
    videos   = ranked[start:end]
    has_more = end < total

    return render_template(
        'lens.html',
        videos   = videos,
        page     = page,
        has_more = has_more,
        total    = total,
    )


@flow_bp.route('/lens/posts')
@login_required
def lens_posts():
    """Lens için AJAX sayfalama — JSON."""
    session_types = session.get('flow_seen_types', [])
    candidates    = _build_candidate_pool(
        current_user, filter_type='video', filter_source='all'
    )
    scored = sorted(
        [(_prism_score(p, current_user, session_types), p) for p in candidates],
        key=lambda x: -x[0],
    )
    ranked   = _apply_guardrails([p for _, p in scored])
    page     = request.args.get('page', 1, type=int)
    total    = len(ranked)
    start    = (page - 1) * LENS_PER_PAGE
    end      = start + LENS_PER_PAGE
    videos   = ranked[start:end]

    data = []
    for post in videos:
        author = post.author
        media  = post.media_list
        if not media:
            continue
        data.append({
            'id':         post.id,
            'slug':       post.slug,
            'content':    post.content[:300] if post.content else '',
            'media':      media,
            'like_count': post.like_count,
            'comment_count': post.comment_count,
            'view_count': post.view_count,
            'is_liked':   post.is_liked_by(current_user),
            'is_saved':   post.is_saved_by(current_user),
            'created_at': post.created_at.isoformat(),
            'author': {
                'id':     author.id,
                'name':   author.full_name or author.email.split('@')[0],
                'avatar': (author.site.avatar_file if author.site else None),
            } if author else {},
        })

    return jsonify({'videos': data, 'page': page, 'has_more': end < total})


@flow_bp.route('/profile-topics/<int:user_id>')
@login_required
def profile_topics(user_id: int):
    """Kullanıcının ilgi topic'leri (widget için)."""
    profile = UserInterestProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        return jsonify({'topics': [], 'mix': {}})
    return jsonify({
        'topics': [
            {'tag': k, 'score': v}
            for k, v in sorted(profile.interests.items(), key=lambda x: -x[1])[:10]
        ],
        'mix': profile.mix,
    })
