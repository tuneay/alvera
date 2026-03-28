"""
blueprints/brand.py
────────────────────
Paket 3 (Marka) işlemleri:
  - Hizmetler      CRUD
  - Portföy        CRUD
  - Referanslar    CRUD
  - İletişim formu (public submit + admin inbox)
"""

import json
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, render_template, abort, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from extensions import db
from models import Service, PortfolioItem, Testimonial, ContactMessage, Site

ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_IMG_MB   = 8


def _save_upload(file, user_id: int, name_stem: str) -> str | None:
    """
    Dosyayı static/uploads/{user_id}/{name_stem}.{ext} olarak kaydeder.
    Eski dosyayı siler. URL path'ini döner ('/uploads/{user_id}/cover.jpg' gibi).
    """
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_IMG:
        return None

    upload_folder = current_app.config['UPLOAD_FOLDER']
    user_dir      = os.path.join(upload_folder, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    # Aynı stem ile eski dosyayı sil
    for f in os.listdir(user_dir):
        if f.startswith(f"{name_stem}."):
            try:
                os.remove(os.path.join(user_dir, f))
            except OSError:
                pass

    filename = f"{name_stem}.{ext}"
    file.save(os.path.join(user_dir, filename))
    return f"/uploads/{user_id}/{filename}"

brand_bp = Blueprint('brand', __name__)


def _require_p3():
    """Paket 3 gerektiren endpointler için guard."""
    if current_user.package != '3':
        abort(403)


# ══════════════════════════════════════════════════════════════════════════════
#   HİZMETLER
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/brand/services', methods=['GET'])
@login_required
def list_services():
    _require_p3()
    services = Service.query.filter_by(user_id=current_user.id).order_by(Service.order_index).all()
    return jsonify({'ok': True, 'services': [s.to_dict() for s in services]})


@brand_bp.route('/brand/services', methods=['POST'])
@login_required
def add_service():
    _require_p3()
    body  = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()[:120]
    if not title:
        return jsonify({'ok': False, 'error': 'Hizmet adı gerekli.'}), 422

    count = Service.query.filter_by(user_id=current_user.id).count()
    svc   = Service(
        user_id     = current_user.id,
        title       = title,
        description = (body.get('description') or '').strip(),
        price_range = (body.get('price_range') or '').strip()[:80],
        cta_label   = (body.get('cta_label') or 'İletişime Geç').strip()[:60],
        order_index = count,
    )
    db.session.add(svc)
    db.session.commit()
    return jsonify({'ok': True, 'service': svc.to_dict()}), 201


@brand_bp.route('/brand/services/<int:sid>', methods=['PATCH'])
@login_required
def update_service(sid):
    _require_p3()
    svc = Service.query.filter_by(id=sid, user_id=current_user.id).first_or_404()
    body = request.get_json(silent=True) or {}

    if 'title'       in body: svc.title       = body['title'].strip()[:120]
    if 'description' in body: svc.description = body['description'].strip()
    if 'price_range' in body: svc.price_range = body['price_range'].strip()[:80]
    if 'cta_label'   in body: svc.cta_label   = body['cta_label'].strip()[:60]
    if 'order_index' in body: svc.order_index = int(body['order_index'])

    db.session.commit()
    return jsonify({'ok': True, 'service': svc.to_dict()})


@brand_bp.route('/brand/services/<int:sid>', methods=['DELETE'])
@login_required
def delete_service(sid):
    _require_p3()
    svc = Service.query.filter_by(id=sid, user_id=current_user.id).first_or_404()
    db.session.delete(svc)
    db.session.commit()
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
#   PORTFÖY
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/brand/portfolio', methods=['GET'])
@login_required
def list_portfolio():
    _require_p3()
    items = PortfolioItem.query.filter_by(user_id=current_user.id).order_by(PortfolioItem.order_index).all()
    return jsonify({'ok': True, 'portfolio': [i.to_dict() for i in items]})


@brand_bp.route('/brand/portfolio', methods=['POST'])
@login_required
def add_portfolio():
    _require_p3()
    body  = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()[:160]
    if not title:
        return jsonify({'ok': False, 'error': 'Proje başlığı gerekli.'}), 422

    count = PortfolioItem.query.filter_by(user_id=current_user.id).count()

    # Etiketleri JSON array olarak sakla
    tags_raw = body.get('tags', [])
    tags_json = json.dumps(tags_raw if isinstance(tags_raw, list) else
                           [t.strip() for t in str(tags_raw).split(',') if t.strip()],
                           ensure_ascii=False)

    item = PortfolioItem(
        user_id     = current_user.id,
        title       = title,
        problem     = (body.get('problem')  or '').strip(),
        solution    = (body.get('solution') or '').strip(),
        result      = (body.get('result')   or '').strip(),
        tags        = tags_json,
        url         = (body.get('url')      or '').strip()[:255],
        order_index = count,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()}), 201


