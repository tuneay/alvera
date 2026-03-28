"""
Alvera Direct — Direkt Mesajlaşma Blueprint
Konuşmalar · Mesaj gönderme · Okundu takibi · Arama · Düzenleme · Silme · Tepkiler · Kod · Dosya paylaşımı
"""
import json
import os
import uuid
import mimetypes
from datetime import datetime, timezone, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func
from werkzeug.utils import secure_filename

from extensions import db
from models import DMConversation, DMMessage, DMReaction, OnboardingData, Site, User

dm_bp = Blueprint('dm', __name__, url_prefix='/dm')

MSG_MAX_LEN = 2000

# ── Dosya yükleme sabitleri ──────────────────────────────────────
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_FILE_EXT  = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                     'txt', 'md', 'csv', 'zip', 'rar', 'mp4', 'mp3'}
MAX_FILE_BYTES    = 30 * 1024 * 1024   # 30 MB


def _allowed_dm_file(filename: str):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext in ALLOWED_IMAGE_EXT:
        return ext, 'image'
    if ext in ALLOWED_FILE_EXT:
        return ext, 'file'
    return None, None


def _format_size(n: int) -> str:
    """Byte sayısını okunabilir stringe dönüştür."""
    if n < 1024:        return f'{n} B'
    if n < 1024**2:     return f'{n/1024:.1f} KB'
    return f'{n/1024**2:.1f} MB'


# ════════════════════════════════════════════════════════════════
#   YARDIMCI: Konuşma bul veya oluştur
# ════════════════════════════════════════════════════════════════

def _get_or_create_conversation(user_a_id: int, user_b_id: int) -> DMConversation:
    """
    İki kullanıcı arasındaki konuşmayı döner; yoksa oluşturur.
    user1_id < user2_id kısıtıyla tutarlı UniqueConstraint sağlanır.
    """
    u1, u2 = (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)
    conv = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()
    if not conv:
        conv = DMConversation(user1_id=u1, user2_id=u2)
        db.session.add(conv)
        db.session.flush()   # ID almak için flush, commit yok
    return conv


def _inbox_conversations(user_id: int):
    """Kullanıcının tüm konuşmalarını son mesaj tarihine göre sıralar."""
    return (
        DMConversation.query
        .filter(
            or_(
                DMConversation.user1_id == user_id,
                DMConversation.user2_id == user_id,
            )
        )
        .order_by(DMConversation.last_message_at.desc())
        .all()
    )


def _total_unread(user_id: int) -> int:
    """Kullanıcının tüm konuşmalarındaki toplam okunmamış mesaj sayısı."""
    return (
        DMMessage.query
        .join(DMConversation, DMMessage.conversation_id == DMConversation.id)
        .filter(
            or_(
                DMConversation.user1_id == user_id,
                DMConversation.user2_id == user_id,
            ),
            DMMessage.sender_id != user_id,
            DMMessage.is_read == False,
        )
        .count()
    )


def _user_meta(user: User) -> dict:
    """Template'e geçirilecek kullanıcı özeti."""
    od   = user.onboarding
    site = user.site
    return {
        'id':        user.id,
        'full_name': user.full_name or user.email.split('@')[0],
        'job_title': od.job_title if od else None,
        'avatar':    (user.full_name or user.email or '?')[0].upper(),
        'avatar_url': site.avatar_file if site else None,
    }


# ════════════════════════════════════════════════════════════════
#   INBOX — /dm/  &  /dm/<user_id>
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/')
@login_required
def inbox():
    """DM inbox — tüm konuşmalar, açık konuşma yok."""
    conversations = _inbox_conversations(current_user.id)
    total_unread  = _total_unread(current_user.id)

    return render_template(
        'dm.html',
        conversations = conversations,
        active_conv   = None,
        messages      = [],
        other_user    = None,
        total_unread  = total_unread,
    )


