import json
from datetime import datetime, timezone

from flask import Blueprint, render_template, abort, Response, request, redirect, url_for
from flask_login import current_user

from models import Site, OnboardingData, User, PageView, UserProfileExtras, CareerEntry, CustomLink, Post, MindMap
from extensions import db

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """
    Landing page.
    Oturum açık kullanıcılar:
      - Onboarding tamamlanmamışsa → /onboarding
      - Tamamlanmışsa              → /feed
    """
    if current_user.is_authenticated:
        ob = OnboardingData.query.filter_by(user_id=current_user.id).first()
        if not ob or not ob.is_complete:
            return redirect(url_for('onboarding.index'))
        return redirect(url_for('feed.index'))

    from sqlalchemy import desc
    featured = (Site.query
                .filter_by(is_published=True)
                .order_by(desc(Site.id))
                .limit(4)
                .all())
    return render_template('index.html', featured=featured)


@main_bp.route('/dashboard')
def dashboard_redirect():
    """/dashboard → /site/ backward-compat 301 yönlendirmesi."""
    return redirect(url_for('site.dashboard'), 301)


# ── Discover / Marketplace ───────────────────────────────────────────────────
@main_bp.route('/discover')
def discover():
    """
    Herkese açık profil rehberi.
    Paket 3 markaları üstte öne çıkarılır, diğerleri altında listelenir.
    """
    published_sites = (Site.query
                       .filter_by(is_published=True)
                       .join(User, Site.user_id == User.id)
                       .add_columns(User.package, User.full_name,
                                    User.is_available, User.id.label('uid'))
                       .all())

    brands    = []   # Paket 3
    profiles  = []   # Paket 1 & 2

    for row in published_sites:
        site, package, full_name, is_available, uid = (
            row.Site, row.package, row.full_name, row.is_available, row.uid
        )
        card = {
            'slug':        site.slug,
            'headline':    site.headline,
            'tagline':     site.tagline,
            'vibe':        site.vibe,
            'is_available': is_available,
            'full_name':   full_name or site.slug,
            'package':     package,
            'avatar_file': site.avatar_file,
            'cover_file':  site.cover_file,
        }
        if package == '3':
            brands.append(card)
        else:
            profiles.append(card)

    return render_template('discover.html',
                           brands=brands,
                           profiles=profiles,
                           total=len(brands) + len(profiles))


# ── SEO: robots.txt ──────────────────────────────────────────────────────────
@main_bp.route('/robots.txt')
def robots():
    base = request.host_url.rstrip('/')
    content = f"""User-agent: *
Allow: /

# Yönetim sayfaları indexlenmesin
Disallow: /dashboard
Disallow: /site/
Disallow: /auth/
Disallow: /onboarding
Disallow: /generate

Sitemap: {base}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')


# ── SEO: sitemap.xml ─────────────────────────────────────────────────────────
@main_bp.route('/sitemap.xml')
def sitemap():
    base  = request.host_url.rstrip('/')
    sites = Site.query.filter_by(is_published=True).all()
    now   = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    urls = [
        f"""  <url>
    <loc>{base}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>"""
    ]

    for s in sites:
        lastmod = s.updated_at.strftime('%Y-%m-%d') if s.updated_at else now
        urls.append(f"""  <url>
    <loc>{base}/{s.slug}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>""")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>'

    return Response(xml, mimetype='application/xml')


# ── Public profil sayfası ────────────────────────────────────────────────────
@main_bp.route('/<slug>')
def profile(slug):
    """Kullanıcının public landing page'i — alvera.me/<slug>"""
    site       = Site.query.filter_by(slug=slug, is_published=True).first_or_404()
    owner      = site.owner
    owner_data = OnboardingData.query.filter_by(user_id=owner.id).first()

    # View tracking: kendi sayfasını görüntüleyenleri sayma
    is_owner = current_user.is_authenticated and current_user.id == owner.id
    if not is_owner:
        try:
            db.session.add(PageView(
                site_id  = site.id,
                referrer = request.referrer,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    skills = []
    if site.skills_display:
        try:
            skills = json.loads(site.skills_display)
        except Exception:
            skills = [s.strip() for s in site.skills_display.split(',') if s.strip()]

    # Social gönderiler — tüm paketler için (pinliler önce, sonra tarihe göre)
    from sqlalchemy import desc as _desc
    posts = (Post.query
             .filter_by(user_id=owner.id)
             .order_by(Post.is_pinned.desc(), Post.created_at.desc())
             .limit(50)
             .all())

    # Paket 3: hizmetler, portföy, referanslar
    p3_services     = []
    p3_portfolio    = []
    p3_testimonials = []
    if owner.package == '3':
        from models import Service, PortfolioItem, Testimonial
        p3_services     = owner.services.all()
        p3_portfolio    = owner.portfolio.all()
        p3_testimonials = owner.testimonials.all()

    # Opsiyonel genişletme verileri (tüm paketler)
    extras = UserProfileExtras.query.filter_by(user_id=owner.id).first()
    career_entries = (CareerEntry.query
                      .filter_by(user_id=owner.id)
                      .order_by(CareerEntry.display_order, CareerEntry.id.desc())
                      .all())
    custom_links = (CustomLink.query
                    .filter_by(user_id=owner.id)
                    .order_by(CustomLink.display_order, CustomLink.id)
                    .all())

    viewer   = current_user if current_user.is_authenticated else None
    mind_map = MindMap.query.filter_by(user_id=owner.id).first()

    return render_template('profile.html',
                           site=site,
                           owner=owner,
                           owner_data=owner_data,
                           skills=skills,
                           posts=posts,
                           viewer=viewer,
                           is_owner=is_owner,
                           p3_services=p3_services,
                           p3_portfolio=p3_portfolio,
                           p3_testimonials=p3_testimonials,
                           extras=extras,
                           career_entries=career_entries,
                           custom_links=custom_links,
                           mind_map=mind_map)
