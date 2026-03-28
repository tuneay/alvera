# ✦ Alvera Flow — Keşif Sayfası & Öneri Algoritması
## Mimari Plan v1.0 | 27 Mart 2026

---

## 1. Vizyon & Felsefe

**Flow**, Alvera Social'ın "seni sana ait olmayan ama sana hitap eden içeriklerle buluşturan" keşif katmanıdır. Klasik bir "trending" sayfası değil; her kullanıcı için farklı biçimde şekillenen, **canlı, öğrenen ve kişiselleşen** bir akış.

Tasarım felsefesi üç ilkeye dayanır:

- **Relevance > Recency:** Yeni olmak tek başına yeterli değil. İçerik sana uygunsa öne çıkar.
- **Diversity Guard:** Algoritma yankı odası yaratmaz. Kasıtlı olarak kenar alanlara çeker.
- **Transparent Signals:** Kullanıcı hangi sinyalin onu nereye götürdüğünü anlayabilir.

---

## 2. İçerik Tipleri (Flow'a Eklenecekler)

Mevcut post tipleri (`text`, `project`, `image`, `code`) korunur.
Flow için şu tipler **eklenir:**

| Tip | Açıklama | Yeni mi? |
|---|---|---|
| `text` | Yazılı gönderi | Mevcut |
| `project` | Proje lansmanı | Mevcut |
| `image` | Fotoğraf gönderisi | Mevcut |
| `code` | Kod bloğu | Mevcut |
| `video` | Kısa video (max 90sn, mp4/webm) | **YENİ** |
| `article` | Uzun form yazı (başlık + body, markdown) | **YENİ** |
| `poll` | Anket (2-4 seçenek) | **YENİ** |

> **Öncelik:** Algoritma video tipi için ayrı bir skor katmanı kullanır çünkü izlenme süresi (watch_duration) en güçlü sinyal.

---

## 3. Sinyal Mimarisi — Ne Topluyoruz?

### 3.1 Açık (Explicit) Sinyaller
Kullanıcının bilinçli yaptığı eylemler.

| Sinyal | Ağırlık | Kaynak |
|---|---|---|
| Like (❤️) | +10 | `PostLike` |
| Yanka / Repost | +15 | `PostYanka` |
| Kaydet | +20 | `SavedPost` |
| Yorum yaz | +12 | `PostComment` |
| "Daha az göster" | -25 | **Yeni: `FlowSignal`** |
| Kişiyi takip et (posttan) | +30 | `Follow` |
| Profil ziyareti (posttan) | +8 | **Yeni: `FlowSignal`** |

### 3.2 Örtük (Implicit) Sinyaller
Kullanıcının bilinçsizce bıraktığı izler.

| Sinyal | Ağırlık | Nasıl? |
|---|---|---|
| Görüntüleme süresi (>5sn) | +3 | `PostView` + JS timestamp |
| Görüntüleme süresi (>15sn) | +6 | `PostView` extended |
| Video izleme oranı >50% | +15 | **Yeni: `VideoView`** |
| Video izleme oranı >80% | +25 | **Yeni: `VideoView`** |
| Kaydırma (skip < 1sn) | -2 | JS IntersectionObserver |
| Gönderiyi genişletme (expand) | +5 | **Yeni: `FlowSignal`** |
| Yorum okuma (scroll içinde) | +4 | JS scroll event |

### 3.3 Pasif Kimlik Sinyalleri
Kullanıcının kim olduğuna dair statik veri.

| Sinyal | Kaynak |
|---|---|
| Meslek kategorisi | `OnboardingData.profession_category` |
| Yetenekler / Skill'ler | `OnboardingData.skills` |
| Vibe tercihi | `OnboardingData.vibe` |
| MindMap konuları | `MindMap` (varsa) |
| Aura eşleşmeleri | `AuraResult` (kimlerle yüksek skor) |
| Takip edilen kullanıcıların kategorileri | `Follow` → `OnboardingData` |

---

## 4. Yeni Veritabanı Modelleri

### 4.1 `FlowSignal` — Davranışsal İz
```python
class FlowSignal(db.Model):
    id          = Integer PK
    user_id     = FK → users
    post_id     = FK → posts
    signal_type = String(30)   # 'view_short'|'view_long'|'expand'|'profile_visit'|'less_like_this'|'skip'
    value       = Float        # normalleştirilmiş ağırlık
    context     = String(20)   # 'flow'|'feed'|'search'  (nereden geldi?)
    created_at  = DateTime
```