@dm_bp.route('/<int:user_id>')
@login_required
def open_conversation(user_id: int):
    """Belirli bir kullanıcıyla konuşmayı aç (veya yeni konuşma başlat)."""
    if user_id == current_user.id:
        return inbox()

    other = User.query.get_or_404(user_id)

    # Konuşmayı bul ya da hazırla (henüz kaydetme)
    u1, u2 = (current_user.id, user_id) if current_user.id < user_id else (user_id, current_user.id)
    conv = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()

    messages = []
    if conv:
        messages = conv.messages.order_by(DMMessage.created_at.asc()).all()
        # Bu konuşmadaki okunmamış mesajları okundu işaretle
        (
            DMMessage.query
            .filter_by(conversation_id=conv.id, is_read=False)
            .filter(DMMessage.sender_id != current_user.id)
            .update({'is_read': True})
        )
        db.session.commit()

    conversations = _inbox_conversations(current_user.id)
    total_unread  = _total_unread(current_user.id)

    return render_template(
        'dm.html',
        conversations = conversations,
        active_conv   = conv,
        messages      = messages,
        other_user    = other,
        total_unread  = total_unread,
    )


# ════════════════════════════════════════════════════════════════
#   MESAJ GÖNDER
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/<int:user_id>/send', methods=['POST'])
@login_required
def send_message(user_id: int):
    """
    POST /dm/<user_id>/send
    Body (JSON): { content: str }
    Yanıt: { ok, message_id, html, conv_id, last_message_at }
    """
    if user_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendinize mesaj gönderemezsiniz.'}), 422

    User.query.get_or_404(user_id)   # hedef var mı?

    data      = request.get_json(silent=True) or {}
    content   = (data.get('content') or '').strip()
    msg_type  = data.get('msg_type', 'text')   # 'text' | 'code'
    code_lang = (data.get('code_language') or '').strip()[:30] or None

    if msg_type not in ('text', 'code'):
        msg_type = 'text'

    if not content:
        return jsonify({'ok': False, 'error': 'Mesaj boş olamaz.'}), 422
    if len(content) > MSG_MAX_LEN:
        return jsonify({'ok': False, 'error': f'Mesaj en fazla {MSG_MAX_LEN} karakter olabilir.'}), 422

    conv = _get_or_create_conversation(current_user.id, user_id)

    msg = DMMessage(
        conversation_id = conv.id,
        sender_id       = current_user.id,
        content         = content,
        msg_type        = msg_type,
        code_language   = code_lang if msg_type == 'code' else None,
        is_read         = False,
    )
    db.session.add(msg)

    # Konuşma zaman damgasını güncelle (sıralama için)
    conv.last_message_at = datetime.now(timezone.utc)
    db.session.commit()

    html = render_template('_dm_message.html', msg=msg, current_user=current_user)

    return jsonify({
        'ok':             True,
        'message_id':     msg.id,
        'html':           html,
        'conv_id':        conv.id,
        'last_message_at': conv.last_message_at.isoformat(),
    })


