"""
Alvera — Site Yönetim Blueprint  (/site)
─────────────────────────────────────────
Dashboard özeti + İçerik düzenleme tek çatı altında.

  GET  /site/        → Özet & analitik hub  (eski /dashboard)
  GET  /site/edit    → İçerik düzenleme     (eski /admin)
  POST /site/save    → AJAX kayıt           (eski /admin/save)
"""
import json
from datetime import datetime, timezone, timedelta

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user

from extensions import db
from models import (
    Site, OnboardingData, Service, PortfolioItem, Testimonial,
    ContactMessage, UserProfileExtras, CareerEntry, CustomLink,
    PageView, Post,
)

site_bp = Blueprint('site', __name__, url_prefix='/site')

# Karakter limitleri — estetik bozulmasın
LIMITS = {
    'headline':  80,
    'tagline':   160,
    'bio_text':  600,
    'cta_text':  40,
    'job_title': 120,
    'company':   120,
    'linkedin':  255,
    'github':    255,
    'twitter':   255,
    'website':   255,
}


# ════════════════════════════════════════════════════════════════
#   DASHBOARD HUB  — /site/
# ════════════════════════════════════════════════════════════════

@site_bp.route('/')
@login_required
def dashboard():
    """Site yönetim özeti & analitik hub. Yalnızca Paket 2 (Ücretli Profil) kullanıcıları erişebilir."""
    if current_user.package != '2':
        # Ücretsiz Sosyal paket kullanıcıları feed'e yönlendirilir
        return redirect(url_for('feed.index'))

    site       = Site.query.filter_by(user_id=current_user.id).first()
    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()

    skills = []
    if site and site.skills_display:
        try:
            skills = json.loads(site.skills_display)
        except Exception:
            skills = [s.strip() for s in site.skills_display.split(',') if s.strip()]

    # Paket 2: site dashboard güncellemeleri (yalnızca source='site'; sosyal gönderiler karışmaz)
    posts = []
    if current_user.package == '2':
        from models import Post as PostModel
        posts = (
            PostModel.query
            .filter_by(user_id=current_user.id, source='site')
            .order_by(PostModel.created_at.desc())
            .limit(20)
            .all()
        )

    # Setup Guide tamamlanma verileri
    has_avatar       = bool(site.avatar_file) if site else False
    has_cover        = bool(site.cover_file)  if site else False
    has_posts        = len(posts) > 0
    has_portfolio    = False
    has_testimonials = False
    if current_user.package == '3' and site:
        has_portfolio    = PortfolioItem.query.filter_by(user_id=current_user.id).count() > 0
        has_testimonials = Testimonial.query.filter_by(user_id=current_user.id).count() > 0

    # Analytics: toplam ve bu hafta görüntülenme
    total_views = 0
    week_views  = 0
    if site:
        week_ago    = datetime.now(timezone.utc) - timedelta(days=7)
        total_views = PageView.query.filter_by(site_id=site.id).count()
        week_views  = PageView.query.filter(
            PageView.site_id  == site.id,
            PageView.viewed_at >= week_ago,
        ).count()

    return render_template(
        'dashboard.html',
        user=current_user,
        site=site,
        onboarding=onboarding,
        skills=skills,
        posts=posts,
        has_avatar=has_avatar,
        has_cover=has_cover,
        has_posts=has_posts,
        has_portfolio=has_portfolio,
        has_testimonials=has_testimonials,
        total_views=total_views,
        week_views=week_views,
    )


# ════════════════════════════════════════════════════════════════
#   İÇERİK DÜZENLEME  — /site/edit
# ════════════════════════════════════════════════════════════════