### 4.2 `UserInterestProfile` — Kullanıcı İlgi Vektörü (Cache)
```python
class UserInterestProfile(db.Model):
    id              = Integer PK
    user_id         = FK → users (unique)
    interest_json   = Text    # {"python":0.87, "design":0.62, "startup":0.45, ...}
    topic_vector    = Text    # JSON list[float] — embedding (1536 dim, OpenAI veya Groq)
    content_mix     = Text    # {"code":0.4, "text":0.3, "image":0.2, "video":0.1}
    last_updated    = DateTime
    signal_count    = Integer # kaç sinyal işlendikten sonra güncellendi
```

### 4.3 `PostFlowScore` — Gönderi Skor Cache'i
```python
class PostFlowScore(db.Model):
    id              = Integer PK
    post_id         = FK → posts (unique)
    quality_score   = Float   # beğeni oranı × takipçi-normalize
    trend_velocity  = Float   # son 2 saatte etkileşim artış hızı
    semantic_tags   = Text    # JSON list: ["python","backend","open-source"]
    embedding       = Text    # JSON float list (içerik vektörü)
    computed_at     = DateTime
    expires_at      = DateTime   # TTL: 2 saat
```

### 4.4 `VideoView` — Video İzleme Verisi
```python
class VideoView(db.Model):
    id              = Integer PK
    user_id         = FK → users
    post_id         = FK → posts
    watch_seconds   = Integer
    total_seconds   = Integer
    watch_ratio     = Float    # watch/total
    replayed        = Boolean
    created_at      = DateTime
```

---

## 5. Çok Katmanlı Algoritma — "PRISM"

Flow algoritmasına verdiğimiz ad: **PRISM** (Personalized Relevance & Interest Score Model).

### Aşama 1 — Candidate Generation (Aday Havuzu)

Tüm gönderileri değil, **işlenebilir bir havuzu** çeker.

**3 havuzdan** aday toplanır:

```
Havuz A — "Sosyal Çevre" (max 200 gönderi)
  → Takip ettiğin kişilerin son 7 günlük gönderileri
  → Takip ettiğin kişilerin beğendikleri (2. derece sinyal)

Havuz B — "Trend" (max 150 gönderi)
  → Son 48 saatte en hızlı etkileşim kazanan gönderiler
  → Kategori bazlı: onboarding'deki meslek kategorisine yakın trendler

Havuz C — "Semantik Keşif" (max 100 gönderi)
  → UserInterestProfile.topic_vector ile en yakın PostFlowScore.embedding
  → Cosine similarity ≥ 0.72 olan gönderiler (AI embedding matching)
```

Toplam aday havuzu: ~450 gönderi → Scoring'e girer.

---

### Aşama 2 — PRISM Scoring (Puanlama)

Her aday gönderi için 5 bileşenli bir skor hesaplanır:

```
PRISM_SCORE = (
    w1 × RelevanceScore     +   # İlgi uyumu
    w2 × QualityScore       +   # İçerik kalitesi
    w3 × SocialProofScore   +   # Sosyal çevreden gelen onay
    w4 × FreshnessScore     +   # Tazelik
    w5 × DiversityBonus         # Çeşitlilik bonusu
)
```

#### 5.1 RelevanceScore (w1 = 0.35)
> Kullanıcının ilgi profiline ne kadar uyuyor?

```python
# Yöntem: UserInterestProfile.topic_vector × PostFlowScore.embedding
# → cosine_similarity(user_vec, post_vec)
# Ayrıca: etiket örtüşmesi (interest_json keys ∩ semantic_tags)
relevance = cosine_sim * 0.7 + tag_overlap_ratio * 0.3
```

**AI Rolü:** Groq/LLAMA → İçerik embedding'i hesapla, semantic_tags çıkar.

#### 5.2 QualityScore (w2 = 0.25)
> İçerik nesnel olarak iyi mi?

```python
# Takipçi sayısına normalize edilmiş etkileşim oranı
followers_norm = log(1 + author.follower_count())
engagement = (likes * 1.0 + comments * 1.2 + yankas * 1.5 + saves * 2.0) / followers_norm
quality = min(1.0, engagement / QUALITY_CAP)   # QUALITY_CAP = 20
```

#### 5.3 SocialProofScore (w3 = 0.20)
> Takip ettiklerinden kaçı bu gönderiye reaksiyon verdi?

```python
# Takip edilenlerin beğeni/yanka/kaydetme sayısı
social_actions = (
    liked_by_following.count() * 2 +
    yankaed_by_following.count() * 3 +
    saved_by_following.count() * 4
)
social_proof = min(1.0, social_actions / SOCIAL_CAP)   # SOCIAL_CAP = 10
```

#### 5.4 FreshnessScore (w4 = 0.15)
> Zamansal çürüme — eski içerik daha az görünür.

