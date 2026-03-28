import os

from flask import Flask, send_from_directory, request, redirect, url_for
from dotenv import load_dotenv
from extensions import db, login_manager

load_dotenv()


def create_app():
    app = Flask(__name__)

    # ── Config ──────────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///alvera.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Upload klasörü: alvera/static/uploads/{user_id}/
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024   # 100 MB istek limiti

    # ── Extensions ──────────────────────────────────────────────────────────
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = None

    # ── Blueprints ───────────────────────────────────────────────────────────
    from blueprints.main import main_bp
    from blueprints.auth import auth_bp
    from blueprints.onboarding import onboarding_bp
    from blueprints.ai import ai_bp
    from blueprints.admin import admin_bp
    from blueprints.site import site_bp        # Yeni: Site yönetim hub'ı
    from blueprints.posts import posts_bp
    from blueprints.brand import brand_bp
    from blueprints.extras import extras_bp
    from blueprints.feed import feed_bp
    from blueprints.dm import dm_bp
    from blueprints.notifications import notif_bp
    from blueprints.mindmap import mindmap_bp
    from blueprints.flow import flow_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(admin_bp)           # Backward-compat /admin → /site/edit
    app.register_blueprint(site_bp)            # /site/ ve /site/edit
    app.register_blueprint(posts_bp)
    app.register_blueprint(brand_bp)
    app.register_blueprint(extras_bp)
    app.register_blueprint(feed_bp)
    app.register_blueprint(dm_bp)
    app.register_blueprint(notif_bp)
    app.register_blueprint(mindmap_bp)
    app.register_blueprint(flow_bp)

    # ── Onboarding Tamamlanma Koruyucu ────────────────────────────────────────
    # Bu before_request hook'u, authenticated kullanıcıların onboarding'i
    # tamamlamadan uygulamanın korumalı alanlarına erişmesini engeller.
    #
    # Muaf tutulan blueprint'ler:
    #   auth       → login / register / logout
    #   onboarding → onboarding akışının kendisi
    #   main       → landing page, public profil, discover, robots, sitemap
    #   admin      → admin paneli
    #   None       → doğrudan app'e kayıtlı route'lar (örn: /uploads/)
    _OB_EXEMPT = frozenset({'auth', 'onboarding', 'main', 'admin', None})

    @app.before_request
    def require_onboarding_complete():
        """
        Kimlik doğrulanmış ama onboarding'i tamamlamamış kullanıcıları
        /onboarding sayfasına yönlendirir.
        """
        from flask_login import current_user as _cu

        # Giriş yapılmamışsa → Flask-Login @login_required halleder
        if not _cu.is_authenticated:
            return

        # Muaf blueprint'ler ve static dosyalar
        if request.blueprint in _OB_EXEMPT:
            return
        if request.endpoint and request.endpoint.endswith('.static'):
            return

        # Onboarding kaydını kontrol et
        from models import OnboardingData as _OBD
        ob = _OBD.query.filter_by(user_id=_cu.id).first()
        if ob and ob.is_complete:
            return  # Tamamlanmış → normal akışa devam

        # Tamamlanmamış: AJAX/JSON istekler için JSON 403, diğerleri redirect
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify as _json
            return _json({
                'ok': False,
                'error': 'Onboarding tamamlanmadı.',
                'redirect': url_for('onboarding.index'),
            }), 403

        return redirect(url_for('onboarding.index'))

    # ── Uploads static route ─────────────────────────────────────────────────
    @app.route('/uploads/<int:user_id>/<path:filename>')
    def uploaded_file(user_id, filename):
        user_dir = os.path.join(upload_folder, str(user_id))
        return send_from_directory(user_dir, filename)

    # ── DB Init ─────────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()

        # ── İnkremental migrasyonlar ─────────────────────────────────────────
        # Mevcut tablolara yeni sütun eklemek için güvenli ALTER TABLE
        from sqlalchemy import text
        _migs = [
            # DMMessage — Aura mesaj tipi desteği
            "ALTER TABLE dm_messages ADD COLUMN msg_type VARCHAR(20) NOT NULL DEFAULT 'text'",
            "ALTER TABLE dm_messages ADD COLUMN meta_json TEXT",
            # Post — Kod bloğu dil etiketi
            "ALTER TABLE posts ADD COLUMN code_language VARCHAR(30)",
            # DMMessage — Alvera Direct yeni özellikler
            "ALTER TABLE dm_messages ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE dm_messages ADD COLUMN edited_at DATETIME",
            "ALTER TABLE dm_messages ADD COLUMN code_language VARCHAR(30)",
            # Post — Gizlilik için rastgele URL slug'ı
            "ALTER TABLE posts ADD COLUMN slug VARCHAR(16)",
        ]
        for _sql in _migs:
            try:
                db.session.execute(text(_sql))
                db.session.commit()
            except Exception:
                db.session.rollback()   # Sütun zaten varsa sessizce geç

        # Mevcut postlara slug backfill (slug NULL olanları doldur)
        import secrets as _secrets
        from models import Post as _Post
        _posts_without_slug = _Post.query.filter(_Post.slug == None).all()  # noqa: E711
        if _posts_without_slug:
            _existing_slugs = set(
                row[0] for row in db.session.execute(
                    text("SELECT slug FROM posts WHERE slug IS NOT NULL")
                ).fetchall()
            )
            for _p in _posts_without_slug:
                while True:
                    _s = _secrets.token_urlsafe(8)[:10]
                    if _s not in _existing_slugs:
                        _existing_slugs.add(_s)
                        _p.slug = _s
                        break
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
