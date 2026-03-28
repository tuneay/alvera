# 💎 Alvera | Proje Anayasası & Geliştirme Rehberi

## 🎯 Vizyon ve Öz
Alvera, kişiye özel ve yapay zeka destekli prestijli landing page'ler sunan bir dijital atölyedir. Alvera bir "site kurucu" değil, profesyoneller için bir "Dijital Kimlik" küratörüdür. 

## 🎨 Görsel Kimlik & Estetik (Linear SaaS)
* **Tema:** Tamamen "Light Mode", beyaz ağırlıklı, ferah ve modern bir "Linear SaaS" estetiği.
* **Tasarım Prensipleri:** Yüksek kaliteli tipografi, ince çizgiler (borders), geniş boşluklar (whitespace).
* **Kısıtlamalar:** Kullanıcı fontları değiştiremez. Tasarımın bozulmaması için inputlarda katı karakter limitleri uygulanır.
* **Hissiyat:** Apple standartlarında akışkanlık, her geçişte 0.5s "ease-in-out" animasyonlar.

## 🛠 Teknik Yığın (Tech Stack)
* **Backend:** Python & Flask.
* **AI:** Groq API üzerinden LLAMA modelleri.
* **Veri:** Kullanıcı girdileri ve site yapıları için JSON tabanlı mimari.
* **Ödeme:** Türkiye odaklı Iyzico entegrasyonu (Subscription modeli).
* **Hosting:** VPS (Ubuntu/Nginx).

## 🔄 Kullanıcı Yolculuğu (User Flow)
1.  **Giriş:** Estetik ve ikna edici ana landing page.
2.  **Kayıt & Ödeme:** Kullanıcı deneyime başlamadan önce Iyzico üzerinden ödeme yapar (Exclusivity).
3.  **Onboarding (Concierge):** Ödeme sonrası, pürüzsüz kayan panellerle dinamik soru-cevap süreci.
4.  **Üretim:** AI, kullanıcının ruhuna ve işine uygun 2 farklı tasarım opsiyonu sunar.
5.  **Yönetim:** Seçilen site `alvera.me/slug` üzerinden yayına alınır; kısıtlı ama özgür bir admin paneli sunulur.

## ✦ Aura Sistemi
İki kullanıcının zihin haritası ve profil verilerini karşılaştıran, AI destekli sosyal analiz özelliği.