# ════════════════════════════════════════════════════════════════
#   YENİ MESAJ POLLING
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/<int:user_id>/poll')
@login_required
def poll_messages(user_id: int):
    """
    GET /dm/<user_id>/poll?since=<message_id>
    Konuşmadaki yeni mesajları döner.
    Yanıt: { messages_html, last_id, unread_total, read_ids }
    read_ids: Gönderenin mesajlarından okundu olarak işaretlenenler
              (gönderen tarafında ✓✓ güncelleme için)
    """
    since_id = request.args.get('since', 0, type=int)

    u1, u2 = (current_user.id, user_id) if current_user.id < user_id else (user_id, current_user.id)
    conv   = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()

    if not conv:
        resp = jsonify({'messages_html': '', 'last_id': since_id, 'unread_total': 0, 'read_ids': []})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    new_msgs = (
        conv.messages
        .filter(DMMessage.id > since_id)
        .order_by(DMMessage.created_at.asc())
        .all()
    )

    # Alınan yeni mesajları okundu işaretle
    changed = False
    for m in new_msgs:
        if m.sender_id != current_user.id and not m.is_read:
            m.is_read = True
            changed = True
    if changed:
        db.session.commit()

    # Gönderenin önceki mesajlarından hangisi okundu oldu?
    # (Polling eden kullanıcının gönderdiği ve az önce okundu işaretlenen mesajlar)
    newly_read_ids = (
        DMMessage.query
        .filter(
            DMMessage.conversation_id == conv.id,
            DMMessage.sender_id == current_user.id,
            DMMessage.is_read == True,
            DMMessage.id <= since_id,   # Sadece zaten bilinen mesajlar
        )
        .with_entities(DMMessage.id)
        .all()
    )
    read_ids = [r.id for r in newly_read_ids]

    html    = ''.join(render_template('_dm_message.html', msg=m, current_user=current_user) for m in new_msgs)
    last_id = new_msgs[-1].id if new_msgs else since_id
    unread  = _total_unread(current_user.id)

    resp = jsonify({
        'messages_html': html,
        'last_id':       last_id,
        'unread_total':  unread,
        'read_ids':      read_ids,
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ════════════════════════════════════════════════════════════════
#   NAV BADGE — Toplam okunmamış sayısı
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/unread-count')
@login_required
def unread_count():
    """
    GET /dm/unread-count
    Yanıt: { count }  — nav badge için
    """
    resp = jsonify({'count': _total_unread(current_user.id)})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ════════════════════════════════════════════════════════════════
#   KONUŞMA SİL (opsiyonel — kendi tarafından gizleme)
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/conv/<int:conv_id>/delete', methods=['DELETE'])
@login_required
def delete_conversation(conv_id: int):
    """
    Sadece konuşmanın katılımcısı silebilir.
    Tüm mesajlar cascade ile silinir.
    """
    conv = DMConversation.query.get_or_404(conv_id)
    if conv.user1_id != current_user.id and conv.user2_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Yetkisiz.'}), 403

    db.session.delete(conv)
    db.session.commit()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════
#   MESAJ SİL
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/msg/<int:msg_id>', methods=['DELETE'])
@login_required
def delete_message(msg_id: int):
    """
    DELETE /dm/msg/<id>
    Sadece mesajın gönderisinde silme yapılabilir (soft-delete).
    """
    msg = DMMessage.query.get_or_404(msg_id)
    if msg.sender_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Yetkisiz.'}), 403

    msg.is_deleted = True
    msg.content    = ''   # İçeriği temizle
    db.session.commit()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════
#   MESAJ DÜZENLE
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/msg/<int:msg_id>', methods=['PATCH'])
@login_required
def edit_message(msg_id: int):
    """
    PATCH /dm/msg/<id>
    Body (JSON): { content: str }
    Sadece gönderici, sadece 5 dakika içinde düzenleyebilir.
    """
    msg = DMMessage.query.get_or_404(msg_id)
    if msg.sender_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Yetkisiz.'}), 403
    if msg.is_deleted:
        return jsonify({'ok': False, 'error': 'Silinmiş mesaj düzenlenemez.'}), 422

    # 5 dakika kontrolü
    age = datetime.now(timezone.utc) - msg.created_at.replace(tzinfo=timezone.utc)
    if age > timedelta(minutes=5):
        return jsonify({'ok': False, 'error': 'Mesaj düzenleme süresi (5 dk) doldu.'}), 422

    data    = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'Mesaj boş olamaz.'}), 422
    if len(content) > MSG_MAX_LEN:
        return jsonify({'ok': False, 'error': f'En fazla {MSG_MAX_LEN} karakter.'}), 422

    msg.content   = content
    msg.edited_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'ok': True, 'content': msg.content})


# ════════════════════════════════════════════════════════════════
#   MESAJ TEPKİSİ (toggle)
# ════════════════════════════════════════════════════════════════

ALLOWED_REACTIONS = {'❤️', '👍', '😂', '🔥', '✦', '👀'}

@dm_bp.route('/msg/<int:msg_id>/react', methods=['POST'])
@login_required
def react_message(msg_id: int):
    """
    POST /dm/msg/<id>/react
    Body (JSON): { emoji: str }
    Aynı emoji varsa toggle (sil), yoksa ekle.
    """
    msg = DMMessage.query.get_or_404(msg_id)
    if msg.is_deleted:
        return jsonify({'ok': False, 'error': 'Silinmiş mesaja tepki verilemez.'}), 422

    # Konuşmaya üye mi kontrol et
    conv = msg.conversation
    if conv.user1_id != current_user.id and conv.user2_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Yetkisiz.'}), 403

    data  = request.get_json(silent=True) or {}
    emoji = (data.get('emoji') or '').strip()
    if emoji not in ALLOWED_REACTIONS:
        return jsonify({'ok': False, 'error': 'Geçersiz tepki.'}), 422

    existing = DMReaction.query.filter_by(
        message_id=msg_id, user_id=current_user.id, emoji=emoji
    ).first()

    if existing:
        db.session.delete(existing)
        action = 'removed'
    else:
        db.session.add(DMReaction(message_id=msg_id, user_id=current_user.id, emoji=emoji))
        action = 'added'

    db.session.commit()

    # Güncel tepki özetini döndür
    summary = msg.reaction_summary(current_user.id)
    return jsonify({'ok': True, 'action': action, 'reactions': summary})


