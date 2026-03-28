"""
Alvera — Admin Blueprint (Backward Compatibility Katmanı)
──────────────────────────────────────────────────────────
Eski /admin ve /admin/save URL'leri yeni /site/edit ve /site/save
adreslerine kalıcı yönlendirme yapar.

Gerçek mantık → blueprints/site.py
"""
from flask import Blueprint, redirect, url_for
from flask_login import login_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@login_required
def panel():
    """/admin → /site/edit (301 kalıcı yönlendirme)."""
    return redirect(url_for('site.edit'), 301)


@admin_bp.route('/admin/save', methods=['POST'])
@login_required
def save():
    """/admin/save → /site/save (308 kalıcı POST yönlendirmesi)."""
    return redirect(url_for('site.save'), 308)