**Kullanıcı akışı:** Başka bir kullanıcının profil sayfasında (mindmap widget'ı veya sosyal profil) "Aura" butonuna basılır → 6 fazlı modal overlay açılır.

**6 Faz:**
1. Aura Skoru (ring animasyonu + sayaç)
2. Benzerlik oranı, kimya etiketleri, sinerji noktaları
3. AI'nın önerdiği ortak faaliyetler
4. Ortak takip analizinden Bağlantı İçgörüleri
5. Zıtlıklar — farklılıklar üzerine AI yorumu + Paylaş kartı
6. Aura sonucunu karşı tarafa DM olarak gönder

**Teknik notlar:**
- Analiz `AuraResult` modeline cache'lenir (canonical pair: `min(a,b), max(a,b)`). Aynı ikili için AI bir daha çalışmaz.
- Overlay açılışında önce `GET /mindmap/aura/cached/<id>` kontrol edilir, cache yoksa `POST /mindmap/aura` ile AI çağrısı yapılır.
- DM mesajı `msg_type='aura'` + `meta_json` (skor, label, url) ile ayrı bir kart olarak görünür.
- Alıcı "Raporu İncele" butonuna basınca `/mindmap/<id>?aura=1` adresine yönlenir; sayfa otomatik overlay'i açar ve cache'den yükler.
- Overlay tek bir `_aura_overlay.html` include dosyasında; hem `mindmap.html` hem `feed_profile.html` bu dosyayı kullanır.
- AI servisi: `generate_aura_analysis()` → Groq/LLAMA 3.3-70b, `max_tokens=3600`.

## 🗂 Sosyal Akış (Feed) Sistemi — Teknik Notlar

### Post Kartı (`_feed_post.html` + `feed.html`)
- **4 tip:** `text`, `project`, `image`, `code`
- Kod gönderilerinde `mention-body` paragrafı render edilmez; içerik yalnızca `post-code-block` içinde gösterilir (`post_type != 'code'` koşulu).
- `post-code-pre`: `max-height: 320px`, `overflow-y: auto`, ince webkit scrollbar. Kart sonsuz büyümez.
- `post-code-card`: Kod bloğu kartın alt kenarına tam oturur (`border-radius: 0 0 15px 15px`).

### Kod Gönderisi — Caption Desteği
- Kullanıcı kod yazarken üstteki `composeCodeCaption` textarea'sına açıklama ekleyebilir (maks. 300 karakter, opsiyonel).
- Caption `link_title` kolonuna kaydedilir (kod gönderilerinde `link_url`/`link_title` kullanılmadığı için migration gerektirmez).
- Kart üzerinde caption varsa `post.link_title` → `mention-body` paragrafı olarak kod bloğunun üstünde gösterilir.
- `submitPost()` JS'de `caption` alanı `POST /feed/post` JSON body'e eklenir ve form temizlenirken sıfırlanır.

### Sağ Panel — "Bu Hafta Öne Çıkanlar"
- Eski statik Kategoriler listesi kaldırıldı.
- `_get_trending_posts(limit=3)` fonksiyonu: son 7 günde `PostLike + PostYanka` subquery join ile en yüksek toplam etkileşimli 3 gönderiyi döndürür.
- `index()` route'una `trending_posts` değişkeni olarak geçilir.
- Widget tasarımı: sıralama numarası (muted), 26px avatar, yazar adı + tip renk noktası (5px daire) + snippet, hover chevron `›`. Skor pill yok.
- `scrollToPost(id)` — tıklanınca smooth scroll + 1.4s border highlight animasyonu.
- Renk noktaları: kod → `#6EE7B7`, proje → `#93C5FD`, fotoğraf → `#C4B5FD`, metin → `#D1D5DB`.

### Önemli Kolonlar (`posts` tablosu)
| Kolon | Kullanım |
|---|---|
| `content` | Metin / Proje metni / Ham kod |
| `code_language` | Kod tipi için dil (python, js…) |
| `link_title` | Kod gönderisi caption'ı (diğer tiplerde null) |
| `link_url` | Eski link gönderileri için (aktif değil) |
| `media_files` | Resim gönderileri için JSON array |

### Bookmark (Kaydedilenler)
- `SavedPost` modeli: `saved_posts` tablosu, `post_id + user_id` unique constraint.
- `Post` modeli: `saves` relationship, `is_saved_by(user)` metodu, `views` relationship, `view_count` property eklendi.
- Route: `POST /feed/post/<id>/save` → toggle. `GET /feed/saved` → kaydedilen gönderiler feed'i.
- Sol panelde "Kaydedilenler" linki (`pp-saved-link`), aktifken mavi. Kart üzerinde `save-btn` (bookmark SVG, dolu/boş toggle).

### Yankı Animasyonu
- `yankaBurst`: rotasyon kaldırıldı. Yeni: `scale(1 → 1.18 → 0.94 → 1)`, `0.38s`, `cubic-bezier(0.22,1,0.36,1)`.

### Görüntülenme Sayacı
- Post kartı aksiyon satırında sağda göz ikonu + sayı (`post-view-count`). 0 ise görünmez, 1000+ ise `1K` formatı.
- `PostView` modeli zaten mevcut; `view_count` property ve UI eklendi.

### Diğer Düzeltmeler
- Akış navbarı profil avatarı artık `/feed/u/<id>` adresine yönlendiriyor (eskiden `site.dashboard`'a gidiyordu).
- Kod kartları artık feed genişliğini patlatmıyor: `.feed-center`, `#feedList`, `.post-card`, `.post-code-block`, `.post-code-pre` üzerine `min-width:0; max-width:100%` eklendi.

## 📜 Geliştirici Kuralları (Claude İçin)
* **Mimar Önceliklidir:** Kod yazmadan önce her zaman yapıyı ve UX detaylarını tartış.
* **Modüler Yapı:** Tüm bileşenleri (Payment, AI, Frontend, Auth) modüler ve temiz kod prensipleriyle yaz.
* **Estetik Bekçiliği:** Eğer bir özellik "Linear" estetiğini bozacaksa, daha minimalist bir alternatif öner.
* **Hata Yönetimi:** Özellikle API çağrılarında ve ödeme süreçlerinde kusursuz hata yönetimi kurgula.