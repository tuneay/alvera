"""
Alvera — Zihin Haritası Blueprint
───────────────────────────────────
Kullanıcının tüm platform verisinden AI ile üretilen kişisel Zihin Haritası.

Endpoints:
  POST /mindmap/generate          → AI üret / yeniden üret → {ok, data, version}
  GET  /mindmap/data/<user_id>    → JSON harita verisi (public, widget için)
  GET  /mindmap/<user_id>         → Tam sayfa görünüm
  GET  /mindmap/                  → Kendi harita sayfası (login gerekli)
"""
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import (
    AuraResult, CareerEntry, DMConversation, DMMessage,
    Follow, MindMap, OnboardingData, Post, Site, User,
    UserProfileExtras
)
from services.ai_service import generate_mind_map, generate_aura_analysis

mindmap_bp = Blueprint('mindmap', __name__, url_prefix='/mindmap')


# ════════════════════════════════════════════════════════════════
#   YARDIMCI — Kullanıcı verisini topla
# ════════════════════════════════════════════════════════════════

def _collect_profile(user: User) -> dict:
    """Kullanıcıya ait tüm profil verisini tek bir dict'e toplar."""
    profile = {}

    profile['full_name'] = user.full_name or ''

    ob: OnboardingData | None = user.onboarding
    if ob:
        profile.update({
            'profession_category': ob.profession_category or '',
            'job_title':           ob.job_title or '',
            'company':             ob.company or '',
            'bio':                 ob.bio or '',
            'skills':              ob.skills or '',
            'vibe':                ob.vibe or '',
            'target_audience':     ob.target_audience or '',
            'achievement':         ob.achievement or '',
            'differentiator':      ob.differentiator or '',
            'brand_name':          ob.brand_name or '',
            'brand_type':          ob.brand_type or '',
            'brand_tagline':       ob.brand_tagline or '',
            'services_raw':        ob.services_raw or '',
        })

    site: Site | None = user.site
    if site:
        profile.update({
            'headline': site.headline or '',
            'tagline':  site.tagline or '',
            'bio_text': site.bio_text or '',
        })

    extras: UserProfileExtras | None = UserProfileExtras.query.filter_by(
        user_id=user.id
    ).first()
    if extras:
        profile.update({
            'status_text':   extras.status_text or '',
            'work_type':     extras.work_type or '',
            'work_budget':   getattr(extras, 'work_budget', '') or '',
        })

    return profile


def _collect_posts(user: User) -> list[str]:
    """Son 50 gönderinin metin içeriklerini döner."""
    posts = (
        Post.query
        .filter_by(user_id=user.id)
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )
    return [p.content for p in posts if p.content and p.content.strip()]


# ════════════════════════════════════════════════════════════════
#   POST /mindmap/generate
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    """
    Mevcut kullanıcının Zihin Haritasını AI ile üretir.
    Daha önce oluşturulmuşsa üzerine yazar (version artar).
    """
    try:
        profile = _collect_profile(current_user)
        posts   = _collect_posts(current_user)

        map_data = generate_mind_map(profile, posts)

        # Doğrulama — minimum düğüm sayısı
        if not map_data.get('nodes') or len(map_data['nodes']) < 5:
            return jsonify({'ok': False, 'error': 'AI yeterli düğüm üretemedi, tekrar deneyin.'}), 422

        mind_map: MindMap | None = MindMap.query.filter_by(
            user_id=current_user.id
        ).first()

        if mind_map is None:
            mind_map = MindMap(user_id=current_user.id, version=1)
            db.session.add(mind_map)
        else:
            mind_map.version += 1
            mind_map.generated_at = datetime.now(timezone.utc)

        mind_map.data = map_data
        db.session.commit()

        return jsonify({
            'ok':      True,
            'data':    map_data,
            'version': mind_map.version,
        })

    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ════════════════════════════════════════════════════════════════
#   GET /mindmap/data/<user_id>
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/data/<int:user_id>')
def get_data(user_id: int):
    """
    Belirtilen kullanıcının harita verisini JSON olarak döner.
    Widget ve landing page embed için kullanılır.
    """
    mind_map: MindMap | None = MindMap.query.filter_by(user_id=user_id).first()
    if not mind_map or not mind_map.map_data:
        return jsonify({'ok': False, 'error': 'Henüz harita oluşturulmamış.'}), 404

    return jsonify({
        'ok':      True,
        'data':    mind_map.data,
        'version': mind_map.version,
        'generated_at': mind_map.generated_at.isoformat() if mind_map.generated_at else None,
    })


