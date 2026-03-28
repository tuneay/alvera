# Alvera — Blueprint & Endpoint Referansı

> Alvera, her biri kendi sorumluluk alanını yöneten **13 Flask Blueprint**'e sahiptir.

---

## Blueprint Listesi

| Blueprint | URL Prefix | Dosya | Açıklama |
|-----------|-----------|-------|----------|
| `main_bp` | `/` | `blueprints/main.py` | Landing, public profil, discover, robots, sitemap |
| `auth_bp` | `/auth` | `blueprints/auth.py` | Kayıt, giriş, çıkış |
| `onboarding_bp` | `/onboarding` | `blueprints/onboarding.py` | 7 adımlı profil sihirbazı |
| `feed_bp` | `/feed` | `blueprints/feed.py` | Sosyal akış (44 KB — en büyük blueprint) |
| `flow_bp` | `/flow` | `blueprints/flow.py` | PRISM keşif algoritması (39 KB) |
| `dm_bp` | `/dm` | `blueprints/dm.py` | Direkt mesajlaşma (21 KB) |
| `ai_bp` | `/ai` | `blueprints/ai.py` | AI işlemler (landing, mindmap, aura) |
| `mindmap_bp` | `/mindmap` | `blueprints/mindmap.py` | Zihin haritası (17 KB) |
| `site_bp` | `/site` | `blueprints/site.py` | Kişisel site yönetimi (9 KB) |
| `brand_bp` | `/brand` | `blueprints/brand.py` | Marka profil yönetimi (15 KB) |
| `notif_bp` | `/notifications` | `blueprints/notifications.py` | Bildirimler |
| `posts_bp` | `/posts` | `blueprints/posts.py` | Gönderi detay ve yönetimi |
| `extras_bp` | `/extras` | `blueprints/extras.py` | Profil ek özellikleri |
| `admin_bp` | `/admin` | `blueprints/admin.py` | Admin paneli |

---

## `/auth` — Kimlik Doğrulama

| Method | URL | Fonksiyon | Açıklama |
|--------|-----|-----------|----------|
| GET/POST | `/auth/register` | `register()` | Yeni kullanıcı kaydı |
| GET/POST | `/auth/login` | `login()` | Giriş |
| GET | `/auth/logout` | `logout()` | Çıkış |

**Akış:**
- Başarılı kayıt → `/onboarding`
- Başarılı giriş → `/onboarding` (tamamlanmamış) veya `/feed`

---

## `/onboarding` — Profil Kurulum Sihirbazı

7 aşamalı akış. Her adım ayrı AJAX veya form submit ile kaydedilir.

| Adım | İçerik |
|------|--------|
| 1 | Kategori + Unvan + Şirket |
| 2 | Bio metni |
| 3 | Yetenekler + Kimlik sinyalleri (target_audience, achievement, differentiator) |
| 4 | Vibe seçimi (minimal / bold / warm) |
| 5 | Sosyal medya linkleri |
| 6 (P2) | Marka kimliği |
| 7 (P2) | Hizmet listesi |

---

## `/feed` — Sosyal Akış

Alvera'nın en kapsamlı blueprint'i.

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/feed` | Ana akış sayfası |
| POST | `/feed/post` | Yeni gönderi oluştur |
| POST | `/feed/post/<id>/like` | Beğen / Beğeniyi geri al |
| POST | `/feed/post/<id>/comment` | Yorum ekle |
| POST | `/feed/post/<id>/yanka` | Yankı ver (günlük max 5) |
| POST | `/feed/post/<id>/save` | Kaydet / Kayıttan çıkar |
| DELETE | `/feed/post/<id>` | Gönderi sil |
| GET | `/feed/@<slug>` | Kullanıcı profil sayfası |
| POST | `/feed/follow/<user_id>` | Takip et / Takibi bırak |
| GET | `/feed/saved` | Kaydedilen gönderiler |
| GET | `/feed/generate` | AI içerik önerisi sayfası |

---

## `/flow` — Keşif (PRISM Algoritması)

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/flow/` | Flow sayfası (HTML) |
| GET | `/flow/posts` | PRISM skorlu gönderi listesi (JSON, sayfalanmış) |
| POST | `/flow/signal` | Batch davranış sinyali yazma |
| GET | `/flow/why/<post_id>` | AI açıklama — "Neden bu içerik?" |
| POST | `/flow/less-like` | "Daha az göster" işareti |
| GET | `/flow/trending-topics` | Yükselen konular widget |
| POST | `/flow/tag-post/<post_id>` | İçerik tagger (admin/cron) |
| POST | `/flow/update-interest` | İlgi profili yenile |