@brand_bp.route('/brand/portfolio/<int:pid>', methods=['PATCH'])
@login_required
def update_portfolio(pid):
    _require_p3()
    item = PortfolioItem.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    body = request.get_json(silent=True) or {}

    if 'title'       in body: item.title    = body['title'].strip()[:160]
    if 'problem'     in body: item.problem  = body['problem'].strip()
    if 'solution'    in body: item.solution = body['solution'].strip()
    if 'result'      in body: item.result   = body['result'].strip()
    if 'url'         in body: item.url      = body['url'].strip()[:255]
    if 'order_index' in body: item.order_index = int(body['order_index'])
    if 'tags' in body:
        tags_raw  = body['tags']
        item.tags = json.dumps(
            tags_raw if isinstance(tags_raw, list) else
            [t.strip() for t in str(tags_raw).split(',') if t.strip()],
            ensure_ascii=False,
        )

    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})


@brand_bp.route('/brand/portfolio/<int:pid>', methods=['DELETE'])
@login_required
def delete_portfolio(pid):
    _require_p3()
    item = PortfolioItem.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
#   REFERANSLAR
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/brand/testimonials', methods=['GET'])
@login_required
def list_testimonials():
    _require_p3()
    items = Testimonial.query.filter_by(user_id=current_user.id).order_by(Testimonial.created_at.desc()).all()
    return jsonify({'ok': True, 'testimonials': [t.to_dict() for t in items]})


