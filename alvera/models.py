from datetime import datetime, timezone
import json

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name     = db.Column(db.String(120), nullable=True)

    is_active     = db.Column(db.Boolean, default=True,  nullable=False)
    has_paid      = db.Column(db.Boolean, default=False, nullable=False)

    # Paket: '1' = Sosyal (Ücretsiz — Alvera Social), '2' = Profil (Ücretli — kişisel site + sosyal)
    package       = db.Column(db.String(1), default='1', nullable=False)

    # Müsaitlik rozeti — profil sayfasında gösterilir
    is_available  = db.Column(db.Boolean, default=False, nullable=False)

    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime, nullable=True)

    # İlişkiler
    onboarding    = db.relationship('OnboardingData', backref='user', uselist=False)
    site          = db.relationship('Site', backref='owner', uselist=False)
    posts         = db.relationship('Post', backref='author', lazy='dynamic',
                                    foreign_keys='Post.user_id',
                                    order_by='Post.created_at.desc()')
    post_likes    = db.relationship('PostLike', backref='liker', lazy='dynamic',
                                    foreign_keys='PostLike.user_id')
    post_comments = db.relationship('PostComment', backref='commenter', lazy='dynamic',
                                    foreign_keys='PostComment.user_id')
    # Takip ilişkileri
    following     = db.relationship('Follow',
                                    foreign_keys='Follow.follower_id',
                                    backref=db.backref('follower_user', lazy='joined'),
                                    lazy='dynamic')
    followers     = db.relationship('Follow',
                                    foreign_keys='Follow.following_id',
                                    backref=db.backref('followed_user', lazy='joined'),
                                    lazy='dynamic')
    services      = db.relationship('Service',       backref='owner', lazy='dynamic',
                                    order_by='Service.order_index')
    portfolio     = db.relationship('PortfolioItem', backref='owner', lazy='dynamic',
                                    order_by='PortfolioItem.order_index')
    testimonials  = db.relationship('Testimonial',   backref='owner', lazy='dynamic',
                                    order_by='Testimonial.created_at.desc()')
    contact_msgs  = db.relationship('ContactMessage', backref='recipient', lazy='dynamic',
                                    order_by='ContactMessage.created_at.desc()')

    def is_following(self, user) -> bool:
        """Bu kullanıcı, verilen kullanıcıyı takip ediyor mu?"""
        return self.following.filter_by(following_id=user.id).first() is not None

    def follow_count(self) -> int:
        return self.following.count()

    def follower_count(self) -> int:
        return self.followers.count()

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.email}>'