**PRISM Algoritması Bileşenleri:**

| Bileşen | Ağırlık | Açıklama |
|---------|---------|----------|
| RelevanceScore (w1) | 0.35 | İlgi alanına uyum (cosine similarity) |
| QualityScore (w2) | 0.25 | Normalize edilmiş etkileşim |
| SocialProofScore (w3) | 0.20 | Takip edilenlerden gelen onay |
| FreshnessScore (w4) | 0.15 | Zamansal çürüme |
| DiversityBonus (w5) | 0.05 | İçerik çeşitlilik bonusu |

---

## `/dm` — Direkt Mesajlaşma

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/dm` | Konuşma listesi |
| GET | `/dm/<conv_id>` | Konuşma açık |
| POST | `/dm/<conv_id>/send` | Mesaj gönder |
| POST | `/dm/<conv_id>/message/<msg_id>/react` | Emoji tepki |
| DELETE | `/dm/<conv_id>/message/<msg_id>` | Mesaj sil |
| PUT | `/dm/<conv_id>/message/<msg_id>/edit` | Mesaj düzenle |
| POST | `/dm/new/<user_id>` | Yeni konuşma başlat |

**Mesaj Tipleri:** `text`, `aura`, `code`

---

## `/ai` — AI İşlemler

| Method | URL | Açıklama |
|--------|-----|----------|
| POST | `/ai/generate` | Landing page varyantları üret |
| POST | `/ai/choose-variant` | Varyant seç ve kaydet |
| POST | `/ai/expand-text` | Kısa metni genişlet |
| POST | `/ai/refresh-bio` | Bio yenile |
| POST | `/ai/mindmap/generate` | Zihin haritası üret |
| GET | `/ai/aura/<user_id>` | Aura analizi görüntüle |
| POST | `/ai/aura/<user_id>/generate` | Aura analizi üret |

---

## `/mindmap` — Zihin Haritası

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/mindmap` | Kendi zihin haritasını görüntüle |
| GET | `/mindmap/<user_id>` | Başkasının zihin haritasını görüntüle |
| POST | `/mindmap/generate` | AI ile yeniden üret |

---

## `/site` — Kişisel Site Yönetimi

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/site` | Site yönetim hub'ı |
| GET | `/site/edit` | Site içeriği düzenleme |
| POST | `/site/publish` | Yayınla / yayından çıkar |
| POST | `/site/upload/avatar` | Profil fotoğrafı yükle |
| POST | `/site/upload/cover` | Kapak görseli yükle |

---

## `/brand` — Marka Profil

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/brand` | Marka sayfası özet |
| POST | `/brand/service/add` | Hizmet ekle |
| PUT | `/brand/service/<id>` | Hizmet güncelle |
| DELETE | `/brand/service/<id>` | Hizmet sil |
| POST | `/brand/portfolio/add` | Portföy kalemi ekle |
| POST | `/brand/testimonial/add` | Referans ekle |

---

## `/extras` — Profil Uzantıları

| Method | URL | Açıklama |
|--------|-----|----------|
| POST | `/extras/status` | Durum mesajı güncelle |
| POST | `/extras/cta` | CTA butonu güncelle |
| POST | `/extras/work-prefs` | Çalışma tercihleri güncelle |
| POST | `/extras/career/add` | Kariyer girişi ekle |
| POST | `/extras/links/add` | Özel link ekle |

---

## Onboarding Koruyucu (Global)

```python
# app.py — @app.before_request
_OB_EXEMPT = frozenset({'auth', 'onboarding', 'main', 'admin', None})

def require_onboarding_complete():
    # Onboarding tamamlanmamışsa korumalı blueprint'lere erişimi engeller
    # AJAX istekler → JSON 403
    # Normal istekler → /onboarding redirect
```
