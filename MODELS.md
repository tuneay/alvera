# Alvera — Veritabanı Modelleri Referansı

> **Dosya:** `alvera/models.py` (1012 satır)  
> **Veritabanı:** SQLite (`instance/alvera.db`) — Üretimde PostgreSQL

---

## Model Haritası

```
CORE
├── User                    → Tüm kullanıcılar
├── OnboardingData          → Profil kurulum verisi
└── Site                    → Yayınlanan kişisel site

SOSYAL AKIş
├── Post                    → Gönderiler (text/project/image/code/video)
├── PostLike                → Beğeniler
├── PostComment             → Yorumlar
├── PostYanka               → Yankı (güçlü, geri alınamaz onay — günde max 5)
├── PostView                → Görüntülenme kaydı
└── SavedPost               → Kaydedilen gönderiler (bookmark)

SOSYAL GRAf
└── Follow                  → Takip ilişkileri

DİREKT MESAJLAŞMA (DM)
├── DMConversation          → İki kullanıcı arası konuşma
├── DMMessage               → Mesajlar (text/aura/code tipleri)
└── DMReaction              → Emoji tepkiler

MARKA & SİTE (Paket 2)
├── Service                 → Sunulan hizmetler
├── PortfolioItem           → Portföy / vaka çalışmaları
├── Testimonial             → Müşteri referansları
└── ContactMessage          → İletişim formu mesajları (mini-CRM)

PROFİL UZANTILARI
├── UserProfileExtras       → Durum mesajı, CTA butonu, çalışma tercihleri
├── CareerEntry             → Kariyer zaman çizelgesi
└── CustomLink              → Özel link merkezi

ANALİTİK
└── PageView                → Profil sayfası ziyaret kaydı

BİLDİRİM
└── Notification            → In-app bildirimler (like/comment/follow/mention/yanka)

AI & KİMLİK
├── MindMap                 → AI ile üretilen zihin haritası
└── AuraResult              → İki kullanıcı arası Aura analizi cache'i

FLOW / PRISM ALGORİTMASI
├── FlowSignal              → Davranışsal etkileşim izleri
├── UserInterestProfile     → Kullanıcı ilgi vektörü (cache)
├── PostFlowScore           → Gönderi PRISM skor cache'i
└── VideoView               → Video izleme verisi
```

---

## Detaylı Model Açıklamaları

### `User`
**Tablo:** `users`

| Sütun | Tip | Açıklama |
|-------|-----|----------|
| `id` | Integer PK | — |
| `email` | String(255) unique | Giriş e-postası |
| `password_hash` | String(255) | werkzeug hash |
| `full_name` | String(120) | Görünen ad |
| `is_active` | Boolean | Hesap aktifliği |
| `has_paid` | Boolean | Ödeme durumu |
| `package` | String(1) | `'1'` = Sosyal (ücretsiz), `'2'` = Profil (ücretli) |
| `is_available` | Boolean | Müsaitlik rozeti |
| `created_at` | DateTime | — |
| `last_login_at` | DateTime | Son oturum zamanı |

**Metotlar:** `is_following()`, `follow_count()`, `follower_count()`, `set_password()`, `check_password()`

---

### `OnboardingData`
**Tablo:** `onboarding_data`

7 adımlı profil kurulum sihirbazının verilerini tutar.

| Adım | Alan | Açıklama |
|------|------|----------|
| 1 | `profession_category`, `job_title`, `company` | Kim kimsin? |
| 2 | `bio` | Kendi anlatımı |
| 3 | `skills`, `target_audience`, `achievement`, `differentiator` | Uzmanlık + Kimlik sinyalleri |
| 4 | `vibe` | Ton tercihi: `minimal` / `bold` / `warm` |
| 5 | `linkedin`, `github`, `twitter`, `website` | Sosyal linkler |
| 6 (P2) | `brand_name`, `brand_type`, `brand_tagline` | Marka kimliği |
| 7 (P2) | `services_raw` | Ham hizmet listesi |

**`is_complete` property:** `completed_at` NOT NULL ise `True`

---

### `Site`
**Tablo:** `sites`

AI tarafından üretilmiş ve kullanıcının seçtiği landing page içeriği.

| Sütun | Açıklama |
|-------|----------|
| `slug` | URL kimliği (örn: `john-doe`) |
| `headline` | AI üretimi başlık |
| `tagline` | Alt başlık |
| `bio_text` | Kişisel anlatı |
| `cta_text` | Call-to-action butonu metni |
| `skills_display` | JSON liste — gösterilen yetenekler |
| `vibe` | Seçilen ton |
| `avatar_file` / `cover_file` | Upload yolları |
| `is_published` | Yayında mı? |
| `chosen_variant` | `'a'` veya `'b'` — AI varyantı |

