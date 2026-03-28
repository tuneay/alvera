"""
Alvera Social — Akış (Social Feed) Blueprint
Takip · Öneri · Görülmüş-gönderi filtresi · Taze içerik · Canlı bildirim
"""
import json
import os
import secrets
import uuid
from datetime import datetime, timezone, date, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import and_, case, func, not_, or_
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Follow, MindMap, Notification, OnboardingData, Post, PostComment,
    PostLike, PostView, PostYanka, SavedPost, Site, User, UserProfileExtras,
    VideoView,
)
from blueprints.notifications import create_notification, notify_mentions

# ────────────────────────────────────────────────────────────────
#   Sabit Haritalamalar
# ────────────────────────────────────────────────────────────────
CAT_MAP = {
    'is_professional':    ('💼', 'İş Profesyoneli'),
    'artist_designer':    ('🎨', 'Sanatçı & Tasarımcı'),
    'musician':           ('🎵', 'Müzisyen'),
    'photographer_video': ('📸', 'Fotoğrafçı & Video'),
    'athlete_coach':      ('🏃', 'Sporcu & Koç'),
    'academic':           ('🎓', 'Akademisyen'),
    'content_creator':    ('📱', 'İçerik Üretici'),
    'chef_gourmet':       ('👨‍🍳', 'Şef & Gurme'),
    'engineer_architect': ('⚙️',  'Mühendis & Mimar'),
    'health_wellness':    ('💚', 'Sağlık & Wellness'),
    'entrepreneur':       ('🚀', 'Girişimci'),
    'writer':             ('✍️',  'Yazar'),
}

PKG_MAP = {
    '1': ('P1', 'Minimal'),
    '2': ('P2', 'Standart'),
    '3': ('P3', 'Marka'),
}

feed_bp = Blueprint('feed', __name__, url_prefix='/feed')

PER_PAGE     = 12   # Her sayfada kaç gönderi
POLL_LIMIT   = 10   # Yeni gönderi yoklaması için max


def _generate_post_slug() -> str:
    """10 haneli URL-güvenli rastgele slug üretir (sıralı ID'yi gizler)."""
    while True:
        slug = secrets.token_urlsafe(8)[:10]
        if not Post.query.filter_by(slug=slug).first():
            return slug


# ── Resim yükleme sabitleri ──────────────────────────────────────────────────
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_BYTES   = 10 * 1024 * 1024   # 10 MB / resim
MAX_IMAGES        = 4                   # Bir gönderide max resim sayısı

# ── Video yükleme sabitleri ───────────────────────────────────────────────────
ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'mov'}
MAX_VIDEO_BYTES   = 150 * 1024 * 1024  # 150 MB — sunucu sıkıştırır
MAX_VIDEO_SECONDS = 90                  # Flow planına göre maks 90 sn


# ════════════════════════════════════════════════════════════════
#   ANA AKIş SAYFASI
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/')
@login_required
def index():
    # AJAX sayfalama isteği
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return _ajax_feed_page()

    page  = request.args.get('page', 1, type=int)
    mode  = request.args.get('mode', 'fresh')   # 'fresh' | 'all'

    posts = _build_feed(current_user, page=page, per_page=PER_PAGE, mode=mode)
    suggestions      = _get_suggestions(current_user, limit=5)
    trending_posts   = _get_trending_posts(limit=3)
    follow_count     = current_user.follow_count()
    follower_count   = current_user.follower_count()
    yanka_remaining  = _daily_yanka_remaining(current_user.id)

    # En son gönderi ID'si — polling için
    latest_id = posts.items[0].id if posts.items else 0

    return render_template(
        'feed.html',
        posts           = posts,
        suggestions     = suggestions,
        trending_posts  = trending_posts,
        follow_count    = follow_count,
        follower_count  = follower_count,
        page            = page,
        mode            = mode,
        latest_id       = latest_id,
        has_next        = posts.has_next,
        viewer          = current_user,
        yanka_remaining = yanka_remaining,
    )


def _ajax_feed_page():
    """Sonsuz scroll için AJAX sayfa yükleme."""
    page = request.args.get('page', 1, type=int)
    mode = request.args.get('mode', 'fresh')
    posts = _build_feed(current_user, page=page, per_page=PER_PAGE, mode=mode)

    html_parts = []
    for post in posts.items:
        html_parts.append(render_template('_feed_post.html', post=post, viewer=current_user))

    return jsonify({
        'html':     ''.join(html_parts),
        'has_next': posts.has_next,
        'count':    len(posts.items),
    })


