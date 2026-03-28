# Alvera — AI Servis Dokümantasyonu

> **Dosya:** `alvera/services/ai_service.py` (891 satır)  
> **Model:** Groq API / LLAMA 3.3-70b-versatile (temel), LLAMA 3.1-8b (hızlı)

---

## Genel Yapı

```python
# Client singleton — ilk çağrıda başlatılır
_client: Groq | None = None

def get_client() -> Groq:
    # GROQ_API_KEY ortam değişkenini okur
    ...
```

**Tüm fonksiyonlar:**
- Groq API'ye `response_format={'type': 'json_object'}` ile istek gönderir
- Dönen JSON'u parse ederek Python dict döndürür
- Hata durumunda exception fırlatır (blueprint katmanında yakalanır)

---

## 1. `generate_variants(profile)` — Landing Page Varyantları

**Amaç:** Kullanıcı profili için 2 farklı landing page içerik varyantı üretir.

**Girdi:** `OnboardingData.to_dict()` çıktısı

**Çıktı:**
```json
{
  "variant_a": {
    "headline": "...",
    "tagline": "...",
    "bio": "...",
    "cta": "...",
    "skills_display": ["...", "..."]
  },
  "variant_b": { ... }
}
```

**Varyant Farkı:**
- **Variant A:** Başarı / kanıtlanmış sonuç odaklı, otorite tonu
- **Variant B:** Misyon / vizyon odaklı, daha anlatısal ve kişisel

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.82

---

## 2. `generate_content_suggestions(profile, recent_posts)` — İçerik Önerileri

**Amaç:** Kullanıcının son gönderilerini analiz ederek 3 kişiselleştirilmiş içerik fikri üretir.

**Girdi:**
- `profile` — kullanıcı profil dict'i
- `recent_posts` — son 10 gönderinin metin listesi

**Çıktı:**
```json
{
  "analysis": "Mevcut içerik akışının özeti...",
  "suggestions": [
    {
      "title": "Çekici başlık",
      "rationale": "Neden bu öneri?",
      "draft": "Hazır taslak gönderi metni..."
    }
  ]
}
```

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.78

---

## 3. `refresh_bio(profile)` — Bio Yenileme

**Amaç:** Güncellenmiş profil verilerine göre yeni headline + bio üretir.

**Çıktı:**
```json
{
  "headline": "...",
  "bio": "..."
}
```

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.80 | **Max tokens:** 400

---

## 4. `generate_brand_variants(profile)` — Marka Varyantları (Paket 2)

**Amaç:** Paket 2 kullanıcıları için marka landing page varyantları + hizmet açıklamaları üretir.

**Çıktı:**
```json
{
  "variant_a": { "headline", "tagline", "bio", "cta", "skills_display" },
  "variant_b": { ... },
  "services": [
    { "title": "...", "description": "..." }
  ]
}
```

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.80 | **Max tokens:** 1600

---

## 5. `expand_text(field, current_text, context)` — Metin Genişletici

**Amaç:** Kullanıcının kısa taslak girdisini bağlam-duyarlı zengin metne dönüştürür.

**Desteklenen alanlar:**

| `field` | Kural |
|---------|-------|
| `bio` | 2-3 cümle, birinci şahıs, 600 karakter max |
| `achievement` | Somut, etkileyici 1-2 cümle, 250 karakter max |
| `differentiator` | Akılda kalıcı tek cümle, 180 karakter max |

**Çıktı:** `{"expanded": "..."}`

**Kategori desteği:** 12 meslek kategorisi için özelleştirilmiş talimatlar (iş profesyoneli, sanatçı, sporcu, akademisyen vb.)

---

## 6. `generate_mind_map(profile, posts)` — Zihin Haritası

**Amaç:** Kullanıcının tüm platform verisini analiz ederek kişilik grafiği (MindMap) üretir.

**Girdi:**
- `profile` — profil + site + extras alanları
- `posts` — son 30 gönderinin content metinleri

**Düğüm Kategorileri:**

| Kategori | Açıklama | Adet |
|---------|----------|------|
| `identity` | Kim olduğu, ana unvanı | 2-3 |
| `expertise` | Somut beceriler, araçlar | 4-5 |
| `value` | Çalışma felsefesi, vibe | 2-3 |
| `goal` | Hedef kitle, kariyer yönü | 2-3 |
| `interest` | Gönderilerden çıkan ilgiler | 2-3 |

**Çıktı:** 12-18 düğüm + 15-25 kenar içeren JSON grafiği

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.72 | **Max tokens:** 2400

---

## 7. `generate_aura_analysis(profile_a, map_a, profile_b, map_b, common_follows)` — Aura Analizi

**Amaç:** İki kullanıcının profil ve zihin haritalarını karşılaştırarak uyum raporu üretir.

**Girdi:**
- Her iki kullanıcının profil dict'i + MindMap verisi
- `common_follows` — ortak takip edilen kullanıcılar listesi

**5 Katmanlı Çıktı:**
```json
{
  "aura_score": 87,
  "aura_label": "Derin Rezonans",
  "aura_subtitle": "...",
  "similarity_ratio": 74,
  "chemistry_tags": ["...", "..."],
  "synergies": [
    { "title": "...", "detail": "..." }
  ],
  "common_activities": [
    { "title": "...", "description": "...", "why": "...", "icon": "💡" }
  ],
  "connection_analysis": {
    "summary": "...",
    "insights": [{ "title": "...", "detail": "..." }]
  },
  "zitliklar": [
    { "title": "...", "detail": "...", "yorum": "...", "icon": "⚡" }
  ]
}
```

**Model:** `llama-3.3-70b-versatile` | **Temperature:** 0.68

---

## 8. `generate_flow_explanation(post_data, user_profile)` — Flow Açıklayıcı

**Amaç:** "Neden bu içerik?" sorusunu tek cümleyle yanıtlar.

**Örnek çıktı:** `"Python projeler paylaştığın için bu gönderi sana önerildi."`

**Model:** `llama-3.1-8b-instant` (hızlı, düşük gecikme)

---

## 9. `tag_post_content(post_content, post_type)` — İçerik Etiketleyici

**Amaç:** Yeni gönderiler için semantik etiketler + içerik özeti üretir.

**Çıktı:**
```json
{
  "semantic_tags": ["python", "backend", "open-source"],
  "summary": "..."
}
```

**Kullanım:** Flow'a yeni gönderi eklendiğinde otomatik tetiklenir

---

## Yardımcı Fonksiyonlar

### `generate_slug(full_name)`
Ad soyaddan URL dostu slug üretir.
```python
generate_slug("Ayşe Kaya")  # → "ayse-kaya"
```
Türkçe karakter çevirimi (ş→s, ğ→g, ü→u, ö→o, ı→i, ç→c) ve alfanümerik normalizasyon yapar.

---

## Vibe Tanımları

| Vibe | Açıklama |
|------|----------|
| `minimal` | Sade, beyaz ağırlıklı, az kelimeyle çok şey anlatan ton |
| `bold` | Güçlü, iddialı, cesur ifadeler, net mesajlar |
| `warm` | Sıcak, ulaşılabilir, samimi, empati taşıyan dil |

---

## Hata Yönetimi

```python
# Blueprint katmanında yakalanır — örnek pattern:
try:
    result = generate_variants(profile.to_dict())
except RuntimeError as e:
    # GROQ_API_KEY eksik
    return jsonify({'ok': False, 'error': str(e)}), 500
except Exception as e:
    # API veya JSON parse hatası
    return jsonify({'ok': False, 'error': 'AI servisi geçici olarak kullanılamıyor.'}), 503
```