```python
# Yarı ömür: video=6h, code/project=12h, text=24h, article=48h
age_hours = (now - post.created_at).total_seconds() / 3600
half_life = {'video': 6, 'code': 12, 'project': 12, 'text': 24, 'article': 48}
freshness = 0.5 ** (age_hours / half_life[post.post_type])

# Trend boost: son 2 saatte hızlı büyüyen içerik için ek puan
freshness += PostFlowScore.trend_velocity * 0.2
```

#### 5.5 DiversityBonus (w5 = 0.05)
> Kullanıcının son 10 gördüğü içerikten ne kadar farklı?

```python
# Son 10 görüntülenen gönderinin tip dağılımı
recent_types = [recent post types in session]
type_frequency = Counter(recent_types)
# En az görülen tiplere bonus
if post.post_type not in recent_types:
    bonus = 0.15
elif type_frequency[post.post_type] <= 2:
    bonus = 0.08
else:
    bonus = 0.0
```

---

### Aşama 3 — Re-ranking & Guardrails

Puanlama sonrası, son listeye girmeden **3 kural** uygulanır:

**Kural 1 — Tekrarlama Engeli**
Aynı yazardan max 2 gönderi arka arkaya gelemeez.

**Kural 2 — "Daha Az Göster" Filtresi**
`FlowSignal.signal_type = 'less_like_this'` verilen içerik tipleri/yazarlar 48 saat bastırılır.

**Kural 3 — Çeşitlilik Zorunluluğu**
Her 10 gönderiden en az 2'si farklı meslek kategorisinden olmalı.

---

### Aşama 4 — AI Katmanları

Flow'da **4 farklı AI rolü** vardır:

| Rol | Model | Tetikleyici | Çıktı |
|---|---|---|---|
| **Content Tagger** | Groq LLAMA 3.3-70b | Yeni gönderi paylaşıldığında | `semantic_tags` JSON, `embedding` vektörü |
| **Interest Updater** | Groq LLAMA 3.3-70b | Her 10 yeni sinyal biriktiğinde | `UserInterestProfile` güncelleme |
| **Trend Detector** | Kural tabanlı (SQL) + Groq | Her 2 saatte bir (cron) | `PostFlowScore.trend_velocity` |
| **Flow Explainer** | Groq LLAMA 3.1-8b (hızlı) | Kullanıcı "Neden?" tıkladığında | Tek cümle açıklama: "Python projeler paylaştığın için…" |

---

## 6. Gerçek Zamanlı Sinyal İşleme

### 6.1 Session-Based Adaptive Scoring
Kullanıcı Flow'u gezarken, her 5 etkileşimde oturum içi ağırlıklar hafifçe güncellenir:

```
Örnek: Kullanıcı 3 kod gönderisini kaydetsin
→ Bu oturumda code tipi posts için w1 (RelevanceScore) %15 artırılır
→ Oturum kapanınca bu geçici boost kalıcı UserInterestProfile'a %20 oranında işlenir
```

### 6.2 IntersectionObserver — Tarayıcı Sinyali
Her Flow kartı için JS:
```javascript
// Kart > 5 saniye viewport'ta kalırsa → view_long sinyali
// Kart < 1 saniye'de geçilirse → skip sinyali
// → POST /flow/signal endpoint'ine gönderilir (debounced, batch)
```

### 6.3 Batch Signal Processing
Sinyaller anında DB'ye yazılmaz. Her **10 saniyede bir** batch halinde:
- `FlowSignal` tablosuna yazılır
- Toplam `signal_count` güncellenir
- `signal_count % 10 == 0` olduğunda `UserInterestProfile` yeniden hesaplanır

---

## 7. Flow Sayfası — UX Mimarisi

### 7.1 Layout
```
┌──────────────────────────────────────────────────────────┐
│  NAVBAR (Feed / Flow / Keşfet / DM)                      │
├──────────┬───────────────────────────┬───────────────────┤
│ SOL PANEL│     FLOW AKIŞ             │   SAĞ PANEL       │
│          │  ┌─────────────────────┐  │                   │
│ Filtreler│  │  İçerik Kartı       │  │  Yükselen Konular │
│          │  │  (video/post/code)  │  │                   │
│ İlgi     │  └─────────────────────┘  │  Önerilen Kişiler │
│ Alanları │  ┌─────────────────────┐  │                   │
│          │  │  İçerik Kartı       │  │  Bu Hafta Viral   │
│ Kişiler  │  └─────────────────────┘  │                   │
│          │  [Infinite Scroll]         │  "Neden bu akış?" │
└──────────┴───────────────────────────┴───────────────────┘
```

### 7.2 Filtre Seçenekleri (Sol Panel)
- **Hepsi** (default)
- Video, Yazı, Kod, Proje, Makale
- **"Benim gibi profesyoneller"** — aynı kategori filtresi
- **"Yeni keşifler"** — takip etmediğin kişilerden
- **"Sosyal çevren"** — sadece takip ettiklerinden