@brand_bp.route('/brand/testimonials', methods=['POST'])
@login_required
def add_testimonial():
    _require_p3()
    body        = request.get_json(silent=True) or {}
    client_name = (body.get('client_name') or '').strip()[:120]
    quote       = (body.get('quote')       or '').strip()
    if not client_name or not quote:
        return jsonify({'ok': False, 'error': 'Müşteri adı ve referans metni gerekli.'}), 422

    rating = int(body.get('rating', 5))
    rating = max(1, min(5, rating))

    t = Testimonial(
        user_id     = current_user.id,
        client_name = client_name,
        client_role = (body.get('client_role') or '').strip()[:120],
        quote       = quote,
        rating      = rating,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({'ok': True, 'testimonial': t.to_dict()}), 201


@brand_bp.route('/brand/testimonials/<int:tid>', methods=['DELETE'])
@login_required
def delete_testimonial(tid):
    _require_p3()
    t = Testimonial.query.filter_by(id=tid, user_id=current_user.id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
#   FOTOĞRAF YÜKLEME
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Profil fotoğrafı yükleme — tüm paketler."""
    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site:
        return jsonify({'ok': False, 'error': 'Önce sitenizi oluşturun.'}), 400

    file = request.files.get('avatar')
    if not file:
        return jsonify({'ok': False, 'error': 'Dosya bulunamadı.'}), 422

    # Boyut kontrolü (8 MB)
    file.seek(0, 2)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > MAX_IMG_MB:
        return jsonify({'ok': False, 'error': f'Maksimum {MAX_IMG_MB} MB yükleyebilirsiniz.'}), 422

    url = _save_upload(file, current_user.id, 'avatar')
    if not url:
        return jsonify({'ok': False, 'error': 'Geçersiz dosya formatı. PNG, JPG veya WebP yükleyin.'}), 422

    site.avatar_file = url
    db.session.commit()
    return jsonify({'ok': True, 'url': url})


@brand_bp.route('/brand/upload-cover', methods=['POST'])
@login_required
def upload_cover():
    """Marka banner/kapak görseli yükleme — Paket 3."""
    _require_p3()
    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site:
        return jsonify({'ok': False, 'error': 'Önce sitenizi oluşturun.'}), 400

    file = request.files.get('cover')
    if not file:
        return jsonify({'ok': False, 'error': 'Dosya bulunamadı.'}), 422

    file.seek(0, 2)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > MAX_IMG_MB:
        return jsonify({'ok': False, 'error': f'Maksimum {MAX_IMG_MB} MB yükleyebilirsiniz.'}), 422

    url = _save_upload(file, current_user.id, 'cover')
    if not url:
        return jsonify({'ok': False, 'error': 'Geçersiz dosya formatı. PNG, JPG veya WebP yükleyin.'}), 422

    site.cover_file = url
    db.session.commit()
    return jsonify({'ok': True, 'url': url})


# ══════════════════════════════════════════════════════════════════════════════
#   İLETİŞİM FORMU (public — login gerektirmez)
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/contact/<slug>', methods=['POST'])
def submit_contact(slug):
    """Ziyaretçinin bir Paket 3 kullanıcısına iletişim formu göndermesi."""
    site  = Site.query.filter_by(slug=slug, is_published=True).first_or_404()
    owner = site.owner

    if owner.package != '3':
        abort(404)

    body    = request.get_json(silent=True) or {}
    name    = (body.get('name')    or '').strip()[:120]
    email   = (body.get('email')   or '').strip()[:255]
    subject = (body.get('subject') or '').strip()[:200]
    message = (body.get('message') or '').strip()

    if not name or not email or not message:
        return jsonify({'ok': False, 'error': 'Ad, e-posta ve mesaj zorunludur.'}), 422

    # Basit e-posta format kontrolü
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'ok': False, 'error': 'Geçerli bir e-posta adresi girin.'}), 422

    service_id = body.get('service_id')
    if service_id:
        svc = Service.query.filter_by(id=int(service_id), user_id=owner.id).first()
        service_id = svc.id if svc else None

    msg = ContactMessage(
        user_id    = owner.id,
        name       = name,
        email      = email,
        subject    = subject,
        message    = message,
        service_id = service_id,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({'ok': True, 'message': 'Mesajınız iletildi.'})


# ══════════════════════════════════════════════════════════════════════════════
#   INBOX — Gelen mesajlar (admin)
# ══════════════════════════════════════════════════════════════════════════════

@brand_bp.route('/brand/inbox', methods=['GET'])
@login_required
def inbox():
    _require_p3()
    msgs = (ContactMessage.query
            .filter_by(user_id=current_user.id)
            .order_by(ContactMessage.created_at.desc())
            .limit(100)
            .all())
    return jsonify({
        'ok': True,
        'messages': [
            {
                'id':         m.id,
                'name':       m.name,
                'email':      m.email,
                'subject':    m.subject,
                'message':    m.message,
                'service_id': m.service_id,
                'is_read':    m.is_read,
                'created_at': m.created_at.isoformat(),
            }
            for m in msgs
        ],
        'unread_count': sum(1 for m in msgs if not m.is_read),
    })


@brand_bp.route('/brand/inbox/<int:mid>/read', methods=['POST'])
@login_required
def mark_read(mid):
    _require_p3()
    msg = ContactMessage.query.filter_by(id=mid, user_id=current_user.id).first_or_404()
    msg.is_read = True
    db.session.commit()
    return jsonify({'ok': True})
