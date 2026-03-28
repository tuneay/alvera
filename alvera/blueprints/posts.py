import json
import os
import uuid

from flask import Blueprint, current_app, jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import Post, Site, User

posts_bp = Blueprint('posts', __name__)

# ── Dosya türü sabitleri ─────────────────────────────────────────────────────
ALLOWED_IMAGE    = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO    = {'mp4', 'webm', 'mov'}
ALLOWED_DOCUMENT = {'pdf'}
ALLOWED_ALL      = ALLOWED_IMAGE | ALLOWED_VIDEO | ALLOWED_DOCUMENT
MAX_FILE_BYTES   = 50 * 1024 * 1024   # 50 MB


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ALL


def _file_type(filename: str) -> str:
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_IMAGE:    return 'image'
    if ext in ALLOWED_VIDEO:    return 'video'
    return 'document'


def _upload_dir(user_id: int) -> str:
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


# ── Gönderi oluştur ──────────────────────────────────────────────────────────
@posts_bp.route('/posts/create', methods=['POST'])
@login_required
def create():
    # Sadece Paket 2 kullanıcıları
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Standart paket kullanıcılarına özeldir.'}), 403

    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'Gönderi içeriği boş olamaz.'}), 422
    if len(content) > 1000:
        return jsonify({'ok': False, 'error': 'İçerik en fazla 1000 karakter olabilir.'}), 422

    # ── Dosya yükleme ────────────────────────────────────────────────────────
    media_list = []
    files = request.files.getlist('media')

    for f in files:
        if not f or not f.filename:
            continue
        if not _allowed(f.filename):
            return jsonify({'ok': False, 'error': f'Desteklenmeyen dosya türü: {f.filename}'}), 422

        # Boyut kontrolü
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > MAX_FILE_BYTES:
            return jsonify({'ok': False, 'error': 'Dosya boyutu 50 MB sınırını aşıyor.'}), 422

        ext      = f.filename.rsplit('.', 1)[1].lower()
        filename = f'{uuid.uuid4().hex}.{ext}'
        f.save(os.path.join(_upload_dir(current_user.id), filename))

        media_list.append({
            'filename':      filename,
            'type':          _file_type(f.filename),
            'original_name': secure_filename(f.filename),
        })

    post = Post(
        user_id     = current_user.id,
        content     = content,
        media_files = json.dumps(media_list) if media_list else None,
        source      = 'site',   # Site dashboard'undan oluşturulan güncelleme; sosyal akışa karışmaz
    )
    db.session.add(post)
    db.session.commit()

    # Render edilmiş HTML kartı döndür (AJAX ile sayfaya eklemek için)
    html = render_template('_post_card.html', post=post, owner=current_user)
    return jsonify({'ok': True, 'post_id': post.id, 'html': html})


# ── Gönderi sil ──────────────────────────────────────────────────────────────
@posts_bp.route('/posts/<int:post_id>/delete', methods=['DELETE'])
@login_required
def delete(post_id: int):
    post = Post.query.filter_by(id=post_id, user_id=current_user.id).first_or_404()

    # Dosyaları diskten sil
    for media in post.media_list:
        filepath = os.path.join(_upload_dir(current_user.id), media['filename'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass  # Sessizce geç

    db.session.delete(post)
    db.session.commit()
    return jsonify({'ok': True})


# ── Gönderi sabitle / sabitlemeyi kaldır ─────────────────────────────────────
@posts_bp.route('/posts/<int:post_id>/pin', methods=['POST'])
@login_required
def pin(post_id: int):
    """Gönderiyi profilin üstüne sabitle (max 2 pinli gönderi)."""
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Standart paket içindir.'}), 403

    post = Post.query.filter_by(id=post_id, user_id=current_user.id).first_or_404()

    if post.is_pinned:
        # Sabitlemeyi kaldır
        post.is_pinned = False
        db.session.commit()
        return jsonify({'ok': True, 'pinned': False})

    # Maksimum 2 sabitlenmiş gönderi
    pinned_count = Post.query.filter_by(user_id=current_user.id, is_pinned=True).count()
    if pinned_count >= 2:
        return jsonify({'ok': False, 'error': 'En fazla 2 gönderi sabitlenebilir.'}), 422

    post.is_pinned = True
    db.session.commit()
    return jsonify({'ok': True, 'pinned': True})


# ── Müsait rozeti toggle ──────────────────────────────────────────────────────
@posts_bp.route('/profile/available-toggle', methods=['POST'])
@login_required
def available_toggle():
    """'Müsait' rozetini aç / kapat."""
    current_user.is_available = not current_user.is_available
    db.session.commit()
    return jsonify({'ok': True, 'is_available': current_user.is_available})