# ════════════════════════════════════════════════════════════════
#   GÖNDERI OLUŞTUR
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post', methods=['POST'])
@login_required
def create_post():
    """
    Gönderi oluştur. Üç varyant:
      • text / project  → JSON body
      • image           → multipart/form-data (dosya + isteğe bağlı açıklama)
      • code            → JSON body (content = kod, code_language = dil)
    """
    is_multipart = request.content_type and 'multipart' in request.content_type

    if is_multipart:
        post_type     = request.form.get('post_type', Post.TYPE_TEXT).strip()
        content       = request.form.get('content', '').strip()
        code_language = ''
        code_caption  = ''
    else:
        data          = request.get_json(silent=True) or {}
        post_type     = data.get('post_type', Post.TYPE_TEXT).strip()
        content       = data.get('content', '').strip()
        code_language = (data.get('code_language') or '').strip()[:30]
        code_caption  = (data.get('caption') or '').strip()[:300]

    if post_type not in Post.VALID_TYPES:
        return jsonify({'ok': False, 'error': 'Geçersiz gönderi tipi.'}), 422

    # İçerik validasyonu (resim ve video gönderilerinde açıklama zorunlu değil)
    if post_type not in (Post.TYPE_IMAGE, Post.TYPE_VIDEO) and not content:
        return jsonify({'ok': False, 'error': 'İçerik boş olamaz.'}), 422
    if len(content) > 1500:
        return jsonify({'ok': False, 'error': 'İçerik en fazla 1500 karakter olabilir.'}), 422

    # ── Resim yükleme ────────────────────────────────────────────────────────
    media_list = []
    if post_type == Post.TYPE_IMAGE:
        files = request.files.getlist('images')
        valid_files = [f for f in files if f and f.filename]

        if not valid_files:
            return jsonify({'ok': False, 'error': 'En az bir resim seçmelisiniz.'}), 422
        if len(valid_files) > MAX_IMAGES:
            return jsonify({'ok': False, 'error': f'En fazla {MAX_IMAGES} resim yüklenebilir.'}), 422

        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_user.id))
        os.makedirs(upload_dir, exist_ok=True)

        for f in valid_files:
            ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
            if ext not in ALLOWED_IMAGE_EXT:
                return jsonify({'ok': False, 'error': f'Desteklenmeyen format: .{ext}. İzin verilenler: jpg, png, gif, webp'}), 422
            f.seek(0, 2)
            size = f.tell(); f.seek(0)
            if size > MAX_IMAGE_BYTES:
                return jsonify({'ok': False, 'error': 'Her resim en fazla 10 MB olabilir.'}), 422

            filename = f'{uuid.uuid4().hex}.{ext}'
            f.save(os.path.join(upload_dir, filename))
            media_list.append({'filename': filename, 'type': 'image'})

    # ── Video yükleme ────────────────────────────────────────────────────────
    if post_type == Post.TYPE_VIDEO:
        video_file = request.files.get('video')
        if not video_file or not video_file.filename:
            return jsonify({'ok': False, 'error': 'Video dosyası seçmelisiniz.'}), 422
        ext = video_file.filename.rsplit('.', 1)[-1].lower() if '.' in video_file.filename else ''
        if ext not in ALLOWED_VIDEO_EXT:
            return jsonify({'ok': False, 'error': 'Desteklenmeyen format. İzin verilenler: mp4, webm, mov'}), 422
        video_file.seek(0, 2); size = video_file.tell(); video_file.seek(0)
        if size > MAX_VIDEO_BYTES:
            return jsonify({'ok': False, 'error': 'Video en fazla 150 MB olabilir.'}), 422
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_user.id))
        os.makedirs(upload_dir, exist_ok=True)
        filename = f'{uuid.uuid4().hex}.{ext}'
        video_file.save(os.path.join(upload_dir, filename))
        media_list.append({'filename': filename, 'type': 'video'})

    post = Post(
        user_id       = current_user.id,
        post_type     = post_type,
        content       = content,
        code_language = code_language if post_type == Post.TYPE_CODE else None,
        link_title    = code_caption   if post_type == Post.TYPE_CODE else None,
        media_files   = json.dumps(media_list) if media_list else None,
        slug          = _generate_post_slug(),
    )
    db.session.add(post)
    db.session.commit()

    # Bildirim: gönderi içindeki @mention'lar
    if content:
        notify_mentions(content, actor_id=current_user.id, post_id=post.id)

    # ── Faz 2: Flow content tagger — arka planda tetikle ──────────────────
    # Groq varsa semantic_tags üret (non-blocking thread)
    try:
        import threading
        from blueprints.flow import tag_post_internal
        t = threading.Thread(target=tag_post_internal, args=(post.id,), daemon=True)
        t.start()
    except Exception:
        pass   # tagger başarısız olursa gönderi yine de kayıtlı

    html = render_template('_feed_post.html', post=post, viewer=current_user)
    return jsonify({'ok': True, 'post_id': post.id, 'slug': post.slug, 'html': html})