# ════════════════════════════════════════════════════════════════
#   MESAJ ARAMA
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/<int:user_id>/search')
@login_required
def search_messages(user_id: int):
    """
    GET /dm/<user_id>/search?q=<kelime>
    Yanıt: { results: [{id, content, created_at, is_mine}] }
    """
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'ok': False, 'error': 'En az 2 karakter girin.'}), 422

    u1, u2 = (current_user.id, user_id) if current_user.id < user_id else (user_id, current_user.id)
    conv   = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()
    if not conv:
        return jsonify({'ok': True, 'results': []})

    results = (
        DMMessage.query
        .filter_by(conversation_id=conv.id, is_deleted=False)
        .filter(DMMessage.content.ilike(f'%{q}%'))
        .filter(DMMessage.msg_type != 'aura')
        .order_by(DMMessage.created_at.desc())
        .limit(30)
        .all()
    )

    return jsonify({
        'ok': True,
        'results': [
            {
                'id':        m.id,
                'content':   m.content[:200],
                'created_at': m.created_at.strftime('%d %b %Y, %H:%M'),
                'is_mine':   m.sender_id == current_user.id,
                'msg_type':  m.msg_type,
            }
            for m in results
        ],
    })


# ════════════════════════════════════════════════════════════════
#   DOSYA YÜKLE + GÖNDER
# ════════════════════════════════════════════════════════════════

@dm_bp.route('/<int:user_id>/send-file', methods=['POST'])
@login_required
def send_file_message(user_id: int):
    """
    POST /dm/<user_id>/send-file
    multipart/form-data: file=<binary>, caption=<str opsiyonel>
    Dosyayı kaydeder ve mesaj olarak gönderir.
    Yanıt: { ok, message_id, html, conv_id }
    """
    if user_id == current_user.id:
        return jsonify({'ok': False, 'error': 'Kendinize dosya gönderemezsiniz.'}), 422

    User.query.get_or_404(user_id)

    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'Dosya bulunamadı.'}), 422

    f = request.files['file']
    if not f.filename:
        return jsonify({'ok': False, 'error': 'Geçersiz dosya adı.'}), 422

    # Boyut kontrolü (stream okunmadan önce Content-Length header'ı)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_FILE_BYTES:
        return jsonify({'ok': False, 'error': f'Dosya boyutu {MAX_FILE_BYTES // (1024*1024)} MB\'ı geçemez.'}), 422

    ext, file_type = _allowed_dm_file(f.filename)
    if not ext:
        return jsonify({'ok': False, 'error': 'Bu dosya türüne izin verilmiyor.'}), 422

    # Güvenli dosya adı + unique prefix
    safe_name   = secure_filename(f.filename)
    unique_name = f'{uuid.uuid4().hex[:12]}_{safe_name}'

    # Kayıt klasörü: uploads/{user_id}/dm/
    upload_root = current_app.config['UPLOAD_FOLDER']
    dm_dir      = os.path.join(upload_root, str(current_user.id), 'dm')
    os.makedirs(dm_dir, exist_ok=True)

    save_path = os.path.join(dm_dir, unique_name)
    f.save(save_path)

    # Erişim URL'si (app.py'deki /uploads/ route'u)
    file_url  = f'/uploads/{current_user.id}/dm/{unique_name}'
    mime_type = mimetypes.guess_type(safe_name)[0] or 'application/octet-stream'
    caption   = (request.form.get('caption') or '').strip()[:300]

    meta = {
        'filename':      safe_name,
        'original_name': f.filename,
        'size':          size,
        'size_str':      _format_size(size),
        'mime':          mime_type,
        'url':           file_url,
        'ext':           ext,
    }

    conv = _get_or_create_conversation(current_user.id, user_id)

    msg = DMMessage(
        conversation_id = conv.id,
        sender_id       = current_user.id,
        content         = caption or safe_name,   # Arama için içerik
        msg_type        = file_type,              # 'image' | 'file'
        meta_json       = json.dumps(meta),
        is_read         = False,
    )
    db.session.add(msg)
    conv.last_message_at = datetime.now(timezone.utc)
    db.session.commit()

    html = render_template('_dm_message.html', msg=msg, current_user=current_user)

    return jsonify({
        'ok':         True,
        'message_id': msg.id,
        'html':       html,
        'conv_id':    conv.id,
    })