# ════════════════════════════════════════════════════════════════
#   GET /mindmap/  (kendi haritam)
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/')
@login_required
def my_map():
    """Giriş yapmış kullanıcının kendi Zihin Haritası sayfası."""
    mind_map: MindMap | None = MindMap.query.filter_by(
        user_id=current_user.id
    ).first()
    return render_template(
        'mindmap.html',
        target=current_user,
        mind_map=mind_map,
        is_own=True,
    )


# ════════════════════════════════════════════════════════════════
#   GET /mindmap/<user_id>
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/<int:user_id>')
def view_map(user_id: int):
    """Başka bir kullanıcının Zihin Haritası sayfası (public)."""
    user = User.query.get_or_404(user_id)
    mind_map: MindMap | None = MindMap.query.filter_by(user_id=user_id).first()

    is_own = current_user.is_authenticated and current_user.id == user_id

    # Aura butonu: giriş yapmış + başkasının sayfasındaysa göster.
    # Harita varlık kontrolü backend API'de yapılıyor; frontend sadece butonu gösterir.
    show_aura_btn = (
        not is_own
        and current_user.is_authenticated
        and bool(mind_map and mind_map.map_data)
    )

    return render_template(
        'mindmap.html',
        target=user,
        mind_map=mind_map,
        is_own=is_own,
        show_aura_btn=show_aura_btn,
    )


# ════════════════════════════════════════════════════════════════
#   POST /mindmap/aura   — Aura Analizi
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
#   YARDIMCI — Canonical pair key
# ════════════════════════════════════════════════════════════════

def _aura_pair(uid_a: int, uid_b: int) -> tuple[int, int]:
    """Daima (küçük_id, büyük_id) döner — DB unique constraint ile uyumlu."""
    return (uid_a, uid_b) if uid_a < uid_b else (uid_b, uid_a)


# ════════════════════════════════════════════════════════════════
#   GET /mindmap/aura/cached/<target_id>
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/aura/cached/<int:target_id>')
@login_required
def aura_cached(target_id: int):
    """
    Bu çift için daha önce üretilmiş Aura Analizi var mı?
    Varsa { ok:true, analysis, cached:true } döner.
    Yoksa { ok:false } döner (404 değil — sadece yok işareti).
    """
    a, b = _aura_pair(current_user.id, target_id)
    rec: AuraResult | None = AuraResult.query.filter_by(
        user_a_id=a, user_b_id=b
    ).first()

    if not rec:
        return jsonify({'ok': False, 'cached': False})

    return jsonify({'ok': True, 'cached': True, 'analysis': rec.data})