# ════════════════════════════════════════════════════════════════
#   GÖNDERI DETAY SAYFASI  — Paylaşılabilir permalink
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/u/<int:user_id>/post/<slug>', methods=['GET'])
@login_required
def post_detail(user_id: int, slug: str):
    """
    Tek gönderi detay sayfası — /feed/u/<user_id>/post/<slug>
    Tüm yorumları, aksiyonları ve OG meta tag'larını içerir.
    """
    post = Post.query.options(
        joinedload(Post.author),
    ).filter(Post.slug == slug, Post.user_id == user_id).first_or_404()

    # Görüntülenme sayacını artır (kendi gönderisi değilse)
    if post.user_id != current_user.id:
        exists = PostView.query.filter_by(
            post_id=post.id, user_id=current_user.id
        ).first()
        if not exists:
            try:
                db.session.add(PostView(post_id=post.id, user_id=current_user.id))
                db.session.commit()
            except Exception:
                db.session.rollback()

    yanka_remaining = _daily_yanka_remaining(current_user.id)

    return render_template(
        'post_detail.html',
        post            = post,
        viewer          = current_user,
        yanka_remaining = yanka_remaining,
    )


# ════════════════════════════════════════════════════════════════
#   GÖNDERI SİL
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post/<slug>', methods=['DELETE'])
@login_required
def delete_post(slug: str):
    post = Post.query.filter_by(slug=slug, user_id=current_user.id).first_or_404()
    db.session.delete(post)
    db.session.commit()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════
#   GÖRÜLDÜ İŞARETLE  ← Intersection Observer tetikler
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post/<slug>/seen', methods=['POST'])
@login_required
def mark_seen(slug: str):
    """
    Bir gönderi ekranın ortasına 0.8s+ girince istemciden çağrılır.
    Görülmüş gönderi bir daha 'fresh' akışta çıkmaz.
    """
    post = Post.query.filter_by(slug=slug).first()
    if not post:
        return jsonify({'ok': False}), 404
    exists = PostView.query.filter_by(
        post_id=post.id, user_id=current_user.id
    ).first()
    if not exists:
        try:
            db.session.add(PostView(post_id=post.id, user_id=current_user.id))
            db.session.commit()
        except Exception:
            db.session.rollback()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════
#   BOOKMARK — Gönderi Kaydetme / Kaldırma
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post/<slug>/save', methods=['POST'])
@login_required
def toggle_save(slug: str):
    """Gönderiyi kaydet ya da kaydı kaldır (toggle)."""
    post = Post.query.filter_by(slug=slug).first_or_404()
    existing = SavedPost.query.filter_by(
        post_id=post.id, user_id=current_user.id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'ok': True, 'saved': False})

    try:
        db.session.add(SavedPost(post_id=post.id, user_id=current_user.id))
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Kaydedilemedi.'}), 500

    return jsonify({'ok': True, 'saved': True})


@feed_bp.route('/video-view', methods=['POST'])
@login_required
def record_video_view():
    """Video izlenme verisini kaydet — Flow algoritması için sinyal."""
    data         = request.get_json(silent=True) or {}
    post_id      = data.get('post_id')
    watch_seconds = float(data.get('watch_seconds', 0))
    total_seconds = float(data.get('total_seconds', 1))
    replayed      = bool(data.get('replayed', False))

    post = Post.query.get(post_id)
    if not post or post.post_type != Post.TYPE_VIDEO:
        return jsonify({'ok': False}), 404

    watch_ratio = min(watch_seconds / total_seconds, 1.0) if total_seconds > 0 else 0.0

    existing = VideoView.query.filter_by(
        post_id=post.id, user_id=current_user.id
    ).first()

    if existing:
        # En uzun izlemeyi tut
        if watch_seconds > existing.watch_seconds:
            existing.watch_seconds = watch_seconds
            existing.watch_ratio   = watch_ratio
        if replayed:
            existing.replayed = True
        db.session.commit()
    else:
        db.session.add(VideoView(
            post_id       = post.id,
            user_id       = current_user.id,
            watch_seconds = watch_seconds,
            total_seconds = total_seconds,
            watch_ratio   = watch_ratio,
            replayed      = replayed,
        ))
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({'ok': True})


