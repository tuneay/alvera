from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, OnboardingData


def _smart_home_url():
    """
    Kullanıcının onboarding durumuna göre uygun yönlendirme URL'si döndürür.
    Onboarding tamamlanmamışsa /onboarding, tamamlanmışsa /feed.
    """
    ob = OnboardingData.query.filter_by(user_id=current_user.id).first()
    if not ob or not ob.is_complete:
        return url_for('onboarding.index')
    return url_for('feed.index')

auth_bp = Blueprint('auth', __name__)


# ── Kayıt ────────────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(_smart_home_url())

    error = None

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        # ── Validasyon ───────────────────────────────────────────────────────
        if not full_name:
            error = 'Lütfen adınızı girin.'
        elif not email or '@' not in email:
            error = 'Geçerli bir e-posta adresi girin.'
        elif len(password) < 8:
            error = 'Şifre en az 8 karakter olmalıdır.'
        elif password != confirm:
            error = 'Şifreler eşleşmiyor.'
        elif User.query.filter_by(email=email).first():
            error = 'Bu e-posta adresi zaten kayıtlı.'

        if not error:
            user = User(email=email, full_name=full_name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            login_user(user, remember=True)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()

            # Ödeme akışı hazır olunca → url_for('payment.checkout') olacak
            return redirect(url_for('onboarding.index'))

    return render_template('auth/register.html', error=error)


# ── Giriş ────────────────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_smart_home_url())

    error = None

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            error = 'E-posta veya şifre hatalı.'
        else:
            login_user(user, remember=remember)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()

            # Onboarding tamamlanmamışsa direkt oraya gönder;
            # tamamlanmışsa next parametresi varsa oraya, yoksa feed'e
            ob = OnboardingData.query.filter_by(user_id=user.id).first()
            if not ob or not ob.is_complete:
                return redirect(url_for('onboarding.index'))

            next_page = request.args.get('next')
            return redirect(next_page or url_for('feed.index'))

    return render_template('auth/login.html', error=error)


# ── Çıkış ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))