class OnboardingData(db.Model):
    __tablename__ = 'onboarding_data'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    current_step = db.Column(db.Integer, default=0, nullable=False)

    # Adım 1 — Sen kimsin?
    profession_category = db.Column(db.String(80), nullable=True)   # Alan / kategori seçimi
    job_title    = db.Column(db.String(120), nullable=True)
    company      = db.Column(db.String(120), nullable=True)

    # Adım 2 — Kendini anlat
    bio          = db.Column(db.Text, nullable=True)

    # Adım 3 — Uzmanlık alanları (virgülle ayrılmış)
    skills       = db.Column(db.String(500), nullable=True)

    # Adım 4 — Ton / Vibe
    vibe         = db.Column(db.String(50), nullable=True)   # minimal | bold | warm

    # Adım 3 — Özgün Kimlik Sinyalleri (her sayfayı özgün kılan sorular)
    target_audience = db.Column(db.String(120), nullable=True)   # Kimler görmeli? (pill seçimi)
    achievement     = db.Column(db.Text,        nullable=True)   # En gurur duyulan an/başarı (≤250 karakter)
    differentiator  = db.Column(db.String(200), nullable=True)   # Rakiplerden ayıran özellik (≤180 karakter)

    # Adım 6 — Sosyal linkler  (eski Adım 5 — kaydırıldı)
    linkedin     = db.Column(db.String(255), nullable=True)
    github       = db.Column(db.String(255), nullable=True)
    twitter      = db.Column(db.String(255), nullable=True)
    website      = db.Column(db.String(255), nullable=True)

    # ── Paket 3 Ek Alanları ───────────────────────────────────────────────────
    # Adım 6 (P3) — Marka kimliği
    brand_name      = db.Column(db.String(120), nullable=True)   # Marka / şirket adı
    brand_type      = db.Column(db.String(60),  nullable=True)   # freelancer|ajans|danışman|startup
    brand_tagline   = db.Column(db.String(200), nullable=True)   # Kısa slogan

    # Adım 7 (P3) — Hizmetler (ham, AI şekillendirecek)
    services_raw    = db.Column(db.Text, nullable=True)          # Virgülle ayrılmış ham hizmet isimleri

    # Durum
    completed_at = db.Column(db.DateTime, nullable=True)
    updated_at   = db.Column(db.DateTime,
                             default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    def to_dict(self) -> dict:
        """AI prompt oluşturmak için tüm veriyi dict olarak döner."""
        return {
            'full_name':             self.user.full_name,
            'profession_category':  self.profession_category,
            'job_title':             self.job_title,
            'company':               self.company,
            'bio':              self.bio,
            'skills':           self.skills,
            'vibe':             self.vibe,
            # Özgün Kimlik Sinyalleri
            'target_audience':  self.target_audience,
            'achievement':      self.achievement,
            'differentiator':   self.differentiator,
            # Sosyal
            'linkedin':         self.linkedin,
            'github':           self.github,
            'twitter':          self.twitter,
            'website':          self.website,
            # Paket 3
            'brand_name':       self.brand_name,
            'brand_type':       self.brand_type,
            'brand_tagline':    self.brand_tagline,
            'services_raw':     self.services_raw,
            'package':          self.user.package,
        }

    def __repr__(self) -> str:
        return f'<OnboardingData user={self.user_id} step={self.current_step}>'


class Site(db.Model):
    """Kullanıcının seçtiği ve yayınladığı landing page içeriği."""
    __tablename__ = 'sites'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    slug            = db.Column(db.String(120), unique=True, nullable=False, index=True)

    # Seçilen varyant içeriği
    headline        = db.Column(db.String(200), nullable=True)
    tagline         = db.Column(db.String(300), nullable=True)
    bio_text        = db.Column(db.Text,        nullable=True)
    cta_text        = db.Column(db.String(100), nullable=True)
    skills_display  = db.Column(db.String(500), nullable=True)   # JSON liste
    vibe            = db.Column(db.String(50),  nullable=True)

    # Ham AI çıktısı
    raw_generation  = db.Column(db.Text, nullable=True)

    # Medya — profil fotoğrafı ve marka banner
    avatar_file     = db.Column(db.String(255), nullable=True)   # static/uploads/{id}/avatar.*
    cover_file      = db.Column(db.String(255), nullable=True)   # static/uploads/{id}/cover.*

    # Durum
    is_published    = db.Column(db.Boolean, default=False, nullable=False)
    chosen_variant  = db.Column(db.String(1), nullable=True)     # 'a' | 'b'
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f'<Site slug={self.slug} published={self.is_published}>'


class Post(db.Model):
    """Akış gönderisi — metin, proje lansmanı, resim veya kod bloğu."""
    __tablename__ = 'posts'

    # Gönderi tipleri
    TYPE_TEXT    = 'text'
    TYPE_PROJECT = 'project'
    TYPE_IMAGE   = 'image'
    TYPE_CODE    = 'code'
    TYPE_VIDEO   = 'video'
    VALID_TYPES  = {TYPE_TEXT, TYPE_PROJECT, TYPE_IMAGE, TYPE_CODE, TYPE_VIDEO}

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    post_type      = db.Column(db.String(20), default=TYPE_TEXT, nullable=False)  # text|project|image|code
    content        = db.Column(db.Text, nullable=False, default='')

    # Kod bloğu için dil etiketi (ör: 'python', 'javascript', 'sql')
    code_language  = db.Column(db.String(30), nullable=True)

    # Geriye dönük uyumluluk — link/collab gönderileri hâlâ okunabilsin
    link_url    = db.Column(db.String(500), nullable=True)
    link_title  = db.Column(db.String(200), nullable=True)

    media_files = db.Column(db.Text, nullable=True)   # JSON array (resim dosyaları)
    is_pinned   = db.Column(db.Boolean, default=False, nullable=False)

    # Rastgele URL slug — sıralı ID'yi gizlemek için (ör: "xK3mP9qR2a")
    slug        = db.Column(db.String(16), unique=True, index=True, nullable=True)

    # Gönderi kaynağı: 'social' = Sosyal Akış, 'site' = Site Dashboard güncelleme alanı
    # Bu alan iki bağlamın birbirini etkilememesini sağlar.
    source      = db.Column(db.String(16), default='social', nullable=False, index=True)

    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at  = db.Column(db.DateTime,
                            default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    # İlişkiler
    likes    = db.relationship('PostLike',    backref='post', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('PostComment', backref='post', lazy='dynamic', cascade='all, delete-orphan',
                                order_by='PostComment.created_at.asc()')
    yankas   = db.relationship('PostYanka',   backref='post', lazy='dynamic', cascade='all, delete-orphan')
    views    = db.relationship('PostView',    backref='post', lazy='dynamic', cascade='all, delete-orphan')
    saves    = db.relationship('SavedPost',   backref='post', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def like_count(self) -> int:
        return self.likes.count()

    @property
    def comment_count(self) -> int:
        return self.comments.count()

    @property
    def yanka_count(self) -> int:
        return self.yankas.count()

    @property
    def view_count(self) -> int:
        return self.views.count()

    def is_liked_by(self, user) -> bool:
        return self.likes.filter_by(user_id=user.id).first() is not None

    def is_yankaed_by(self, user) -> bool:
        return self.yankas.filter_by(user_id=user.id).first() is not None

    def is_saved_by(self, user) -> bool:
        return self.saves.filter_by(user_id=user.id).first() is not None

    @property
    def media_list(self) -> list:
        if not self.media_files:
            return []
        try:
            return json.loads(self.media_files)
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def has_media(self) -> bool:
        return bool(self.media_files)

    def to_dict(self) -> dict:
        return {
            'id':            self.id,
            'post_type':     self.post_type,
            'content':       self.content,
            'code_language': self.code_language,
            'media':         self.media_list,
            'like_count':    self.like_count,
            'comment_count': self.comment_count,
            'created_at':    self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f'<Post id={self.id} type={self.post_type} user={self.user_id}>'


class PostLike(db.Model):
    """Gönderi beğenisi."""
    __tablename__ = 'post_likes'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),)

    def __repr__(self) -> str:
        return f'<PostLike post={self.post_id} user={self.user_id}>'


class PostComment(db.Model):
    """Gönderi yorumu."""
    __tablename__ = 'post_comments'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content    = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self) -> str:
        return f'<PostComment id={self.id} post={self.post_id}>'


class PostYanka(db.Model):
    """
    Yankı — Geri alınamaz, kısıtlı sayıda verilen güçlü onay.

    Kurallar:
      • Bir kullanıcı aynı gönderiye sadece 1 Yankı verebilir (UniqueConstraint).
      • Günde en fazla 5 Yankı verilebilir (DAILY_LIMIT).
      • Yankı verildikten sonra geri alınamaz (Proof of Work mekanizması).
      • Yankı almış gönderiler feed algoritmasında daha yüksek öncelikle çıkar.
    """
    __tablename__ = 'post_yankas'

    DAILY_LIMIT = 5   # Günlük maksimum Yankı kotası

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_post_yanka'),)

    def __repr__(self) -> str:
        return f'<PostYanka post={self.post_id} user={self.user_id}>'


class Follow(db.Model):
    """Kullanıcı takip ilişkisi."""
    __tablename__ = 'follows'

    id           = db.Column(db.Integer, primary_key=True)
    follower_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    following_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('follower_id', 'following_id', name='uq_follow'),)

    def __repr__(self) -> str:
        return f'<Follow {self.follower_id}→{self.following_id}>'


class PostView(db.Model):
    """Kullanıcının gördüğü gönderi kaydı — görülmüş gönderiler tekrar çıkmaz."""
    __tablename__ = 'post_views'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    viewed_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_post_view'),)

    def __repr__(self) -> str:
        return f'<PostView post={self.post_id} user={self.user_id}>'


class SavedPost(db.Model):
    """Kullanıcının kaydettiği (bookmark) gönderi."""
    __tablename__ = 'saved_posts'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_saved_post'),)

    def __repr__(self) -> str:
        return f'<SavedPost post={self.post_id} user={self.user_id}>'


# ════════════════════════════════════════════════════════════════
#   PAKET 3 — Marka/Servis Modelleri
# ════════════════════════════════════════════════════════════════

class Service(db.Model):
    """Paket 3: Kullanıcının sunduğu hizmetler."""
    __tablename__ = 'services'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    title       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text,        nullable=True)   # AI tarafından zenginleştirilebilir
    price_range = db.Column(db.String(80),  nullable=True)   # "₺5.000 – ₺15.000" veya "Teklif alın"
    cta_label   = db.Column(db.String(60),  nullable=True,   default='İletişime Geç')
    order_index = db.Column(db.Integer,     default=0,        nullable=False)

    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'title':       self.title,
            'description': self.description,
            'price_range': self.price_range,
            'cta_label':   self.cta_label,
        }

    def __repr__(self) -> str:
        return f'<Service "{self.title}" user={self.user_id}>'


