"""
Alvera — Bildirim Sistemi Blueprint
In-app bildirimler: beğeni · yorum · takip · @mention
"""
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import Notification, Post, Site, User

notif_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

# Sayfada kaç bildirim gösterilsin
LIST_LIMIT    = 30
DROPDOWN_LIMIT = 8


# ════════════════════════════════════════════════════════════════
#   YARDIMCI — Bildirim oluştur (tekrar oluşturmayı önle)
# ════════════════════════════════════════════════════════════════

def create_notification(*, user_id: int, actor_id: int,
                        notif_type: str, post_id: int | None = None) -> None:
    """
    Bildirim oluşturur.
    • Kendine bildirim gönderilmez.
    • Aynı (user, actor, type, post) kombinasyonu zaten varsa tekrar oluşturulmaz.
    """
    if user_id == actor_id:
        return

    exists = Notification.query.filter_by(
        user_id    = user_id,
        actor_id   = actor_id,
        notif_type = notif_type,
        post_id    = post_id,
        is_read    = False,
    ).first()

    if exists:
        # Zaten okunmamış bildirim var — sadece zamanı yenile
        exists.created_at = datetime.now(timezone.utc)
        db.session.commit()
        return

    notif = Notification(
        user_id    = user_id,
        actor_id   = actor_id,
        notif_type = notif_type,
        post_id    = post_id,
    )
    db.session.add(notif)
    db.session.commit()


def parse_mentions(content: str) -> list[int]:
    """
    '@[Ad Soyad|user_id]' formatındaki mention'lardan user_id listesi çıkarır.
    Örnek: '@[Tuna Akgün|3]' → [3]
    """
    return [int(uid) for uid in re.findall(r'@\[[^\|]+\|(\d+)\]', content)]


def notify_mentions(content: str, actor_id: int, post_id: int | None = None) -> None:
    """İçerikteki @mention'lara bildirim gönderir."""
    for uid in parse_mentions(content):
        create_notification(
            user_id    = uid,
            actor_id   = actor_id,
            notif_type = Notification.TYPE_MENTION,
            post_id    = post_id,
        )


# ════════════════════════════════════════════════════════════════
#   BİLDİRİM LİSTESİ SAYFASI
# ════════════════════════════════════════════════════════════════

@notif_bp.route('/')
@login_required
def index():
    """Tüm bildirimler sayfası."""
    notifs = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(LIST_LIMIT)
        .all()
    )

    # Sayfayı açınca tümünü okundu işaretle
    unread = [n for n in notifs if not n.is_read]
    if unread:
        for n in unread:
            n.is_read = True
        db.session.commit()

    return render_template('notifications.html', notifs=notifs)


# ════════════════════════════════════════════════════════════════
#   DROPDOWN VERİSİ  (nav zil ikonuna tıklayınca)
# ════════════════════════════════════════════════════════════════

@notif_bp.route('/dropdown')
@login_required
def dropdown():
    """
    GET /notifications/dropdown
    Son 8 bildirimi HTML olarak döner + okunmamış sayı.
    Nav dropdown'u AJAX ile doldurur.
    """
    notifs = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(DROPDOWN_LIMIT)
        .all()
    )

    # Okundu işaretle
    changed = False
    for n in notifs:
        if not n.is_read:
            n.is_read = True
            changed = True
    if changed:
        db.session.commit()

    html = render_template('_notif_dropdown.html', notifs=notifs)
    resp = jsonify({'html': html, 'count': len(notifs)})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ════════════════════════════════════════════════════════════════
#   OKUNMAMIŞ SAYISI POLL  (nav badge için)
# ════════════════════════════════════════════════════════════════

@notif_bp.route('/unread-count')
@login_required
def unread_count():
    """
    GET /notifications/unread-count
    Yanıt: { count }
    """
    count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()
    resp = jsonify({'count': count})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ════════════════════════════════════════════════════════════════
#   TÜMÜNÜ OKUNDU İŞARETLE
# ════════════════════════════════════════════════════════════════

@notif_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """POST /notifications/mark-all-read"""
    (
        Notification.query
        .filter_by(user_id=current_user.id, is_read=False)
        .update({'is_read': True})
    )
    db.session.commit()
    return jsonify({'ok': True})
