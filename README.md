# Alvera — Dijital Kimlik & Sosyal Platform

> **Alvera**, profesyonellerin dijital kimliğini keşfetmesini, kişisel landing page oluşturmasını ve bir sosyal ağda bağlantı kurmasını sağlayan **yapay zeka destekli** bir platformdur.

---

## 🚀 Genel Bakış

Alvera iki ana katmandan oluşur:

| Katman | Açıklama |
|--------|----------|
| **Alvera Profil** | AI ile üretilen personal landing page (kişisel site) |
| **Alvera Social** | LinkedIn benzeri sosyal akış + keşif algoritması |

---

## 🏗️ Mimari Özet

```
AlveraStat/
├── alvera/                    # Ana Flask uygulaması
│   ├── app.py                 # Uygulama fabrikası (create_app)
│   ├── extensions.py          # SQLAlchemy + Flask-Login
│   ├── models.py              # 20+ veritabanı modeli
│   ├── blueprints/            # 13 Blueprint (route katmanı)
│   ├── services/
│   │   └── ai_service.py      # Groq/LLAMA AI fonksiyonları
│   ├── templates/             # Jinja2 HTML şablonları
│   └── static/                # CSS, JS, uploads
└── FLOW_ALGORITHM_PLAN.md     # Flow/PRISM algoritması planı
```

---

## ⚙️ Teknoloji Yığını

| Bileşen | Teknoloji |
|---------|-----------|
| Backend | Python 3.12 + Flask 3.0.3 |
| ORM | Flask-SQLAlchemy 3.1.1 |
| Kimlik Doğrulama | Flask-Login 0.6.3 |
| Veritabanı | SQLite (geliştirme), PostgreSQL (üretim) |
| AI | Groq API + LLAMA 3.3-70b / 3.1-8b |
| Ödeme | iyzipay |
| Frontend | Vanilla HTML + CSS + JavaScript (Jinja2) |

---

## 📦 Kurulum

```bash
# 1. Repoyu klonla
git clone <repo-url>
cd AlveraStat/alvera

# 2. Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Bağımlılıkları yükle
pip install -r requirements.txt

# 4. Ortam değişkenlerini ayarla
# .env dosyası oluştur:
# SECRET_KEY=your-secret-key
# GROQ_API_KEY=your-groq-api-key

# 5. Uygulamayı başlat
python app.py
```

---

## 🌐 Temel Sayfalar & Rotalar

| Sayfa | URL | Blueprint |
|-------|-----|-----------|
| Landing (Ana) | `/` | `main` |
| Kayıt / Giriş | `/auth/register`, `/auth/login` | `auth` |
| Onboarding | `/onboarding` | `onboarding` |
| Sosyal Akış | `/feed` | `feed` |
| Flow / Keşif | `/flow` | `flow` |
| Profil | `/@<slug>` | `main` |
| DM | `/dm` | `dm` |
| MindMap | `/mindmap` | `mindmap` |
| Bildirimler | `/notifications` | `notifications` |
| Site Yönetimi | `/site` | `site` |
| Admin | `/admin` | `admin` |

---

## 📄 Dokümantasyon Dosyaları

| Dosya | İçerik |
|-------|--------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Sistem mimarisi & akış diyagramı |
| [MODELS.md](./MODELS.md) | Veritabanı modelleri referansı |
| [AI_SYSTEM.md](./AI_SYSTEM.md) | AI servis fonksiyonları dokümantasyonu |
| [BLUEPRINTS.md](./BLUEPRINTS.md) | Blueprint'ler & endpoint listesi |
| [FLOW_ALGORITHM_PLAN.md](./FLOW_ALGORITHM_PLAN.md) | PRISM keşif algoritması planı |

---

## 🔑 Ortam Değişkenleri

| Değişken | Açıklama | Zorunlu |
|----------|----------|---------|
| `SECRET_KEY` | Flask session şifreleme anahtarı | ✅ |
| `GROQ_API_KEY` | Groq AI API anahtarı | ✅ |

---

## 👤 Kullanıcı Paketleri

| Paket | Kod | Özellikler |
|-------|-----|-----------|
| Sosyal (Ücretsiz) | `'1'` | Sosyal akış, profil sayfası, DM, Flow |
| Profil (Ücretli) | `'2'` | + AI kişisel site, portföy, testimonial, marka sayfası |
