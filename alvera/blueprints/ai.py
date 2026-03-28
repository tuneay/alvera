import json
import re

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user

from extensions import db
from models import Site, OnboardingData
from services.ai_service import generate_variants, \
                                generate_slug, generate_content_suggestions, refresh_bio, \
                                expand_text

ai_bp = Blueprint('ai', __name__)


def _make_unique_slug(base_slug: str) -> str:
    """Slug çakışırsa sonuna numara ekler."""
    slug = base_slug
    counter = 1
    while Site.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


# ── Üretim sayfası ────────────────────────────────────────────────────────────
@ai_bp.route('/generate')
@login_required
def generate_page():
    # Yalnızca Paket 2 (Ücretli Profil) kullanıcıları kişisel site oluşturabilir
    if current_user.package != '2':
        return redirect(url_for('feed.index'))

    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not onboarding or not onboarding.is_complete:
        return redirect(url_for('onboarding.index'))

    site = Site.query.filter_by(user_id=current_user.id).first()
    if site and site.chosen_variant:
        return redirect(url_for('site.dashboard'))

    return render_template('generate.html', package=current_user.package)


# ── AJAX: AI üretimini başlat ─────────────────────────────────────────────────
@ai_bp.route('/generate/create', methods=['POST'])
@login_required
def create():
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Profil paketine özeldir.'}), 403

    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not onboarding or not onboarding.is_complete:
        return jsonify({'ok': False, 'error': 'Onboarding tamamlanmamış.'}), 400

    site = Site.query.filter_by(user_id=current_user.id).first()
    if site and site.raw_generation:
        try:
            variants = json.loads(site.raw_generation)
            return jsonify({'ok': True, 'variants': variants})
        except Exception:
            pass

    try:
        profile = onboarding.to_dict()

        # Paket 2 → standart kişisel profil varyantları
        result = generate_variants(profile)

        if not site:
            base_slug = generate_slug(current_user.full_name or current_user.email.split('@')[0])
            slug      = _make_unique_slug(base_slug)
            site      = Site(user_id=current_user.id, slug=slug)
            db.session.add(site)

        site.raw_generation = json.dumps(result, ensure_ascii=False)
        site.vibe           = onboarding.vibe
        db.session.commit()

        return jsonify({'ok': True, 'variants': result})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── AJAX: Varyant seçimi ──────────────────────────────────────────────────────
@ai_bp.route('/generate/choose', methods=['POST'])
@login_required
def choose():
    body    = request.get_json(silent=True) or {}
    variant = body.get('variant')

    if variant not in ('a', 'b'):
        return jsonify({'ok': False, 'error': 'Geçersiz seçim.'}), 400

    site = Site.query.filter_by(user_id=current_user.id).first()
    if not site or not site.raw_generation:
        return jsonify({'ok': False, 'error': 'Önce üretim yapılmalı.'}), 400

    try:
        result  = json.loads(site.raw_generation)
        chosen  = result.get(f'variant_{variant}', {})

        site.chosen_variant  = variant
        site.headline        = chosen.get('headline', '')
        site.tagline         = chosen.get('tagline', '')
        site.bio_text        = chosen.get('bio', '')
        site.cta_text        = chosen.get('cta', '')
        site.skills_display  = json.dumps(chosen.get('skills_display', []), ensure_ascii=False)
        site.is_published    = True

        db.session.commit()

        return jsonify({'ok': True, 'redirect': url_for('site.dashboard')})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── AJAX: İçerik önerisi al (Paket 2) ────────────────────────────────────────
@ai_bp.route('/ai/content-suggestions', methods=['POST'])
@login_required
def content_suggestions():
    """
    Kullanıcının profilini + son gönderilerini analiz eder,
    3 kişiselleştirilmiş içerik fikri döner.
    """
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Standart paket kullanıcılarına özeldir.'}), 403

    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not onboarding or not onboarding.is_complete:
        return jsonify({'ok': False, 'error': 'Önce onboarding\'i tamamlayın.'}), 400

    # Son 10 gönderiyi al
    recent_posts = [p.content for p in current_user.posts.limit(10).all()]

    try:
        profile = onboarding.to_dict()
        result  = generate_content_suggestions(profile, recent_posts)
        return jsonify({'ok': True, **result})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── AJAX: Bio yenile (Paket 2) ────────────────────────────────────────────────
@ai_bp.route('/ai/refresh-bio', methods=['POST'])
@login_required
def refresh_bio_route():
    """
    Güncel profil verilerine göre yeni headline + bio üretir,
    Site tablosuna kaydeder.
    """
    if current_user.package != '2':
        return jsonify({'ok': False, 'error': 'Bu özellik Profil paketine özeldir.'}), 403

    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    site       = Site.query.filter_by(user_id=current_user.id).first()

    if not onboarding or not site:
        return jsonify({'ok': False, 'error': 'Profil verisi bulunamadı.'}), 400

    try:
        profile = onboarding.to_dict()
        result  = refresh_bio(profile)

        site.headline = result.get('headline', site.headline)
        site.bio_text = result.get('bio', site.bio_text)
        db.session.commit()

        return jsonify({
            'ok':       True,
            'headline': site.headline,
            'bio':      site.bio_text,
        })

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── AJAX: Metin Genişletici — Onboarding sırasında kullanılır ─────────────────
@ai_bp.route('/ai/expand-text', methods=['POST'])
@login_required
def expand_text_route():
    """
    Kullanıcının yazdığı kısa metni (bio / achievement / differentiator)
    bağlam bilgisiyle zenginleştirir.

    Body:
        field       — 'bio' | 'achievement' | 'differentiator'
        text        — ham kısa metin
        job_title   — (opsiyonel) onboarding'den anlık değer
        profession_category — (opsiyonel)
    """
    body  = request.get_json(silent=True) or {}
    field = body.get('field', 'bio')
    text  = (body.get('text') or '').strip()

    if field not in ('bio', 'achievement', 'differentiator'):
        return jsonify({'ok': False, 'error': 'Geçersiz alan.'}), 400
    if not text or len(text) < 5:
        return jsonify({'ok': False, 'error': 'Lütfen önce bir şeyler yazın.'}), 422

    # Bağlamı önce mevcut onboarding verisinden al, eksikleri body'den tamamla
    onboarding = OnboardingData.query.filter_by(user_id=current_user.id).first()
    context = {
        'full_name':           current_user.full_name or '',
        'job_title':           body.get('job_title') or (onboarding.job_title if onboarding else '') or '',
        'profession_category': body.get('profession_category') or (onboarding.profession_category if onboarding else '') or '',
        'vibe':                body.get('vibe') or (onboarding.vibe if onboarding else '') or 'minimal',
    }

    try:
        result = expand_text(field, text, context)
        return jsonify({'ok': True, 'expanded': result.get('expanded', text)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