class PortfolioItem(db.Model):
    """Paket 3: Portföy / vaka çalışmaları."""
    __tablename__ = 'portfolio_items'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    title       = db.Column(db.String(160), nullable=False)
    problem     = db.Column(db.Text,        nullable=True)   # Problem / Bağlam
    solution    = db.Column(db.Text,        nullable=True)   # Yapılanlar
    result      = db.Column(db.Text,        nullable=True)   # Sonuç
    tags        = db.Column(db.String(300), nullable=True)   # JSON liste ["React","UX"]
    url         = db.Column(db.String(255), nullable=True)   # Canlı link
    cover_file  = db.Column(db.String(255), nullable=True)   # Upload edilen kapak resmi
    order_index = db.Column(db.Integer,     default=0,        nullable=False)

    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def tags_list(self) -> list:
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except Exception:
            return [t.strip() for t in self.tags.split(',') if t.strip()]

    def to_dict(self) -> dict:
        return {
            'id':       self.id,
            'title':    self.title,
            'problem':  self.problem,
            'solution': self.solution,
            'result':   self.result,
            'tags':     self.tags_list,
            'url':      self.url,
        }

    def __repr__(self) -> str:
        return f'<PortfolioItem "{self.title}" user={self.user_id}>'


class Testimonial(db.Model):
    """Paket 3: Müşteri referansları."""
    __tablename__ = 'testimonials'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    client_name  = db.Column(db.String(120), nullable=False)
    client_role  = db.Column(db.String(120), nullable=True)   # "Kurucu, Acme A.Ş."
    quote        = db.Column(db.Text,        nullable=False)
    rating       = db.Column(db.Integer,     default=5,        nullable=False)  # 1-5

    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'client_name': self.client_name,
            'client_role': self.client_role,
            'quote':       self.quote,
            'rating':      self.rating,
        }

    def __repr__(self) -> str:
        return f'<Testimonial from="{self.client_name}" user={self.user_id}>'