@feed_bp.route('/saved')
@login_required
def saved_posts():
    """Kullanıcının kaydettiği gönderiler."""
    page = request.args.get('page', 1, type=int)

    saved_ids_q = (
        db.session.query(SavedPost.post_id)
        .filter_by(user_id=current_user.id)
        .order_by(SavedPost.created_at.desc())
    )

    posts = (
        Post.query
        .filter(
            Post.id.in_(saved_ids_q),
            Post.source == 'social',   # Site güncellemeleri kaydedilenler listesine girmez
        )
        .order_by(
            db.case(
                {row.post_id: idx for idx, row in enumerate(
                    SavedPost.query.filter_by(user_id=current_user.id)
                    .order_by(SavedPost.created_at.desc()).all()
                )},
                value=Post.id
            )
        )
        .paginate(page=page, per_page=PER_PAGE, error_out=False)
    )

    suggestions     = _get_suggestions(current_user, limit=5)
    trending_posts  = _get_trending_posts(limit=3)
    follow_count    = current_user.follow_count()
    follower_count  = current_user.follower_count()
    yanka_remaining = _daily_yanka_remaining(current_user.id)
    latest_id       = posts.items[0].id if posts.items else 0

    return render_template(
        'feed.html',
        posts           = posts,
        suggestions     = suggestions,
        trending_posts  = trending_posts,
        follow_count    = follow_count,
        follower_count  = follower_count,
        page            = page,
        mode            = 'saved',
        latest_id       = latest_id,
        has_next        = posts.has_next,
        viewer          = current_user,
        yanka_remaining = yanka_remaining,
    )


# ════════════════════════════════════════════════════════════════
#   YANKI — Proof of Work onay sistemi
# ════════════════════════════════════════════════════════════════

def _daily_yanka_used(user_id: int) -> int:
    """Bugün kullanılan Yankı sayısı."""
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_start = today_start.replace(tzinfo=timezone.utc)
    return PostYanka.query.filter(
        PostYanka.user_id == user_id,
        PostYanka.created_at >= today_start,
    ).count()


def _daily_yanka_remaining(user_id: int) -> int:
    return max(0, PostYanka.DAILY_LIMIT - _daily_yanka_used(user_id))


@feed_bp.route('/post/<slug>/yanka', methods=['POST'])
@login_required
def give_yanka(slug: str):
    """
    POST /feed/post/<slug>/yanka
    Geri alınamaz Yankı ver. Günde en fazla 5.
    Yanıt: { ok, yanka_count, remaining }
    """
    post = Post.query.filter_by(slug=slug).first_or_404()

    # Kendi gönderisine Yankı verilemez
    if post.user_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendi gönderine Yankı veremezsin.'}), 422

    # Zaten Yankı verilmiş mi?
    already = PostYanka.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if already:
        return jsonify({'ok': False, 'error': 'Bu gönderiye zaten Yankı verdin.'}), 422

    # Günlük kota kontrol
    remaining = _daily_yanka_remaining(current_user.id)
    if remaining <= 0:
        return jsonify({'ok': False, 'error': 'Bugünkü Yankı kotanı doldurdun. Yarın tekrar dene.'}), 422

    yanka = PostYanka(post_id=post.id, user_id=current_user.id)
    db.session.add(yanka)
    db.session.commit()

    # Bildirim: gönderi sahibine
    create_notification(
        user_id    = post.user_id,
        actor_id   = current_user.id,
        notif_type = Notification.TYPE_YANKA,
        post_id    = post.id,
    )

    remaining_after = remaining - 1
    return jsonify({
        'ok':          True,
        'yanka_count': post.yanka_count,
        'remaining':   remaining_after,
    })


# ════════════════════════════════════════════════════════════════
#   YENİ GÖNDERI YOKLAMA  ← Her 30sn frontend'den çağrılır
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/poll')
@login_required
def poll_new():
    """
    ?since=<post_id>  → verilen ID'den büyük yeni gönderi sayısını döner.
    Takip edilenlerden + aynı kategoriden yeni gönderiler sayılır.
    """
    since_id = request.args.get('since', 0, type=int)

    following_ids = [f.following_id for f in current_user.following.all()]

    own_data     = OnboardingData.query.filter_by(user_id=current_user.id).first()
    own_category = own_data.profession_category if own_data else None

    same_cat_ids = []
    if own_category:
        rows = (
            OnboardingData.query
            .filter(
                OnboardingData.profession_category == own_category,
                OnboardingData.user_id != current_user.id,
            )
            .with_entities(OnboardingData.user_id)
            .all()
        )
        same_cat_ids = [r.user_id for r in rows]

    relevant_ids = list(set(following_ids + same_cat_ids))

    if not relevant_ids:
        return jsonify({'count': 0, 'latest_id': since_id})

    q = (
        Post.query
        .filter(
            Post.id > since_id,
            Post.user_id.in_(relevant_ids),
            Post.user_id != current_user.id,
            Post.source == 'social',   # Site güncellemeleri banner sayacına dahil edilmez
        )
    )
    count     = q.count()
    latest    = q.order_by(Post.id.desc()).first()
    latest_id = latest.id if latest else since_id

    return jsonify({'count': count, 'latest_id': latest_id})


