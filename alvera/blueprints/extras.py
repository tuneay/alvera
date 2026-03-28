"""
extras.py — Opsiyonel profil genişletme endpoint'leri:
  UserProfileExtras (durum, CTA, çalışma tercihleri)
  CareerEntry (kariyer zaman çizelgesi)
  CustomLink  (link merkezi + tıklama takibi)
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import UserProfileExtras, CareerEntry, CustomLink

extras_bp = Blueprint('extras', __name__)


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _get_or_create_extras() -> UserProfileExtras:
    ex = UserProfileExtras.query.filter_by(user_id=current_user.id).first()
    if not ex:
        ex = UserProfileExtras(user_id=current_user.id)
        db.session.add(ex)
    return ex


# ── Profil Bilgileri (durum + CTA + çalışma tercihleri) ──────────────────────

@extras_bp.route('/extras/profile-info', methods=['POST'])
@login_required
def save_profile_info():
    body = request.get_json(silent=True) or {}
    ex = _get_or_create_extras()

    ex.status_text     = (body.get('status_text')     or '').strip()[:160] or None
    ex.status_emoji    = (body.get('status_emoji')    or '').strip()[:10]  or None
    ex.cta_text        = (body.get('cta_text')        or '').strip()[:80]  or None
    ex.cta_url         = (body.get('cta_url')         or '').strip()[:255] or None
    ex.cta_enabled     = bool(body.get('cta_enabled', False))
    ex.work_type       = (body.get('work_type')       or '').strip()[:20]  or None
    ex.work_engagement = (body.get('work_engagement') or '').strip()[:30]  or None
    ex.work_budget     = (body.get('work_budget')     or '').strip()[:50]  or None

    db.session.commit()
    return jsonify({'ok': True})


# ── Kariyer Zaman Çizelgesi ───────────────────────────────────────────────────

@extras_bp.route('/extras/career', methods=['GET'])
@login_required
def list_career():
    entries = (CareerEntry.query
               .filter_by(user_id=current_user.id)
               .order_by(CareerEntry.display_order, CareerEntry.id.desc())
               .all())
    return jsonify([e.to_dict() for e in entries])


@extras_bp.route('/extras/career', methods=['POST'])
@login_required
def add_career():
    body = request.get_json(silent=True) or {}
    role    = (body.get('role')    or '').strip()[:120]
    company = (body.get('company') or '').strip()[:120]
    start   = (body.get('start_year') or '').strip()[:20]

    if not role or not company or not start:
        return jsonify({'ok': False, 'error': 'Görev, şirket ve başlangıç yılı zorunludur.'}), 422

    count = CareerEntry.query.filter_by(user_id=current_user.id).count()
    if count >= 10:
        return jsonify({'ok': False, 'error': 'En fazla 10 kariyer girişi ekleyebilirsiniz.'}), 422

    entry = CareerEntry(
        user_id       = current_user.id,
        role          = role,
        company       = company,
        start_year    = start,
        end_year      = (body.get('end_year') or '').strip()[:20] or None,
        is_current    = bool(body.get('is_current', False)),
        description   = (body.get('description') or '').strip()[:300] or None,
        display_order = count,
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'ok': True, 'entry': entry.to_dict()})


@extras_bp.route('/extras/career/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_career(entry_id):
    entry = CareerEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'ok': True})


# ── Link Merkezi ──────────────────────────────────────────────────────────────

@extras_bp.route('/extras/links', methods=['GET'])
@login_required
def list_links():
    links = (CustomLink.query
             .filter_by(user_id=current_user.id)
             .order_by(CustomLink.display_order, CustomLink.id)
             .all())
    return jsonify([l.to_dict() for l in links])


@extras_bp.route('/extras/links', methods=['POST'])
@login_required
def add_link():
    body  = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()[:80]
    url   = (body.get('url')   or '').strip()[:255]

    if not title or not url:
        return jsonify({'ok': False, 'error': 'Başlık ve URL zorunludur.'}), 422
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    count = CustomLink.query.filter_by(user_id=current_user.id).count()
    if count >= 10:
        return jsonify({'ok': False, 'error': 'En fazla 10 link ekleyebilirsiniz.'}), 422

    link = CustomLink(
        user_id       = current_user.id,
        title         = title,
        url           = url,
        emoji         = (body.get('emoji') or '').strip()[:10] or None,
        display_order = count,
    )
    db.session.add(link)
    db.session.commit()
    return jsonify({'ok': True, 'link': link.to_dict()})


@extras_bp.route('/extras/links/<int:link_id>', methods=['DELETE'])
@login_required
def delete_link(link_id):
    link = CustomLink.query.filter_by(id=link_id, user_id=current_user.id).first_or_404()
    db.session.delete(link)
    db.session.commit()
    return jsonify({'ok': True})


@extras_bp.route('/extras/links/<int:link_id>/click', methods=['POST'])
def track_click(link_id):
    """Public endpoint — profil sayfasındaki link tıklamalarını say."""
    link = CustomLink.query.get_or_404(link_id)
    try:
        link.click_count += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True})