### 7.3 "Neden Bu İçerik?" — Transparency Widget
Her kartta `…` menüsünde:
```
┌─────────────────────────────────────┐
│  Bu içerik sana neden gösteriliyor? │
│                                     │
│  🔵 Python projeler paylaştın       │
│  🔵 @enes_dev'i takip ediyorsun     │
│  🔵 Bu sabah backend yazıları izledin│
│                                     │
│  [Daha az göster] [İlgi alanı ekle] │
└─────────────────────────────────────┘
```

---

## 8. Backend Endpoint Listesi

| Method | URL | İşlev |
|---|---|---|
| GET | `/flow/` | Flow sayfası (HTML) |
| GET | `/flow/posts` | Sayfalanmış PRISM skorlu gönderi listesi (JSON) |
| POST | `/flow/signal` | Batch sinyal yazma (JSON array) |
| GET | `/flow/why/<post_id>` | AI açıklama (Groq LLAMA 3.1-8b) |
| POST | `/flow/less-like` | "Daha az göster" işaret |
| GET | `/flow/trending-topics` | Yükselen konular widget |
| POST | `/flow/tag-post/<post_id>` | İçerik tagger (admin/cron) |
| POST | `/flow/update-interest` | Interest profile yenile (cron/otomatik) |
| GET | `/flow/profile-topics/<user_id>` | Kullanıcının ilgi topic'leri |

---

## 9. Cron Job'lar

| İş | Sıklık | İşlev |
|---|---|---|
| `flow_recompute_trending` | Her 2 saatte | `PostFlowScore.trend_velocity` hesapla |
| `flow_tag_new_posts` | Her 15 dakikada | Son 15 dak'ta paylaşılan gönderileri tagger'a gönder |
| `flow_expire_scores` | Her 6 saatte | Süresi dolmuş `PostFlowScore` kayıtları sil |
| `flow_interest_decay` | Her gün gece yarısı | `UserInterestProfile` eski sinyalleri %20 azalt (forgetting curve) |

---

## 10. Geliştirme Fazları

### Faz 1 — Temel Altyapı (Önce Bu)
- `FlowSignal`, `UserInterestProfile`, `PostFlowScore`, `VideoView` modellerini yaz
- `/flow/signal` endpoint'ini yaz (batch sinyal kabul)
- `PostFlowScore` hesaplama fonksiyonu (embedding olmadan, kural tabanlı)
- Basit PRISM: sadece QualityScore + FreshnessScore + SocialProofScore
- Video desteği (upload + player)

### Faz 2 — AI Katmanı
- Groq LLAMA entegrasyonu: `content_tagger` servisi
- `UserInterestProfile` otomatik güncelleme
- Cosine similarity ile Havuz C (semantik keşif)
- "Neden?" widget — Flow Explainer

### Faz 3 — Gerçek Zamanlı
- JS IntersectionObserver sinyal sistemi
- Session-based adaptive scoring
- Cron job'lar devreye alma
- `DiversityGuard` ve guardrail'ler

### Faz 4 — UI & Polish
- Flow sayfası tam UI (Linear SaaS estetik)
- Video kartı tasarımı
- Makale tipi gönderi
- Anket (poll) tipi
- Filtre paneli + Trending Topics widget

---

## 11. Teknik Notlar & Kısıtlar

- **Embedding servisi:** Groq, embedding API sunmaz. Seçenekler:
  - OpenAI `text-embedding-3-small` (1536 dim, ücretli)
  - Cohere `embed-multilingual-v3` (1024 dim, Türkçe desteği iyi)
  - **Önerilen:** Cohere — Türkçe içerik için daha iyi, ücretsiz tier mevcut
  - Alternatif: Groq LLAMA ile pseudo-embedding (tag listesi üzerinden Jaccard similarity) — ücretsiz ama daha kaba

- **Vektör depolama:** SQLite/PostgreSQL'de JSON olarak. Kullanıcı sayısı artınca pgvector'e geçiş planla.

- **Gizlilik:** `FlowSignal` verileri 90 gün sonra otomatik silinir. `UserInterestProfile` kullanıcı hesabını silerken tamamen silinir.

- **Video hosting:** İlk aşamada kendi VPS'e upload. Ölçeklenince Cloudflare R2 + Stream'e geç.

---

## 12. Başarı Metrikleri

| Metrik | Hedef |
|---|---|
| Ortalama oturum süresi (Flow'da) | ≥ 4 dakika |
| "Daha az göster" oranı | ≤ %8 |
| Yeni takip (Flow'dan gelen) | ≥ %15 toplam takibin |
| RelevanceScore isabeti | cosine_sim ortalama ≥ 0.65 |
| Video tamamlanma oranı | ≥ %45 |