# ════════════════════════════════════════════════════════════════
#   BEĞENİ TOGGLE
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post/<slug>/like', methods=['POST'])
@login_required
def toggle_like(slug: str):
    post     = Post.query.filter_by(slug=slug).first_or_404()
    existing = PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()

    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(PostLike(post_id=post.id, user_id=current_user.id))
        liked = True

    db.session.commit()

    # Bildirim: beğeni eklendiyse gönderi sahibine bildir
    if liked and post.user_id != current_user.id:
        create_notification(
            user_id    = post.user_id,
            actor_id   = current_user.id,
            notif_type = Notification.TYPE_LIKE,
            post_id    = post.id,
        )

    return jsonify({'ok': True, 'liked': liked, 'like_count': post.like_count})


# ════════════════════════════════════════════════════════════════
#   YORUM EKLE
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/post/<slug>/comment', methods=['POST'])
@login_required
def add_comment(slug: str):
    post    = Post.query.filter_by(slug=slug).first_or_404()
    data    = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'ok': False, 'error': 'Yorum boş olamaz.'}), 422
    if len(content) > 500:
        return jsonify({'ok': False, 'error': 'Yorum en fazla 500 karakter olabilir.'}), 422

    comment = PostComment(post_id=post.id, user_id=current_user.id, content=content)
    db.session.add(comment)
    db.session.commit()

    # Bildirim: gönderi sahibine yorum bildirimi
    if post.user_id != current_user.id:
        create_notification(
            user_id    = post.user_id,
            actor_id   = current_user.id,
            notif_type = Notification.TYPE_COMMENT,
            post_id    = post.id,
        )

    # Bildirim: yorumdaki @mention'lar
    notify_mentions(content, actor_id=current_user.id, post_id=post.id)

    html = render_template('_feed_comment.html', comment=comment)
    return jsonify({
        'ok':            True,
        'comment_id':    comment.id,
        'comment_count': post.comment_count,
        'html':          html,
    })