class ContactMessage(db.Model):
    """Paket 3: Profil üzerinden gelen iletişim mesajları (mini-CRM)."""
    __tablename__ = 'contact_messages'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Gönderen bilgileri
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(255), nullable=False)
    subject    = db.Column(db.String(200), nullable=True)
    message    = db.Column(db.Text,        nullable=False)

    # Hangi hizmete ilgi duyuldu (opsiyonel)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)

    is_read    = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    service    = db.relationship('Service', backref='inquiries')

    def __repr__(self) -> str:
        return f'<ContactMessage from={self.email} to_user={self.user_id}>'


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


# ════════════════════════════════════════════════════════════════
#   DM — Direkt Mesajlaşma Modelleri
# ════════════════════════════════════════════════════════════════

class DMConversation(db.Model):
    """İki kullanıcı arasındaki özel mesajlaşma konuşması."""
    __tablename__ = 'dm_conversations'

    id              = db.Column(db.Integer, primary_key=True)
    user1_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    user2_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    last_message_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # İlişkiler
    messages = db.relationship(
        'DMMessage', backref='conversation', lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='DMMessage.created_at.asc()',
    )
    user1 = db.relationship('User', foreign_keys=[user1_id], backref=db.backref('dm_convs_as_u1', lazy='dynamic'))
    user2 = db.relationship('User', foreign_keys=[user2_id], backref=db.backref('dm_convs_as_u2', lazy='dynamic'))

    __table_args__ = (db.UniqueConstraint('user1_id', 'user2_id', name='uq_dm_conv'),)

    def other_user(self, current_user_id: int):
        """Konuşmadaki diğer kullanıcıyı döner."""
        return self.user2 if self.user1_id == current_user_id else self.user1

    def unread_count(self, for_user_id: int) -> int:
        """Belirtilen kullanıcı için okunmamış mesaj sayısı."""
        return self.messages.filter_by(is_read=False).filter(
            DMMessage.sender_id != for_user_id
        ).count()

    def last_message(self):
        """En son mesajı döner."""
        return self.messages.order_by(DMMessage.created_at.desc()).first()

    def __repr__(self) -> str:
        return f'<DMConversation {self.user1_id}↔{self.user2_id}>'


