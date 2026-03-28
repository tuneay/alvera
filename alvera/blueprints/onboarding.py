from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user

from extensions import db
from models import OnboardingData, UserProfileExtras, CareerEntry, CustomLink

onboarding_bp = Blueprint('onboarding', __name__)

# ── Paket Akış Mimarisi ───────────────────────────────────────────────────────
# Paket 1 (Sosyal/Ücretsiz)  → /onboarding → paket seçimi → /onboarding/social
#   Social adımları: 1(Kimlik) 2(Bio) 3(Sinyaller) 4(Uzmanlık) 6(Linkler)
#   Vibe (5) atlanır. Tamamlandığında → feed
# Paket 2 (Profil/Ücretli)   → /onboarding → paket seçimi → adımlar 1-6
#   Tüm adımlar dahil (vibe 5). Tamamlandığında → extras → generate → site
BASE_STEPS = 6   # Sunucu adım sayısı (0-6)


def _get_or_create_onboarding() -> OnboardingData:
    data = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not data:
        data = OnboardingData(user_id=current_user.id, current_step=0)
        db.session.add(data)
        db.session.commit()
    return data


# ── Onboarding giriş (paket seçimi) ──────────────────────────────────────────
@onboarding_bp.route('/onboarding')
@login_required
def index():
    data = _get_or_create_onboarding()

    if data.is_complete:
        return redirect(url_for('feed.index'))

    # Paket 1 kullanıcıları adım 0'ı tamamladıysa Social akışına yönlendir
    if getattr(current_user, 'package', '1') == '1' and data.current_step > 0:
        return redirect(url_for('onboarding.social'))

    return render_template('onboarding.html',
                           current_step = data.current_step,
                           total_steps  = BASE_STEPS + 1,  # paket seçim adımı dahil
                           data         = data,
                           user_package = current_user.package)


# ── Social Onboarding (Paket 1 — Koyu Tema) ───────────────────────────────────
@onboarding_bp.route('/onboarding/social')
@login_required
def social():
    """Ücretsiz/Sosyal paket kullanıcıları için özel onboarding akışı."""
    data = _get_or_create_onboarding()

    if data.is_complete:
        return redirect(url_for('feed.index'))

    # Paket 2 kullanıcıları buraya gelemez
    if getattr(current_user, 'package', '1') != '1':
        return redirect(url_for('onboarding.index'))

    # Adım 0 henüz tamamlanmamışsa paket seçimine gönder
    if data.current_step == 0:
        return redirect(url_for('onboarding.index'))

    return render_template('onboarding_social.html',
                           data         = data,
                           current_step = data.current_step)


# ── Adım kaydetme (AJAX — her iki paket için ortak) ───────────────────────────
@onboarding_bp.route('/onboarding/save', methods=['POST'])
@login_required
def save():
    body      = request.get_json(silent=True) or {}
    step      = body.get('step')
    step_data = body.get('data', {})

    max_step = BASE_STEPS  # 0-6

    if step is None or not isinstance(step, int) or not (0 <= step <= max_step):
        return jsonify({'ok': False, 'error': 'Geçersiz adım.'}), 400

    data = _get_or_create_onboarding()

    if data.is_complete:
        return jsonify({'ok': False, 'error': 'Onboarding zaten tamamlandı.'}), 400

    # ── Adıma özel kayıt ─────────────────────────────────────────────────────
    if step == 0:
        package = (step_data.get('package') or '').strip()
        if package not in ('1', '2'):
            return jsonify({'ok': False, 'error': 'Lütfen bir paket seçin.'}), 422
        current_user.package = package

    elif step == 1:
        job_title = (step_data.get('job_title') or '').strip()
        if not job_title:
            return jsonify({'ok': False, 'error': 'Lütfen kendinizi tanımlayan bir unvan/başlık girin.'}), 422
        data.profession_category = (step_data.get('profession_category') or '').strip()[:80]
        data.job_title = job_title[:120]
        data.company   = (step_data.get('company') or '').strip()[:120]

    elif step == 2:
        bio = (step_data.get('bio') or '').strip()
        if not bio:
            return jsonify({'ok': False, 'error': 'Lütfen kendinizden bahsedin.'}), 422
        data.bio = bio[:600]

    elif step == 3:
        achievement     = (step_data.get('achievement')     or '').strip()
        differentiator  = (step_data.get('differentiator')  or '').strip()
        target_audience = (step_data.get('target_audience') or '').strip()
        data.achievement     = achievement[:250]    if achievement     else None
        data.differentiator  = differentiator[:200] if differentiator  else None
        data.target_audience = target_audience[:120] if target_audience else None

    elif step == 4:
        skills = (step_data.get('skills') or '').strip()
        if not skills:
            return jsonify({'ok': False, 'error': 'En az bir uzmanlık alanı girin.'}), 422
        data.skills = skills[:500]

    elif step == 5:
        # Sadece Paket 2 (Profil) bu adımı kullanır; Paket 1 bu adımı atlar
        vibe = (step_data.get('vibe') or '').strip()
        if vibe not in ('minimal', 'bold', 'warm'):
            return jsonify({'ok': False, 'error': 'Lütfen bir his seçin.'}), 422
        data.vibe = vibe

    elif step == 6:
        data.linkedin = (step_data.get('linkedin') or '').strip()[:255]
        data.github   = (step_data.get('github')   or '').strip()[:255]
        data.twitter  = (step_data.get('twitter')  or '').strip()[:255]
        data.website  = (step_data.get('website')  or '').strip()[:255]
        data.completed_at = datetime.now(timezone.utc)

    # İlerleme güncelle
    if step >= data.current_step:
        data.current_step = min(step + 1, max_step + 1)

    db.session.commit()

    # ── Adım 0: Pakete göre yönlendir ────────────────────────────────────────
    if step == 0:
        if current_user.package == '1':
            return jsonify({'ok': True, 'next_url': url_for('onboarding.social')})
        return jsonify({'ok': True, 'next_url': None})   # Paket 2 → aynı template devam

    # ── Adım 6: Son adım — pakete göre yönlendir ─────────────────────────────
    if step == 6:
        pkg = getattr(current_user, 'package', '1')
        if pkg == '2':
            return jsonify({'ok': True, 'next_url': url_for('onboarding.extras')})
        else:
            return jsonify({'ok': True, 'next_url': url_for('feed.index')})

    return jsonify({'ok': True, 'next_url': None})


# ── Opsiyonel Extras (yalnızca Paket 2) ──────────────────────────────────────
@onboarding_bp.route('/onboarding/extras')
@login_required
def extras():
    """Onboarding sonrası opsiyonel zenginleştirme adımı (yalnızca Paket 2 için)."""
    data = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not data or not data.is_complete:
        return redirect(url_for('onboarding.index'))
    if getattr(current_user, 'package', '1') == '1':
        return redirect(url_for('feed.index'))
    return render_template('onboarding_extras.html')