---

### `Post`
**Tablo:** `posts`

| Post Tipi | Sabit | Açıklama |
|-----------|-------|----------|
| `text` | `TYPE_TEXT` | Yazılı gönderi |
| `project` | `TYPE_PROJECT` | Proje lansmanı |
| `image` | `TYPE_IMAGE` | Fotoğraf gönderisi |
| `code` | `TYPE_CODE` | Sözdizimi renkli kod bloğu |
| `video` | `TYPE_VIDEO` | Kısa video (max 90sn) |

**Önemli Alanlar:**
- `slug` — Rastgele 10 karakterlik URL (ID gizleme)
- `source` — `'social'` veya `'site'` (iki bağlamı ayırır)
- `code_language` — Kod bloğu için dil etiketi
- `media_files` — JSON array (resim dosyaları)

---

### `PostYanka`
**Tablo:** `post_yankas`

> Yankı, beğeniden daha güçlü ve kısıtlı bir onay mekanizmasıdır.

- **Günlük limit:** 5 Yankı (kişi başı) — `DAILY_LIMIT = 5`
- **Geri alınamaz** — Proof of Work mekanizması
- Feed algoritmasında Yankı almış gönderiler daha yüksek öncelik alır

---

### `DMMessage`
**Tablo:** `dm_messages`

| `msg_type` | Açıklama |
|-----------|----------|
| `text` | Sıradan metin mesajı |
| `aura` | Aura analizi paylaşımı (meta_json ile) |
| `code` | Sözdizimi renkli kod bloğu |

---

### `MindMap`
**Tablo:** `mind_maps`

AI tarafından kullanıcının tüm platform verisinden üretilen kimlik grafiği.

```json
{
  "nodes": [
    {
      "id": "n1",
      "label": "Ürün Tasarımcısı",
      "category": "identity",  // identity|expertise|value|goal|interest
      "weight": 10,
      "description": "Kısa açıklama"
    }
  ],
  "edges": [
    {
      "source": "n1",
      "target": "n2",
      "label": "güçlendirir",
      "strength": 0.8
    }
  ],
  "central_node": "n1"
}
```

---

### `AuraResult`
**Tablo:** `aura_results`

İki kullanıcı arasındaki Aura uyum analizi. `user_a_id < user_b_id` kısıtıyla tutarlılık sağlanır.

---

### Flow / PRISM Modelleri

| Model | Tablo | Açıklama |
|-------|-------|----------|
| `FlowSignal` | `flow_signals` | Davranışsal iz — `view_short`, `view_long`, `expand`, `profile_visit`, `less_like_this`, `skip` |
| `UserInterestProfile` | `user_interest_profiles` | İlgi vektörü cache — `interest_json` + `content_mix` |
| `PostFlowScore` | `post_flow_scores` | Gönderi kalite + trend skoru — 2 saatte bir yenilenir |
| `VideoView` | `video_views` | `watch_seconds`, `watch_ratio`, `replayed` |

---

### `Notification`
**Tablo:** `notifications`

| `notif_type` | Tetikleyici |
|-------------|-------------|
| `like` | Gönderiniz beğenildi |
| `comment` | Gönderinize yorum yapıldı |
| `follow` | Biri sizi takip etti |
| `mention` | Mention edildınız |
| `yanka` | Gönderinize Yankı verildi |

---

## İlişki Diyagramı (Özet)

```
User ──1:1── OnboardingData
User ──1:1── Site
User ──1:1── MindMap
User ──1:1── UserInterestProfile
User ──1:1── UserProfileExtras
User ──1:N── Post
User ──1:N── PostLike
User ──1:N── PostComment
User ──1:N── PostYanka
User ──1:N── Follow (follower / following)
User ──1:N── DMConversation (user1 / user2)
User ──1:N── Service
User ──1:N── PortfolioItem
User ──1:N── Testimonial
User ──1:N── CareerEntry
User ──1:N── CustomLink
User ──1:N── Notification
User ──M:N── AuraResult (user_a / user_b)

Post ──1:N── PostLike
Post ──1:N── PostComment
Post ──1:N── PostYanka
Post ──1:N── PostView
Post ──1:N── SavedPost
Post ──1:N── FlowSignal
Post ──1:1── PostFlowScore

DMConversation ──1:N── DMMessage
DMMessage ──1:N── DMReaction
```