# ════════════════════════════════════════════════════════════════
#   POST /mindmap/aura
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/aura', methods=['POST'])
@login_required
def aura():
    """
    İki kullanıcının zihin haritasını + profilini karşılaştırarak Aura Analizi döner.
    Sonuç cache'e kaydedilir; aynı çift için AI tekrar çağrılmaz.

    Body: { "target_user_id": <int> }
    """
    data      = request.get_json(silent=True) or {}
    target_id = data.get('target_user_id')

    if not target_id:
        return jsonify({'ok': False, 'error': 'target_user_id gerekli.'}), 400
    if target_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendinizle aura analizi yapamazsınız.'}), 400

    target_user = User.query.get(target_id)
    if not target_user:
        return jsonify({'ok': False, 'error': 'Kullanıcı bulunamadı.'}), 404

    # ── Cache kontrolü ──────────────────────────────────────────
    a, b = _aura_pair(current_user.id, target_id)
    cached_rec: AuraResult | None = AuraResult.query.filter_by(
        user_a_id=a, user_b_id=b
    ).first()
    if cached_rec:
        return jsonify({'ok': True, 'analysis': cached_rec.data, 'cached': True})

    # ── Her iki haritayı doğrula ─────────────────────────────────
    map_a: MindMap | None = MindMap.query.filter_by(user_id=current_user.id).first()
    map_b: MindMap | None = MindMap.query.filter_by(user_id=target_id).first()

    if not map_a or not map_a.map_data:
        return jsonify({'ok': False, 'error': 'Önce kendi zihin haritanı oluşturman gerekiyor.'}), 422
    if not map_b or not map_b.map_data:
        return jsonify({'ok': False, 'error': 'Bu kullanıcının henüz zihin haritası yok.'}), 422

    try:
        profile_a = _collect_profile(current_user)
        profile_b = _collect_profile(target_user)

        # Ortak takip edilenler
        follows_a = {f.following_id for f in Follow.query.filter_by(
            follower_id=current_user.id).all()}
        follows_b = {f.following_id for f in Follow.query.filter_by(
            follower_id=target_id).all()}
        common_ids = follows_a & follows_b

        common_follows_data = []
        if common_ids:
            for u in User.query.filter(User.id.in_(common_ids)).limit(20).all():
                od = OnboardingData.query.filter_by(user_id=u.id).first()
                common_follows_data.append({
                    'name':     u.full_name or '',
                    'title':    od.job_title if od else '',
                    'category': od.profession_category if od else '',
                })

        result = generate_aura_analysis(
            profile_a=profile_a,
            map_a=map_a.data,
            profile_b=profile_b,
            map_b=map_b.data,
            common_follows=common_follows_data or None,
        )
        result['common_follows_count'] = len(common_ids)

        # ── Cache'e kaydet ───────────────────────────────────────
        rec = AuraResult(user_a_id=a, user_b_id=b)
        rec.data = result
        db.session.add(rec)
        db.session.commit()

        return jsonify({'ok': True, 'analysis': result, 'cached': False})

    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ════════════════════════════════════════════════════════════════
#   POST /mindmap/aura/send-dm  — Aura sonucunu DM olarak gönder
# ════════════════════════════════════════════════════════════════

@mindmap_bp.route('/aura/send-dm', methods=['POST'])
@login_required
def aura_send_dm():
    """
    Mevcut Aura analizini DM olarak karşı kullanıcıya gönderir.
    Body: { "target_user_id": <int> }
    Hedefin mesajlarına özel bir 'aura' tipi kart düşer.
    """
    import json as _json

    data      = request.get_json(silent=True) or {}
    target_id = data.get('target_user_id')

    if not target_id:
        return jsonify({'ok': False, 'error': 'target_user_id gerekli.'}), 400
    if target_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendinize gönderemezsiniz.'}), 400

    target_user = User.query.get(target_id)
    if not target_user:
        return jsonify({'ok': False, 'error': 'Kullanıcı bulunamadı.'}), 404

    # Cache'de analiz var mı?
    a, b = _aura_pair(current_user.id, target_id)
    cached_rec: AuraResult | None = AuraResult.query.filter_by(
        user_a_id=a, user_b_id=b
    ).first()
    if not cached_rec:
        return jsonify({'ok': False, 'error': 'Önce Aura analizi yapman gerekiyor.'}), 422

    result = cached_rec.data
    score  = result.get('aura_score', '?')
    label  = result.get('aura_label', '')
    sender_name = current_user.full_name or current_user.email.split('@')[0]

    # DM mesaj içeriği — karşı taraf için okunabilir metin
    content = (
        f'✦ {sender_name} sizinle Aura analizi yaptı!\n'
        f'Aura Skoru: {score} — {label}\n'
        f'Detayları görmek için butona tıklayın.'
    )

    # meta_json: frontend'in raporu göstermesi için gerekli özet
    meta = {
        'aura_score': score,
        'aura_label': label,
        'from_user_id': current_user.id,
        'from_user_name': sender_name,
        'target_mindmap_url': f'/mindmap/{current_user.id}',
    }

    # Konuşmayı bul veya oluştur
    u1, u2 = (current_user.id, target_id) if current_user.id < target_id \
             else (target_id, current_user.id)
    conv = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()
    if not conv:
        conv = DMConversation(user1_id=u1, user2_id=u2)
        db.session.add(conv)
        db.session.flush()

    msg = DMMessage(
        conversation_id = conv.id,
        sender_id       = current_user.id,
        content         = content,
        msg_type        = 'aura',
        meta_json       = _json.dumps(meta, ensure_ascii=False),
        is_read         = False,
    )
    db.session.add(msg)
    conv.last_message_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'ok': True, 'conv_id': conv.id})