class DMMessage(db.Model):
    """
    Direkt mesaj.
    msg_type: 'text' (varsayılan) | 'aura' | 'code'
    meta_json: Aura tipi mesajlarda analiz özeti (JSON string)
    """
    __tablename__ = 'dm_messages'

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('dm_conversations.id'), nullable=False, index=True)
    sender_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content         = db.Column(db.String(4000), nullable=False)
    msg_type        = db.Column(db.String(20), default='text', nullable=False)   # 'text' | 'aura' | 'code'
    code_language   = db.Column(db.String(30), nullable=True)                    # Kod tipi için dil
    meta_json       = db.Column(db.Text, nullable=True)                           # JSON — aura özeti
    is_read         = db.Column(db.Boolean, default=False, nullable=False)
    is_deleted      = db.Column(db.Boolean, default=False, nullable=False)
    edited_at       = db.Column(db.DateTime, nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    sender    = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_dms', lazy='dynamic'))
    reactions = db.relationship('DMReaction', backref='message', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def meta(self) -> dict:
        """meta_json'u dict olarak döner."""
        if not self.meta_json:
            return {}
        try:
            return json.loads(self.meta_json)
        except Exception:
            return {}

    def reaction_summary(self, current_user_id: int = None) -> list:
        """Tepki özetini döner: [{emoji, count, reacted_by_me}]"""
        from sqlalchemy import func
        rows = (
            db.session.query(DMReaction.emoji, func.count(DMReaction.id))
            .filter_by(message_id=self.id)
            .group_by(DMReaction.emoji)
            .all()
        )
        result = []
        for emoji, count in rows:
            reacted = False
            if current_user_id:
                reacted = DMReaction.query.filter_by(
                    message_id=self.id, user_id=current_user_id, emoji=emoji
                ).first() is not None
            result.append({'emoji': emoji, 'count': count, 'reacted_by_me': reacted})
        return result

    def __repr__(self) -> str:
        return f'<DMMessage conv={self.conversation_id} sender={self.sender_id} type={self.msg_type}>'


class DMReaction(db.Model):
    """Mesaj tepkisi — kullanıcı başına emoji."""
    __tablename__ = 'dm_reactions'

    id         = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('dm_messages.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    emoji      = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', 'emoji', name='uq_dm_reaction'),)


class AuraResult(db.Model):
    """
    İki kullanıcı arasındaki Aura analizinin cache'i.
    user_a_id < user_b_id kısıtıyla tutarlılık sağlanır.
    Bir çift için sadece bir kayıt bulunur; analiz tekrar yapılmaz.
    """
    __tablename__ = 'aura_results'

    id         = db.Column(db.Integer, primary_key=True)
    user_a_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    user_b_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    result_json = db.Column(db.Text, nullable=False)   # generate_aura_analysis() çıktısı
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('user_a_id', 'user_b_id', name='uq_aura_pair'),
    )

    user_a = db.relationship('User', foreign_keys=[user_a_id])
    user_b = db.relationship('User', foreign_keys=[user_b_id])

    @property
    def data(self) -> dict:
        try:
            return json.loads(self.result_json)
        except Exception:
            return {}

    @data.setter
    def data(self, value: dict) -> None:
        self.result_json = json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:
        return f'<AuraResult {self.user_a_id}↔{self.user_b_id}>'


