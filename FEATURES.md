# Alvera — Özellik Haritası

> Platform özelliklerinin modül bazlı özeti.

---

## 🔐 Kimlik & Güvenlik

| Özellik | Detay |
|---------|-------|
| E-posta + şifre kaydı | Minimum 8 karakter, doğrulama |
| Parola hash'leme | `werkzeug.security` (bcrypt tabanlı) |
| Oturaum yönetimi | Flask-Login, `remember=True` desteği |
| Onboarding kapısı | Profil kurulmadan uygulama açılmaz |
| Post URL gizleme | Sıralı ID yerine rastgele 10 karakterlik slug |

---

## 👤 Profil Sistemi

| Özellik | Detay |
|---------|-------|
| Akıllı onboarding | 7 adım, her kişi tipi için özelleştirilmiş (iş, sanat, spor, akademi...) |
| Vibe seçimi | 3 ton: minimal, bold, warm |
| Kimlik sinyalleri | Hedef kitle, en büyük başarı, rakipten fark |
| Müsaitlik rozeti | "Şu an işbirliği açığım" toggle |
| Profil extras | Durum mesajı + emoji, CTA butonu, çalışma tercihi |
| Kariyer zaman çizelgesi | Şirket, rol, tarih aralığı |
| Link Merkezi | Özel linkler (tıklanma sayısı tracking) |
| Sosyal linkler | LinkedIn, GitHub, Twitter, Website |

---

## 🤖 Yapay Zeka Özellikleri

| Özellik | Model | Açıklama |
|---------|-------|----------|
| Landing page varyantları | LLAMA 3.3-70b | 2 farklı kimlik anlatısı, JSON çıktı |
| İçerik önerileri | LLAMA 3.3-70b | Gönderi analizi + 3 hazır taslak |
| Bio yenileme | LLAMA 3.3-70b | Profilden güncel headline + bio |
| Metin genişletici | LLAMA 3.3-70b | Kısa taslağı özgün metne dönüştür |
| Marka varyantları (P2) | LLAMA 3.3-70b | + hizmet açıklamaları |
| Zihin haritası | LLAMA 3.3-70b | 12-18 düğüm, 5 kategori, ağırlıklı graf |
| Aura analizi | LLAMA 3.3-70b | 5 katmanlı uyum raporu, 0-100 skor |
| Flow açıklayıcı | LLAMA 3.1-8b | "Neden bu içerik?" — tek cümle |
| İçerik etiketleyici | LLAMA 3.3-70b | Semantic tags + özet |

---

## 📱 Sosyal Özellikler

| Özellik | Detay |
|---------|-------|
| Gönderi tipleri | Text, project, image (çoklu), code (sözdizimi renklendirmeli), video |
| Beğeni | Toggle, anlık güncelleme |
| Yorum | Sıralı, anlık |
| Yankı (Yanka) | Geri alınamaz, günde max 5, feed'de öncelikli |
| Kaydet | Bookmark, ayrı "Kaydedilenler" sayfası |
| Takip | Çift yönlü sosyal graf |
| Pin | Gönderileri profile sabitleme |

---

## 🔍 Flow / Keşif (PRISM Algoritması)

| Özellik | Detay |
|---------|-------|
| 3 Aday havuzu | Sosyal çevre (200) + Trend (150) + Semantik keşif (100) |
| 5 Skor bileşeni | Relevance + Quality + Social Proof + Freshness + Diversity |
| Davranış sinyalleri | Görüntüleme süresi, skip, expand, kaydet, "daha az göster" |
| Batch sinyal işleme | 10 saniyede bir toplu yazma |
| Session adaptasyonu | Her 5 etkileşimde oturum içi ağırlık güncelleme |
| Sheffali filtreler | Hepsi / Video / Yazı / Kod / Proje / Makale / ... |
| "Neden?" widget | Her içeriğin önerilme sebebi (AI açıklama) |
| Re-ranking / Guardrails | Tekrarlama engeli, "daha az göster" filtresi, çeşitlilik zorunluluğu |
| Trend dedektörü | Son 2 saatte hızlı büyüyen içerik tespiti |
| Video izleme sinyali | watch_ratio > %50 ve %80 için ayrı sinyal güçleri |

---

## 💬 Direkt Mesajlaşma (Alvera Direct)

| Özellik | Detay |
|---------|-------|
| Bire-bir konuşmalar | UniqueConstraint ile yinelenme engeli |
| Mesaj tipleri | text, aura (analiz paylaşımı), code (sözdizimi renkli) |
| Emoji tepkiler | Kişi başı emoji kısıtlı (UniqueConstraint) |
| Okunмamış sayacı | Konuşma başlığında badge |
| Mesaj silme | Soft delete (`is_deleted`) |
| Mesaj düzenleme | `edited_at` timestamp |
| Kod paylaşımı | Dil seçimli kod bloğu mesajları |

---

## 🧠 Aura & Zihin Haritası

| Özellik | Detay |
|---------|-------|
| Zihin haritası | Hesaplama: son 50 gönderi + tüm profil verisi |
| MindMap cache | Tek kayıt (user başına), versiyonlu |
| Aura skoru | 0-100 arası uyum puanı |
| Aura cache | Bir çift için tek kayıt (user_a_id < user_b_id) |
| DM Aura | Konuşma içinde Aura analizi başlatma + paylaşma |
| Ortak takip | Aura analizinde socyal overlap hesabı |

---

## 🏗️ Kişisel Site (Paket 2)

| Özellik | Detay |
|---------|-------|
| AI varyant seçimi | A/B iki farklı kimlik anlatısı |
| Slug | `ad-soyad` formatında URL |
| Profil fotoğrafı | Upload + crop desteği |
| Kapak görseli | Geniş banner alanı |
| Yayın kontrolü | `is_published` toggle |
| Portföy | Problem/Çözüm/Sonuç formatı, etiket, URL, kapak |
| Hizmetler | Başlık, açıklama, fiyat aralığı, CTA |
| Referanslar | Müşteri adı, rol, yorum, yıldız puanı |
| İletişim | Mini-CRM: gelen mesajlar, okundu işareti |
| Sayfa görüntüleme | Analytics teaser (PageView kayıtları) |

---

## 🔔 Bildirimler

| Tür | Tetikleyici |
|-----|-------------|
| `like` | Gönderiniz beğenildi |
| `comment` | Gönderinize yorum yapıldı |
| `follow` | Biri sizi takip etti |
| `mention` | @mention yapıldı |
| `yanka` | Gönderinize Yankı verildi |

Tüm bildirimler in-app, gerçek zamanlı dropdown ile gösterilir.

---

## ⚙️ Admin Paneli

- Kullanıcı listesi ve yönetimi
- Paket düzenleme
- Genel istatistikler

---

## 🚧 Geliştirme Yol Haritası (PRISM)

| Faz | İçerik | Durum |
|-----|--------|-------|
| Faz 1 | Temel altyapı: FlowSignal, UserInterestProfile, PostFlowScore, VideoView modelleri; kural tabanlı PRISM | ✅ Modeller hazır |
| Faz 2 | Groq LLAMA ile içerik tagger + UserInterestProfile otomatik güncelleme + Cosine similarity | 🔧 Planlandı |
| Faz 3 | JS IntersectionObserver sinyal sistemi + Session adaptive scoring + Cron job'lar | 🔧 Planlandı |
| Faz 4 | Flow UI polishing: video kartı, makale tipi, anket, filtre paneli | 🔧 Planlandı |

Ayrıntılar için: [FLOW_ALGORITHM_PLAN.md](./FLOW_ALGORITHM_PLAN.md)