# ════════════════════════════════════════════════════════════════
#   TAKİP TOGGLE  — takip sonrası anlık post enjeksiyonu
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def toggle_follow(user_id: int):
    if user_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendinizi takip edemezsiniz.'}), 422

    target   = User.query.get_or_404(user_id)
    existing = Follow.query.filter_by(
        follower_id=current_user.id, following_id=user_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({
            'ok':             True,
            'following':      False,
            'follower_count': target.follower_count(),
            'posts_html':     None,
        })

    # Yeni takip — son 5 gönderisini akışa enjekte et
    db.session.add(Follow(follower_id=current_user.id, following_id=user_id))
    db.session.commit()

    # Bildirim: takip edilen kişiye
    create_notification(
        user_id    = user_id,
        actor_id   = current_user.id,
        notif_type = Notification.TYPE_FOLLOW,
    )

    recent_posts = (
        Post.query
        .filter_by(user_id=user_id, source='social')   # Takip preview'ında yalnızca sosyal gönderiler
        .order_by(Post.created_at.desc())
        .limit(5)
        .all()
    )

    posts_html = ''.join(
        render_template('_feed_post.html', post=p, viewer=current_user)
        for p in recent_posts
    )

    return jsonify({
        'ok':             True,
        'following':      True,
        'follower_count': target.follower_count(),
        'posts_html':     posts_html,
        'post_count':     len(recent_posts),
    })


# ════════════════════════════════════════════════════════════════
#   YENİ GÖNDERİLERİ YÜKLE  (banner'a tıklayınca)
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/load-new')
@login_required
def load_new():
    """?since=<id> → en yeni gönderileri HTML olarak döner."""
    since_id      = request.args.get('since', 0, type=int)
    following_ids = [f.following_id for f in current_user.following.all()]

    own_data     = OnboardingData.query.filter_by(user_id=current_user.id).first()
    own_category = own_data.profession_category if own_data else None
    same_cat_ids = []
    if own_category:
        rows = (
            OnboardingData.query
            .filter(
                OnboardingData.profession_category == own_category,
                OnboardingData.user_id != current_user.id,
            )
            .with_entities(OnboardingData.user_id)
            .all()
        )
        same_cat_ids = [r.user_id for r in rows]

    relevant_ids = list(set(following_ids + same_cat_ids))
    if not relevant_ids:
        return jsonify({'html': '', 'count': 0, 'latest_id': since_id})

    posts = (
        Post.query
        .options(joinedload(Post.author))
        .filter(
            Post.id > since_id,
            Post.user_id.in_(relevant_ids),
            Post.user_id != current_user.id,
            Post.source == 'social',   # Site güncellemeleri yeni içerik olarak yüklenmez
        )
        .order_by(Post.created_at.desc())
        .limit(POLL_LIMIT)
        .all()
    )

    html      = ''.join(render_template('_feed_post.html', post=p, viewer=current_user) for p in posts)
    latest_id = posts[0].id if posts else since_id

    return jsonify({'html': html, 'count': len(posts), 'latest_id': latest_id})


# ════════════════════════════════════════════════════════════════
#   @MENTION ARAMA  — otomatik tamamlama için
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/mention-search')
@login_required
def mention_search():
    """
    GET /feed/mention-search?q=<sorgu>
    Platforma kayıtlı kullanıcıları ada göre arar (max 8 sonuç).
    Yanıt: { users: [{ id, full_name, job_title, avatar }] }
    """
    q     = request.args.get('q', '').strip()[:50]
    limit = 8

    base_q = (
        User.query
        .filter(User.id != current_user.id)
    )

    if q:
        like_q = f'%{q}%'
        base_q = base_q.filter(
            or_(
                User.full_name.ilike(like_q),
                User.email.ilike(like_q),
            )
        )

    users = base_q.order_by(User.full_name.asc()).limit(limit).all()

    result = []
    for u in users:
        od      = u.onboarding
        site    = u.site
        avatar_char = (u.full_name or u.email or '?')[0].upper()
        result.append({
            'id':        u.id,
            'full_name': u.full_name or u.email.split('@')[0],
            'job_title': od.job_title if od else None,
            'avatar':    avatar_char,
            'avatar_url': site.avatar_file if site else None,
        })

    return jsonify({'users': result})


# ════════════════════════════════════════════════════════════════
#   YARDIMCI FONKSİYONLAR
# ════════════════════════════════════════════════════════════════

def _build_feed(viewer, page: int = 1, per_page: int = 12, mode: str = 'fresh'):
    """
    mode='fresh'  → görülmemiş gönderiler öncelikli, görülmüşler sonda
    mode='all'    → tüm gönderiler, görülmüş/görülmemiş ayrımı yok

    Sıralama: Takip edilenler → Aynı kategori → Diğerleri (her grupta tarih DESC)
    """
    following_ids = [f.following_id for f in viewer.following.all()]

    own_data     = OnboardingData.query.filter_by(user_id=viewer.id).first()
    own_category = own_data.profession_category if own_data else None

    same_cat_ids = []
    if own_category:
        rows = (
            OnboardingData.query
            .filter(
                OnboardingData.profession_category == own_category,
                OnboardingData.user_id != viewer.id,
                not_(OnboardingData.user_id.in_(following_ids)) if following_ids else True,
            )
            .with_entities(OnboardingData.user_id)
            .all()
        )
        same_cat_ids = [r.user_id for r in rows]

    # Görülmüş gönderi ID'leri (fresh mode'da hariç tutulur)
    seen_ids = []
    if mode == 'fresh':
        seen_rows = (
            PostView.query
            .filter_by(user_id=viewer.id)
            .with_entities(PostView.post_id)
            .all()
        )
        seen_ids = [r.post_id for r in seen_rows]

    # Öncelik CASE ifadesi
    if following_ids and same_cat_ids:
        priority = case(
            (Post.user_id.in_(following_ids), 1),
            (Post.user_id.in_(same_cat_ids), 2),
            else_=3,
        )
    elif following_ids:
        priority = case(
            (Post.user_id.in_(following_ids), 1),
            else_=3,
        )
    elif same_cat_ids:
        priority = case(
            (Post.user_id.in_(same_cat_ids), 2),
            else_=3,
        )
    else:
        from sqlalchemy import literal
        priority = literal(3)

    # Fresh mode: görülmüş gönderiler en sona (öncelik 10)
    if mode == 'fresh' and seen_ids:
        seen_penalty = case(
            (Post.id.in_(seen_ids), 10),
            else_=0,
        )
        order_priority = (priority + seen_penalty).asc()
    else:
        order_priority = priority.asc()

    # Yankı ağırlığı: çok Yankı almış gönderiler aynı öncelik katmanında öne geçer.
    # Subquery ile gönderi başına Yankı sayısını hesapla.
    yanka_sub = (
        db.session.query(
            PostYanka.post_id,
            func.count(PostYanka.id).label('yanka_cnt'),
        )
        .group_by(PostYanka.post_id)
        .subquery()
    )

    q = (
        Post.query
        .options(joinedload(Post.author))
        .outerjoin(yanka_sub, Post.id == yanka_sub.c.post_id)
        .filter(
            Post.user_id != viewer.id,
            Post.source == 'social',   # Site dashboard güncellemeleri akışa karışmaz
        )
        .order_by(
            order_priority,
            func.coalesce(yanka_sub.c.yanka_cnt, 0).desc(),   # Yankı ağırlığı
            Post.created_at.desc(),
        )
    )

    return q.paginate(page=page, per_page=per_page, error_out=False)


def _get_suggestions(viewer, limit: int = 5):
    """Aynı kategoriden, takip edilmeyen, profili yayında kullanıcılar."""
    own_data     = OnboardingData.query.filter_by(user_id=viewer.id).first()
    own_category = own_data.profession_category if own_data else None
    following_ids = [f.following_id for f in viewer.following.all()]

    q = (
        User.query
        .join(OnboardingData, OnboardingData.user_id == User.id)
        .join(Site, Site.user_id == User.id)
        .filter(User.id != viewer.id, Site.is_published == True)
    )

    if following_ids:
        q = q.filter(not_(User.id.in_(following_ids)))

    if own_category:
        same = q.filter(
            OnboardingData.profession_category == own_category
        ).limit(limit).all()
        if len(same) < limit:
            others = q.filter(
                or_(
                    OnboardingData.profession_category != own_category,
                    OnboardingData.profession_category == None,
                )
            ).limit(limit - len(same)).all()
            return same + others
        return same

    return q.limit(limit).all()


def _get_trending_posts(limit: int = 3):
    """Bu haftanın en çok etkileşim (yanka + onay) alan gönderilerini döndür."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    like_sub = (
        db.session.query(
            PostLike.post_id,
            func.count(PostLike.id).label('like_cnt'),
        )
        .group_by(PostLike.post_id)
        .subquery()
    )

    yanka_sub = (
        db.session.query(
            PostYanka.post_id,
            func.count(PostYanka.id).label('yanka_cnt'),
        )
        .group_by(PostYanka.post_id)
        .subquery()
    )

    lc         = func.coalesce(like_sub.c.like_cnt,   0)
    yc         = func.coalesce(yanka_sub.c.yanka_cnt, 0)
    score_expr = (lc + yc)

    rows = (
        db.session.query(Post, score_expr)
        .outerjoin(like_sub,  Post.id == like_sub.c.post_id)
        .outerjoin(yanka_sub, Post.id == yanka_sub.c.post_id)
        .options(joinedload(Post.author))
        .filter(Post.created_at >= week_ago)
        .order_by(score_expr.desc())
        .limit(limit)
        .all()
    )

    return [{'post': p, 'score': int(s)} for p, s in rows]


# ════════════════════════════════════════════════════════════════
#   SOCIAL PROFİL SAYFASI  (/feed/u/<user_id>)
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/u/<int:user_id>')
@login_required
def social_profile(user_id: int):
    """Bir kullanıcının Social profil sayfası."""
    target      = User.query.get_or_404(user_id)
    target_od   = OnboardingData.query.filter_by(user_id=user_id).first()
    target_site = target.site
    extras      = UserProfileExtras.query.filter_by(user_id=user_id).first()

    posts = (
        Post.query
        .filter_by(user_id=user_id, source='social')   # Profil sayfasında yalnızca sosyal gönderiler
        .order_by(Post.is_pinned.desc(), Post.created_at.desc())
        .limit(50)
        .all()
    )

    post_count     = Post.query.filter_by(user_id=user_id, source='social').count()
    follower_count = target.follower_count()
    follow_count   = target.follow_count()
    is_own         = (current_user.id == user_id)
    is_following   = current_user.is_following(target) if not is_own else False

    cat_slug  = target_od.profession_category if target_od else None
    cat_info  = CAT_MAP.get(cat_slug) if cat_slug else None
    pkg_info  = PKG_MAP.get(target.package, ('P2', 'Standart'))

    mind_map        = MindMap.query.filter_by(user_id=user_id).first()
    yanka_remaining = _daily_yanka_remaining(current_user.id)

    return render_template(
        'feed_profile.html',
        target          = target,
        target_od       = target_od,
        target_site     = target_site,
        extras          = extras,
        posts           = posts,
        post_count      = post_count,
        follower_count  = follower_count,
        follow_count    = follow_count,
        is_own          = is_own,
        is_following    = is_following,
        cat_info        = cat_info,
        pkg_info        = pkg_info,
        viewer          = current_user,
        mind_map        = mind_map,
        yanka_remaining = yanka_remaining,
    )


# ════════════════════════════════════════════════════════════════
#   SOCIAL PROFİL DÜZENLE  (AJAX POST)
# ════════════════════════════════════════════════════════════════

@feed_bp.route('/u/edit', methods=['POST'])
@login_required
def edit_social_profile():
    """
    Kullanıcının kendi Social profilini hızlıca düzenler.
    Body (JSON): full_name, bio, status_text, status_emoji
    """
    data = request.get_json(silent=True) or {}

    # full_name
    new_name = (data.get('full_name') or '').strip()[:120]
    if new_name:
        current_user.full_name = new_name

    # bio (OnboardingData)
    od = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if od and 'bio' in data:
        od.bio = (data['bio'] or '').strip()[:1000]

    # status (UserProfileExtras)
    extras = UserProfileExtras.query.filter_by(user_id=current_user.id).first()
    if not extras:
        extras = UserProfileExtras(user_id=current_user.id)
        db.session.add(extras)

    if 'status_text' in data:
        extras.status_text  = (data['status_text']  or '').strip()[:100]
    if 'status_emoji' in data:
        extras.status_emoji = (data['status_emoji'] or '').strip()[:10]

    db.session.commit()
    return jsonify({
        'ok':        True,
        'full_name': current_user.full_name,
    })


# ════════════════════════════════════════════════════════════════
#   SOCIAL PROFİL — AVATAR YÜKLEME  (AJAX multipart/form-data)
# ════════════════════════════════════════════════════════════════

_ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
_MAX_IMG_MB  = 8


def _feed_save_upload(file, user_id: int, name_stem: str):
    """Dosyayı static/uploads/{user_id}/{name_stem}.{ext} konumuna kaydeder."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in _ALLOWED_IMG:
        return None
    upload_folder = current_app.config['UPLOAD_FOLDER']
    user_dir = os.path.join(upload_folder, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    for f in os.listdir(user_dir):
        if f.startswith(f"{name_stem}."):
            try:
                os.remove(os.path.join(user_dir, f))
            except OSError:
                pass
    filename = f"{name_stem}.{ext}"
    file.save(os.path.join(user_dir, filename))
    return f"/uploads/{user_id}/{filename}"


@feed_bp.route('/u/upload-avatar', methods=['POST'])
@login_required
def upload_social_avatar():
    """Social profilden profil fotoğrafı yükleme."""
    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site:
        return jsonify({'ok': False, 'error': 'Site bulunamadı.'}), 400
    file = request.files.get('avatar')
    if not file:
        return jsonify({'ok': False, 'error': 'Dosya bulunamadı.'}), 422
    file.seek(0, 2)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > _MAX_IMG_MB:
        return jsonify({'ok': False, 'error': f'Maksimum {_MAX_IMG_MB} MB yükleyebilirsiniz.'}), 422
    url = _feed_save_upload(file, current_user.id, 'avatar')
    if not url:
        return jsonify({'ok': False, 'error': 'Geçersiz format. PNG, JPG veya WebP yükleyin.'}), 422
    site.avatar_file = url
    db.session.commit()
    return jsonify({'ok': True, 'url': url})


@feed_bp.route('/u/upload-cover', methods=['POST'])
@login_required
def upload_social_cover():
    """Social profilden kapak/banner görseli yükleme."""
    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site:
        return jsonify({'ok': False, 'error': 'Site bulunamadı.'}), 400
    file = request.files.get('cover')
    if not file:
        return jsonify({'ok': False, 'error': 'Dosya bulunamadı.'}), 422
    file.seek(0, 2)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > _MAX_IMG_MB:
        return jsonify({'ok': False, 'error': f'Maksimum {_MAX_IMG_MB} MB yükleyebilirsiniz.'}), 422
    url = _feed_save_upload(file, current_user.id, 'cover')
    if not url:
        return jsonify({'ok': False, 'error': 'Geçersiz format. PNG, JPG veya WebP yükleyin.'}), 422
    site.cover_file = url
    db.session.commit()
    return jsonify({'ok': True, 'url': url})