class PageView(db.Model):
    """Profil sayfası ziyaret kaydı — analytics teaser için."""
    __tablename__ = 'page_views'

    id        = db.Column(db.Integer, primary_key=True)
    site_id   = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False, index=True)
    viewed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    referrer  = db.Column(db.String(500), nullable=True)  # ilerisi için

    def __repr__(self) -> str:
        return f'<PageView site={self.site_id} at={self.viewed_at}>'


# ── Opsiyonel Profil Genişletme ───────────────────────────────────────────────

class UserProfileExtras(db.Model):
    """Durum mesajı, CTA butonu ve çalışma tercihleri."""
    __tablename__ = 'user_profile_extras'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # "Şu An" Durum
    status_text     = db.Column(db.String(160), nullable=True)
    status_emoji    = db.Column(db.String(10),  nullable=True)

    # Öne Çıkan CTA Butonu
    cta_text        = db.Column(db.String(80),  nullable=True)
    cta_url         = db.Column(db.String(255), nullable=True)
    cta_enabled     = db.Column(db.Boolean, default=False, nullable=False)

    # Çalışma Tercihleri
    work_type       = db.Column(db.String(20),  nullable=True)  # remote|hybrid|onsite|esnek
    work_engagement = db.Column(db.String(30),  nullable=True)  # freelance|tam-zamanli|proje|danismanlik
    work_budget     = db.Column(db.String(50),  nullable=True)  # serbest metin: "₺5.000/ay+"

    updated_at = db.Column(db.DateTime,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f'<UserProfileExtras user={self.user_id}>'


class CareerEntry(db.Model):
    """Kariyer zaman çizelgesi girişi."""
    __tablename__ = 'career_entries'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    role          = db.Column(db.String(120), nullable=False)
    company       = db.Column(db.String(120), nullable=False)
    start_year    = db.Column(db.String(20),  nullable=False)   # "2020" veya "Mar 2020"
    end_year      = db.Column(db.String(20),  nullable=True)
    is_current    = db.Column(db.Boolean, default=False, nullable=False)
    description   = db.Column(db.String(300), nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    def to_dict(self):
        return {
            'id':          self.id,
            'role':        self.role,
            'company':     self.company,
            'start_year':  self.start_year,
            'end_year':    self.end_year,
            'is_current':  self.is_current,
            'description': self.description,
        }

    def __repr__(self) -> str:
        return f'<CareerEntry {self.role}@{self.company}>'


class CustomLink(db.Model):
    """Kullanıcı tanımlı özel linkler (Link Merkezi)."""
    __tablename__ = 'custom_links'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title         = db.Column(db.String(80),  nullable=False)
    url           = db.Column(db.String(255), nullable=False)
    emoji         = db.Column(db.String(10),  nullable=True)
    click_count   = db.Column(db.Integer, default=0, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    def to_dict(self):
        return {
            'id':          self.id,
            'title':       self.title,
            'url':         self.url,
            'emoji':       self.emoji,
            'click_count': self.click_count,
        }

    def __repr__(self) -> str:
        return f'<CustomLink "{self.title}" user={self.user_id}>'


# ════════════════════════════════════════════════════════════════
#   BİLDİRİM MODELİ
# ════════════════════════════════════════════════════════════════

class Notification(db.Model):
    """
    Kullanıcıya iletilen in-app bildirim.

    Türler:
      'like'    — gönderiniz beğenildi
      'comment' — gönderinize yorum yapıldı
      'follow'  — biri sizi takip etti
      'mention' — gönderi/yorumda mention edildınız
    """
    __tablename__ = 'notifications'

    # Türler — sabit liste
    TYPE_LIKE    = 'like'
    TYPE_COMMENT = 'comment'
    TYPE_FOLLOW  = 'follow'
    TYPE_MENTION = 'mention'
    TYPE_YANKA   = 'yanka'
    VALID_TYPES  = {TYPE_LIKE, TYPE_COMMENT, TYPE_FOLLOW, TYPE_MENTION, TYPE_YANKA}

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)  # alıcı
    actor_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)              # tetikleyen
    notif_type = db.Column(db.String(20), nullable=False)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='SET NULL'), nullable=True)
    is_read    = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # İlişkiler
    recipient = db.relationship('User', foreign_keys=[user_id],  backref=db.backref('notifications', lazy='dynamic'))
    actor     = db.relationship('User', foreign_keys=[actor_id], backref=db.backref('triggered_notifications', lazy='dynamic'))
    post      = db.relationship('Post', foreign_keys=[post_id])

    def __repr__(self) -> str:
        return f'<Notification {self.notif_type} → user={self.user_id}>'