@site_bp.route('/edit')
@login_required
def edit():
    """Site içerik düzenleme paneli. Yalnızca Paket 2 (Ücretli Profil) kullanıcıları erişebilir."""
    if current_user.package != '2':
        return redirect(url_for('feed.index'))

    site       = Site.query.filter_by(user_id=current_user.id).first()
    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()

    if not site or not site.is_published:
        return redirect(url_for('site.dashboard'))

    skills = []
    if site.skills_display:
        try:
            skills = json.loads(site.skills_display)
        except Exception:
            skills = [s.strip() for s in site.skills_display.split(',') if s.strip()]

    # Paket 3 verileri
    p3_services     = []
    p3_portfolio    = []
    p3_testimonials = []
    p3_inbox        = []
    unread_count    = 0

    if current_user.package == '3':
        p3_services     = current_user.services.all()
        p3_portfolio    = current_user.portfolio.all()
        p3_testimonials = current_user.testimonials.all()
        p3_inbox        = (current_user.contact_msgs
                           .order_by(ContactMessage.created_at.desc())
                           .limit(50).all())
        unread_count    = sum(1 for m in p3_inbox if not m.is_read)

    # Opsiyonel genişletme verileri
    extras = UserProfileExtras.query.filter_by(user_id=current_user.id).first()
    career_entries = (CareerEntry.query
                      .filter_by(user_id=current_user.id)
                      .order_by(CareerEntry.display_order, CareerEntry.id.desc())
                      .all())
    custom_links = (CustomLink.query
                    .filter_by(user_id=current_user.id)
                    .order_by(CustomLink.display_order, CustomLink.id)
                    .all())

    return render_template(
        'admin.html',
        user=current_user,
        site=site,
        onboarding=onboarding,
        skills=skills,
        limits=LIMITS,
        p3_services=p3_services,
        p3_portfolio=p3_portfolio,
        p3_testimonials=p3_testimonials,
        p3_inbox=p3_inbox,
        unread_count=unread_count,
        extras=extras,
        career_entries=career_entries,
        custom_links=custom_links,
    )


# ════════════════════════════════════════════════════════════════
#   KAYDET  — /site/save  (AJAX POST)
# ════════════════════════════════════════════════════════════════

@site_bp.route('/save', methods=['POST'])
@login_required
def save():
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Profil paketine özeldir.'}), 403

    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site or not site.is_published:
        return jsonify({'ok': False, 'error': 'Site bulunamadı.'}), 404

    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    body       = request.get_json(silent=True) or {}
    section    = body.get('section')   # 'identity' | 'content' | 'links'
    data       = body.get('data', {})

    if section == 'content':
        headline = (data.get('headline') or '').strip()
        tagline  = (data.get('tagline')  or '').strip()
        bio_text = (data.get('bio_text') or '').strip()
        cta_text = (data.get('cta_text') or '').strip()

        if not headline:
            return jsonify({'ok': False, 'error': 'Başlık boş olamaz.'}), 422

        site.headline = headline[:LIMITS['headline']]
        site.tagline  = tagline[:LIMITS['tagline']]
        site.bio_text = bio_text[:LIMITS['bio_text']]
        site.cta_text = cta_text[:LIMITS['cta_text']]

        skills_raw = (data.get('skills') or '').strip()
        if skills_raw:
            skills_list = [s.strip() for s in skills_raw.split(',') if s.strip()][:6]
            site.skills_display = json.dumps(skills_list, ensure_ascii=False)

    elif section == 'identity':
        if onboarding:
            onboarding.job_title = (data.get('job_title') or '').strip()[:LIMITS['job_title']]
            onboarding.company   = (data.get('company')   or '').strip()[:LIMITS['company']]

    elif section == 'links':
        if onboarding:
            onboarding.linkedin = (data.get('linkedin') or '').strip()[:LIMITS['linkedin']]
            onboarding.github   = (data.get('github')   or '').strip()[:LIMITS['github']]
            onboarding.twitter  = (data.get('twitter')  or '').strip()[:LIMITS['twitter']]
            onboarding.website  = (data.get('website')  or '').strip()[:LIMITS['website']]
    else:
        return jsonify({'ok': False, 'error': 'Geçersiz section.'}), 400

    db.session.commit()
    return jsonify({'ok': True})