# ════════════════════════════════════════════════════════════════
#   ZİHİN HARİTASI MODELİ
# ════════════════════════════════════════════════════════════════

class MindMap(db.Model):
    """
    Kullanıcının tüm platform verisinden AI ile üretilen Zihin Haritası.

    map_data JSON yapısı:
    {
        "nodes": [
            {
                "id":          "n1",
                "label":       "Ürün Tasarımcısı",
                "category":    "identity",   // identity | expertise | value | goal | interest
                "weight":      10,           // 1-10 — görsel büyüklük
                "description": "Kısa açıklama metni (tooltip)"
            }, ...
        ],
        "edges": [
            {
                "source":   "n1",
                "target":   "n2",
                "label":    "uzmanlık alanı",
                "strength": 0.8             // 0.0-1.0 — kenar kalınlığı
            }, ...
        ],
        "central_node": "n1"               // en merkezi / ağırlıklı düğüm
    }
    """
    __tablename__ = 'mind_maps'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'),
                             unique=True, nullable=False, index=True)
    map_data     = db.Column(db.Text, nullable=True)   # JSON string
    version      = db.Column(db.Integer, default=1, nullable=False)
    generated_at = db.Column(db.DateTime,
                             default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    # İlişkiler
    owner = db.relationship('User', backref=db.backref('mind_map', uselist=False))

    @property
    def data(self) -> dict | None:
        """map_data JSON stringini dict'e çevirir."""
        if not self.map_data:
            return None
        try:
            return json.loads(self.map_data)
        except (json.JSONDecodeError, TypeError):
            return None

    @data.setter
    def data(self, value: dict) -> None:
        """Dict'i JSON stringe çevirir ve map_data'ya yazar."""
        self.map_data = json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:
        return f'<MindMap user={self.user_id} v={self.version}>'


# ════════════════════════════════════════════════════════════════
#   FLOW — Keşif & Öneri Katmanı (PRISM Algoritması)
# ════════════════════════════════════════════════════════════════

class FlowSignal(db.Model):
    """
    Kullanıcının Flow akışındaki davranışsal izleri.
    signal_type: 'view_short'|'view_long'|'expand'|'profile_visit'|'less_like_this'|'skip'
    context: 'flow'|'feed'|'search'
    """
    __tablename__ = 'flow_signals'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    post_id     = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    signal_type = db.Column(db.String(30), nullable=False)
    value       = db.Column(db.Float, default=0.0, nullable=False)
    context     = db.Column(db.String(20), default='flow', nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship('User', backref=db.backref('flow_signals', lazy='dynamic'))
    post = db.relationship('Post', backref=db.backref('flow_signals', lazy='dynamic'))

    def __repr__(self):
        return f'<FlowSignal user={self.user_id} post={self.post_id} type={self.signal_type}>'


class UserInterestProfile(db.Model):
    """
    Kullanıcının ilgi alanı vektörü — PRISM algoritması için cache katmanı.
    interest_json: {"python":0.87, "design":0.62, "startup":0.45, ...}
    content_mix: {"code":0.4, "text":0.3, "image":0.2, "video":0.1}
    """
    __tablename__ = 'user_interest_profiles'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False, index=True)
    interest_json = db.Column(db.Text, nullable=True)    # {"tag": score, ...}
    content_mix   = db.Column(db.Text, nullable=True)    # {"code":0.4, ...}
    last_updated  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    signal_count  = db.Column(db.Integer, default=0, nullable=False)

    user = db.relationship('User', backref=db.backref('interest_profile', uselist=False))

    @property
    def interests(self) -> dict:
        if not self.interest_json:
            return {}
        try:
            return json.loads(self.interest_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @interests.setter
    def interests(self, value: dict):
        self.interest_json = json.dumps(value, ensure_ascii=False)

    @property
    def mix(self) -> dict:
        if not self.content_mix:
            return {}
        try:
            return json.loads(self.content_mix)
        except (json.JSONDecodeError, TypeError):
            return {}

    @mix.setter
    def mix(self, value: dict):
        self.content_mix = json.dumps(value, ensure_ascii=False)

    def __repr__(self):
        return f'<UserInterestProfile user={self.user_id} signals={self.signal_count}>'


class PostFlowScore(db.Model):
    """
    Gönderi bazlı PRISM skor cache'i — her 2 saatte yenilenir.
    semantic_tags: JSON list → ["python","backend","open-source"]
    """
    __tablename__ = 'post_flow_scores'

    id             = db.Column(db.Integer, primary_key=True)
    post_id        = db.Column(db.Integer, db.ForeignKey('posts.id'), unique=True, nullable=False, index=True)
    quality_score  = db.Column(db.Float, default=0.0, nullable=False)
    trend_velocity = db.Column(db.Float, default=0.0, nullable=False)
    semantic_tags  = db.Column(db.Text, nullable=True)   # JSON list
    computed_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at     = db.Column(db.DateTime, nullable=True, index=True)

    post = db.relationship('Post', backref=db.backref('flow_score', uselist=False))

    @property
    def tags(self) -> list:
        if not self.semantic_tags:
            return []
        try:
            return json.loads(self.semantic_tags)
        except (json.JSONDecodeError, TypeError):
            return []

    @tags.setter
    def tags(self, value: list):
        self.semantic_tags = json.dumps(value, ensure_ascii=False)

    def __repr__(self):
        return f'<PostFlowScore post={self.post_id} quality={self.quality_score:.2f}>'


class VideoView(db.Model):
    """
    Video gönderisi izleme verisi — en güçlü PRISM sinyali.
    """
    __tablename__ = 'video_views'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    post_id       = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    watch_seconds = db.Column(db.Integer, default=0, nullable=False)
    total_seconds = db.Column(db.Integer, default=0, nullable=False)
    watch_ratio   = db.Column(db.Float, default=0.0, nullable=False)
    replayed      = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship('User', backref=db.backref('video_views', lazy='dynamic'))
    post = db.relationship('Post', backref=db.backref('video_views', lazy='dynamic'))

    def __repr__(self):
        return f'<VideoView user={self.user_id} post={self.post_id} ratio={self.watch_ratio:.2f}>'
