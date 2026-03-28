"""
Alvera AI Servisi
─────────────────
Groq / LLAMA üzerinden:
  1. Kullanıcı profiline göre 2 landing page varyantı üretir.
  2. Mevcut gönderileri analiz ederek 3 kişiselleştirilmiş içerik önerisi üretir.
  3. Güncellenmiş profile göre bio yeniler.
"""

import os
import json
import re

from groq import Groq

# ─── Client ──────────────────────────────────────────────────────────────────
_client: Groq | None = None

def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get('GROQ_API_KEY')
        if not api_key:
            raise RuntimeError('GROQ_API_KEY ortam değişkeni tanımlı değil.')
        _client = Groq(api_key=api_key)
    return _client


# ─── Vibe tanımları ───────────────────────────────────────────────────────────
VIBE_DESCRIPTIONS = {
    'minimal': (
        'sade, beyaz ağırlıklı ve zamansız bir estetik. '
        'Az kelimeyle çok şey anlatma. Sakin ve rafine bir ses tonu.'
    ),
    'bold': (
        'güçlü, iddialı ve kendinden emin bir ses. '
        'Cesur ifadeler, net mesajlar. Okuyucuyu etkileyen, akılda kalan başlıklar.'
    ),
    'warm': (
        'sıcak, ulaşılabilir ve insani bir ton. '
        'Samimi ifadeler, dostane bir ses. Okuyucuyla bağ kuran, empati taşıyan dil.'
    ),
}


# ─── Slug üretimi ─────────────────────────────────────────────────────────────
def generate_slug(full_name: str) -> str:
    """Ad soyaddan URL slug üretir. Örn: "Ayşe Kaya" → "ayse-kaya" """
    replacements = {
        'ş': 's', 'ğ': 'g', 'ü': 'u', 'ö': 'o', 'ı': 'i', 'ç': 'c',
        'Ş': 's', 'Ğ': 'g', 'Ü': 'u', 'Ö': 'o', 'İ': 'i', 'Ç': 'c',
    }
    slug = full_name.lower().strip()
    for char, replacement in replacements.items():
        slug = slug.replace(char, replacement)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


# ─── 1. Ana üretim fonksiyonu — Landing page varyantları ─────────────────────
def generate_variants(profile: dict) -> dict:
    """
    Kullanıcı profilini alır, Groq'a gönderir ve 2 varyant döner.

    Dönen yapı:
    {
        "variant_a": { headline, tagline, bio, cta, skills_display },
        "variant_b": { headline, tagline, bio, cta, skills_display }
    }
    """
    vibe       = profile.get('vibe', 'minimal')
    vibe_desc  = VIBE_DESCRIPTIONS.get(vibe, VIBE_DESCRIPTIONS['minimal'])
    skills_str = profile.get('skills', '')
    company    = profile.get('company', '')
    company_line   = f"Çalıştığı yer / Kurum: {company}" if company else ""
    category       = profile.get('profession_category', '')
    category_line  = f"Alan / Kategori: {category}" if category else ""

    # Özgün Kimlik Sinyalleri
    target_audience = profile.get('target_audience', '')
    achievement     = profile.get('achievement', '')
    differentiator  = profile.get('differentiator', '')
    ta_line   = f"Hedef kitle: {target_audience}"   if target_audience else ""
    ach_line  = f"En büyük başarısı / gurur anı: {achievement}" if achievement else ""
    diff_line = f"Onu rakiplerinden ayıran şey: {differentiator}" if differentiator else ""

    prompt = f"""Sen dünyaca ünlü bir dijital kimlik danışmanı ve yaratıcı metin yazarısın.
Aşağıdaki profile dayanarak TÜRKÇE olarak iki farklı landing page varyantı yaz.
Kişi bir iş profesyoneli olabileceği gibi sanatçı, sporcu, içerik üretici, akademisyen veya başka bir alanda da olabilir — metni buna göre uyarla.
Her varyant aynı kişiyi farklı bir açıdan yansıtmalı — çıktılar birbirinden belirgin biçimde ayrışmalı.

─── PROFİL ───
İsim: {profile.get('full_name', '')}
{category_line}
Unvan / Tanım: {profile.get('job_title', '')}
{company_line}
Kendi anlatımı: {profile.get('bio', '')}
Uzmanlık / Odak alanları: {skills_str}
İstenen his / ton: {vibe} — {vibe_desc}

─── ÖZGÜN KİMLİK SİNYALLERİ ───
{ta_line}
{ach_line}
{diff_line}

─── KURALLAR ───
- Bu kişiye has sinyalleri (başarı, fark, hedef kitle) kesinlikle metne yansıt — jenerik klişelerden kaç.
- headline: 4-7 kelime, akılda kalıcı ve sadece bu kişiye ait. Genel başlıklar yasak.
- tagline: 8-14 kelime; hedef kitleye ne sunduğunu ya da ne fark yarattığını anlatsın.
- bio: 2-3 cümle, birinci şahıs. Başarı sinyalini veya farklaştırıcıyı doğal biçimde içersin.
- cta: 3-5 kelime (Örn: "Birlikte çalışalım", "İletişime geçin", "Hikayemi keşfedin")
- skills_display: uzmanlık listesinden en fazla 5 tanesini seç, JSON array olarak.
- Variant A: başarı / kanıtlanmış sonuç odaklı, otorite tonu.
- Variant B: misyon / vizyon odaklı, daha anlatısal ve kişisel.
- Tüm metin Türkçe olmalı.

─── ÇIKTI FORMATI ───
Sadece aşağıdaki JSON yapısını döndür, başka hiçbir şey yazma:

{{
  "variant_a": {{
    "headline": "...",
    "tagline": "...",
    "bio": "...",
    "cta": "...",
    "skills_display": ["...", "..."]
  }},
  "variant_b": {{
    "headline": "...",
    "tagline": "...",
    "bio": "...",
    "cta": "...",
    "skills_display": ["...", "..."]
  }}
}}"""

    client = get_client()

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen bir dijital kimlik danışmanısın. '
                    'Her zaman sadece geçerli JSON döndürürsün, başka hiçbir şey yazmazsın.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.82,
        max_tokens=1200,
        response_format={'type': 'json_object'},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


# ─── 2. İçerik önerisi — Post analizi + 3 kişiselleştirilmiş fikir ───────────
def generate_content_suggestions(profile: dict, recent_posts: list[str]) -> dict:
    """
    Kullanıcının profilini ve son gönderilerini analiz ederek
    3 kişiselleştirilmiş içerik fikri döner.

    Parametreler:
        profile      — to_dict() çıktısı (job_title, skills, vibe, vb.)
        recent_posts — son 10 gönderinin metin listesi (boş olabilir)

    Dönen yapı:
    {
        "analysis": "...",   // kullanıcıya gösterilen kısa analiz
        "suggestions": [
            {
                "title": "...",
                "rationale": "...",   // neden önerildiği (1 cümle)
                "draft": "..."        // hazır taslak metin (compose'a aktarılır)
            },
            ...  // 3 öneri
        ]
    }
    """
    vibe      = profile.get('vibe', 'minimal')
    vibe_desc = VIBE_DESCRIPTIONS.get(vibe, VIBE_DESCRIPTIONS['minimal'])

    # Gönderi özetini oluştur
    if recent_posts:
        posts_section = "─── SON GÖNDERİLER ───\n"
        for i, p in enumerate(recent_posts[:10], 1):
            snippet = p[:200].replace('\n', ' ')
            posts_section += f"{i}. {snippet}\n"
    else:
        posts_section = "─── SON GÖNDERİLER ───\nKullanıcı henüz hiç gönderi paylaşmamış.\n"

    prompt = f"""Sen bir profesyonel içerik stratejistisin. Aşağıdaki kişinin dijital profilini ve son paylaşımlarını analiz et.

─── PROFİL ───
İsim: {profile.get('full_name', '')}
Unvan: {profile.get('job_title', '')}
Şirket: {profile.get('company', '') or 'Belirtilmemiş'}
Uzmanlık: {profile.get('skills', '')}
Kişisel Anlatı: {profile.get('bio', '')}
Ton Tercihi: {vibe} — {vibe_desc}

{posts_section}

─── GÖREVİN ───
1. Mevcut gönderileri kısaca analiz et: hangi konular ele alınmış, hangi boşluklar var, içerik tutarlılığı nasıl.
2. Bu kişi için dijital iz bırakma ve SEO açısından değerli 3 özgün içerik fikri öner.

─── İÇERİK FİKİRLERİ İÇİN KURALLAR ───
- Her öneri bu kişinin mesleğine ve uzmanlığına %100 özgü olmalı, jenerik olmamalı.
- draft metin direkt paylaşılabilir olmalı: 2-4 cümle, samimi, birinci şahıs, profesyonel.
- Ton tercihi olan "{vibe}" stiline uygun olmalı.
- Kişinin henüz değinmediği konulara öncelik ver.
- Türkçe yaz.

─── ÇIKTI FORMATI ───
Sadece JSON döndür:

{{
  "analysis": "Mevcut içerik akışının 1-2 cümlelik özeti ve eksiklikleri.",
  "suggestions": [
    {{
      "title": "Kısa ve çekici başlık (5-8 kelime)",
      "rationale": "Bu fikrin neden değerli olduğu — 1 cümle.",
      "draft": "Hazır taslak gönderi metni. Kullanıcı küçük düzenlemelerle paylaşabilmeli."
    }},
    {{
      "title": "...",
      "rationale": "...",
      "draft": "..."
    }},
    {{
      "title": "...",
      "rationale": "...",
      "draft": "..."
    }}
  ]
}}"""

    client = get_client()

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen bir içerik stratejisti ve dijital kimlik danışmanısın. '
                    'Yalnızca geçerli JSON döndürürsün.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.78,
        max_tokens=900,
        response_format={'type': 'json_object'},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


# ─── 3. Bio yenileme — Güncel profil + vibe'a göre yeni anlatı ───────────────
def refresh_bio(profile: dict) -> dict:
    """
    Güncellenmiş profil verilerine göre yeni bir bio + headline üretir.

    Dönen yapı:
    {
        "headline": "...",
        "bio": "..."
    }
    """
    vibe      = profile.get('vibe', 'minimal')
    vibe_desc = VIBE_DESCRIPTIONS.get(vibe, VIBE_DESCRIPTIONS['minimal'])

    prompt = f"""Aşağıdaki profesyonel profil için yeni, güncel bir dijital kimlik anlatısı yaz.

─── GÜNCEL PROFİL ───
İsim: {profile.get('full_name', '')}
Unvan: {profile.get('job_title', '')}
Şirket: {profile.get('company', '') or 'Belirtilmemiş'}
Uzmanlık: {profile.get('skills', '')}
Kişisel not: {profile.get('bio', '')}
Ton: {vibe} — {vibe_desc}

─── KURALLAR ───
- headline: 4-7 kelime, özgün, klişesiz.
- bio: 2-3 cümle, birinci şahıs, güncel profili yansıtmalı. Enerjik ve özgün.
- Türkçe.

Sadece JSON döndür:
{{
  "headline": "...",
  "bio": "..."
}}"""

    client = get_client()

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': 'Sen bir yaratıcı metin yazarısın. Yalnızca geçerli JSON döndürürsün.',
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.80,
        max_tokens=400,
        response_format={'type': 'json_object'},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


# ─── 4. Paket 3 — Marka varyantları + hizmet açıklamaları ────────────────────
def generate_brand_variants(profile: dict) -> dict:
    """
    Paket 3 kullanıcısı için:
      - 2 farklı marka anlatısı varyantı (headline, tagline, bio, cta, skills_display)
      - services_raw listesindeki her hizmet için kısa profesyonel açıklama

    Dönen yapı:
    {
        "variant_a": { "headline", "tagline", "bio", "cta", "skills_display" },
        "variant_b": { "headline", "tagline", "bio", "cta", "skills_display" },
        "services":  [ { "title": "...", "description": "..." }, ... ]
    }
    """
    vibe          = profile.get('vibe', 'minimal')
    vibe_desc     = VIBE_DESCRIPTIONS.get(vibe, VIBE_DESCRIPTIONS['minimal'])
    brand_name    = profile.get('brand_name', '')
    brand_type    = profile.get('brand_type', 'diger')
    brand_tagline = profile.get('brand_tagline', '')
    services_raw  = profile.get('services_raw', '')
    skills_str    = profile.get('skills', '')
    company       = profile.get('company', '')

    # Özgün Kimlik Sinyalleri (P3 için de kullan)
    target_audience = profile.get('target_audience', '')
    achievement     = profile.get('achievement', '')
    differentiator  = profile.get('differentiator', '')
    ta_line   = f"Hedef müşteri / kitle: {target_audience}"   if target_audience else ""
    ach_line  = f"Markanın öne çıkan başarısı / kanıtı: {achievement}" if achievement else ""
    diff_line = f"Rakiplerden farkı: {differentiator}" if differentiator else ""

    services_list = [s.strip() for s in services_raw.split(',') if s.strip()]
    services_json = json.dumps(services_list, ensure_ascii=False)

    brand_type_labels = {
        'freelancer': 'Freelancer / Bağımsız Profesyonel',
        'ajans':      'Ajans',
        'danışman':   'Danışman / Consultant',
        'startup':    'Startup / Girişim',
        'diger':      'Diğer',
    }
    brand_type_label = brand_type_labels.get(brand_type, brand_type)
    tagline_line     = f"Marka sloganı: {brand_tagline}" if brand_tagline else ''
    company_line     = f"Şirket / Kurum: {company}" if company else ''

    prompt = f"""Sen dünyaca tanınan bir marka danışmanı ve yaratıcı metin yazarısın.
Aşağıdaki marka profiline göre TÜRKÇE iki farklı landing page varyantı ve hizmet açıklamaları yaz.
Her varyant belirgin biçimde farklı bir marka sesi ve pozisyonlama açısı taşımalı.

─── MARKA PROFİLİ ───
Marka Adı: {brand_name}
İş Türü: {brand_type_label}
{tagline_line}
Kurucu: {profile.get('full_name', '')}
Unvan: {profile.get('job_title', '')}
{company_line}
Uzmanlık Alanları: {skills_str}
Kişisel Anlatı: {profile.get('bio', '')}
Ton Tercihi: {vibe} — {vibe_desc}
Sunulan Hizmetler: {services_raw}

─── ÖZGÜN MARKA SİNYALLERİ ───
{ta_line}
{ach_line}
{diff_line}

─── VARYANT KURALLARI ───
- headline: 4-7 kelime, marka odaklı, akılda kalıcı.
- tagline: 8-15 kelime, markanın değer önerisini anlatan bir cümle.
- bio: 2-3 cümle, üçüncü şahıs ya da "biz" perspektifinden markanın anlatısı.
- cta: 3-5 kelime (Örn: "Projenizi Başlatalım", "Teklif Alın", "Keşfet")
- skills_display: uzmanlık alanlarından en fazla 5 tanesini seç, JSON array.
- Variant A kurumsal ve güven odaklı, B daha yaratıcı ve iddialı olsun.

─── HİZMET AÇIKLAMALARI ───
Şu hizmetler için kısa, profesyonel açıklamalar yaz:
{services_json}

Her hizmet için:
- description: 1-2 cümle, net ve değer odaklı, potansiyel müşteriye hitap eden.

─── ÇIKTI FORMATI ───
Sadece JSON döndür, başka hiçbir şey yazma:

{{
  "variant_a": {{
    "headline": "...",
    "tagline": "...",
    "bio": "...",
    "cta": "...",
    "skills_display": ["..."]
  }},
  "variant_b": {{
    "headline": "...",
    "tagline": "...",
    "bio": "...",
    "cta": "...",
    "skills_display": ["..."]
  }},
  "services": [
    {{"title": "...", "description": "..."}},
    ...
  ]
}}"""

    client   = get_client()
    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen bir marka danışmanı ve yaratıcı metin yazarısın. '
                    'Her zaman sadece geçerli JSON döndürürsün, başka hiçbir şey yazmazsın.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.80,
        max_tokens=1600,
        response_format={'type': 'json_object'},
    )

    return json.loads(response.choices[0].message.content)


# ─── 5. Metin Genişletici — Kullanıcının kısa girdisini zenginleştirir ───────
# Alan kategorisi ve bağlam bilgisine göre iş profesyonelinden sanatçıya,
# sporcudan akademisyene kadar herkese özgü bir dil üretir.

FIELD_INSTRUCTIONS = {
    'bio': (
        'Kullanıcının yazdığı kısa bio taslağını alıp doğal, birinci şahıs, '
        '2-3 cümlelik zengin bir anlatıya dönüştür. '
        'Özgeçmiş gibi değil; bir insanın kendi sesini duyurduğu sıcak ve güçlü bir metin olsun. '
        'Kişinin alanına (sanat, spor, iş, akademi vb.) uygun bir ton kullan. '
        'Orijinal fikri koru ama daha canlı ve özgün hale getir. '
        'Karakter limiti: 600.'
    ),
    'achievement': (
        'Kullanıcının bahsettiği başarıyı veya gurur anını alıp somut, etkileyici 1-2 cümleye dönüştür. '
        'Sayı, proje adı veya ölçülebilir etki varsa mutlaka koru. '
        'Yoksa genel bir ifade yerine özel detay ekle. '
        'Karakter limiti: 250.'
    ),
    'differentiator': (
        'Kullanıcının rakiplerinden farkını anlatan kısa notu alıp keskin, akılda kalıcı tek bir cümleye dönüştür. '
        'Bu onların benzersiz değer önerisi — jenerik olmayacak, sadece bu kişiye ait olacak. '
        'Karakter limiti: 180.'
    ),
}

# Kategori başlıkları (prompt için okunabilir)
CATEGORY_LABELS = {
    'is-profesyoneli':    'İş / Kurumsal Profesyonel',
    'sanatci-tasarimci':  'Sanatçı & Tasarımcı',
    'muzisyen':           'Müzisyen & Performans Sanatçısı',
    'fotograf-video':     'Fotoğrafçı & Video İçerik',
    'sporcu-koc':         'Sporcu & Fitness Koçu',
    'akademisyen':        'Akademisyen & Araştırmacı',
    'icerik-uretici':     'İçerik Üretici & Influencer',
    'sef-gurme':          'Şef & Gurme',
    'muhendis-mimar':     'Mühendis & Mimar',
    'saglik-wellness':    'Sağlık & Wellness Uzmanı',
    'girisimci':          'Girişimci & Startup Kurucusu',
    'yazar-icerik':       'Yazar & İçerik Stratejisti',
}


def expand_text(field: str, current_text: str, context: dict) -> dict:
    """
    Kullanıcının kısa metin girdisini alır, bağlam bilgisiyle zenginleştirir.

    Parametreler:
        field        — 'bio' | 'achievement' | 'differentiator'
        current_text — Kullanıcının yazdığı ham metin
        context      — {'job_title': ..., 'profession_category': ...,
                         'full_name': ..., 'vibe': ...}

    Döner:
        {'expanded': '...'}
    """
    instructions = FIELD_INSTRUCTIONS.get(field, FIELD_INSTRUCTIONS['bio'])

    job_title = context.get('job_title', '')
    category  = context.get('profession_category', '')
    full_name = context.get('full_name', '')
    vibe      = context.get('vibe', 'minimal')
    vibe_desc = VIBE_DESCRIPTIONS.get(vibe, VIBE_DESCRIPTIONS['minimal'])

    cat_label = CATEGORY_LABELS.get(category, category) if category else ''
    cat_line  = f"Alan / Kategori: {cat_label}" if cat_label else ''
    job_line  = f"Unvan / Tanım: {job_title}" if job_title else ''
    name_line = f"Kişi: {full_name}" if full_name else ''

    prompt = f"""Sen Türkçe metin yazan, kısa girdileri sıcak ve etkileyici anlatılara dönüştüren bir metin danışmanısın.

─── BAĞLAM ───
{name_line}
{cat_line}
{job_line}
Ton tercihi: {vibe} — {vibe_desc}

─── KULLANICININ YAZDIĞI (ham, kısa) ───
{current_text}

─── GÖREV ───
{instructions}

─── KURALLAR ───
- Türkçe yaz.
- Orijinal anlam ve kişisel sesi koru, sadece zenginleştir.
- Çok uzun, klişe veya kurumsal bir dil kullanma.
- Sadece JSON döndür.

{{
  "expanded": "..."
}}"""

    client = get_client()
    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen bir Türkçe metin danışmanısın. '
                    'Her zaman sadece geçerli JSON döndürürsün.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.78,
        max_tokens=500,
        response_format={'type': 'json_object'},
    )
    return json.loads(response.choices[0].message.content)


# ─── 6. Zihin Haritası üretimi ────────────────────────────────────────────────
def generate_mind_map(profile: dict, posts: list[str]) -> dict:
    """
    Kullanıcının tüm platform verisini analiz ederek bir Zihin Haritası üretir.

    Parametreler:
        profile : OnboardingData.to_dict() + sites + extras alanları
        posts   : Son 50 gönderinin content metinleri listesi

    Dönen yapı:
    {
        "nodes": [
            {
                "id":          "n1",
                "label":       "Ürün Tasarımcısı",
                "category":    "identity",
                "weight":      10,
                "description": "Kısa açıklama"
            }, ...
        ],
        "edges": [
            {
                "source":   "n1",
                "target":   "n2",
                "label":    "uzmanlık alanı",
                "strength": 0.8
            }, ...
        ],
        "central_node": "n1"
    }

    Kategoriler:
        identity  — kim olduğu (unvan, alan, marka kimliği)
        expertise — somut beceriler, araçlar, teknik yetkinlikler
        value     — çalışma felsefesi, vibe, differentiator
        goal      — hedef kitle, kariyer hedefleri, CTA odağı
        interest  — postlardan ve geçmişten çıkan ilgi alanları
    """
    full_name    = profile.get('full_name', '')
    category     = profile.get('profession_category', '')
    job_title    = profile.get('job_title', '')
    bio          = profile.get('bio', '')
    skills       = profile.get('skills', '')
    vibe         = profile.get('vibe', '')
    target_aud   = profile.get('target_audience', '')
    achievement  = profile.get('achievement', '')
    differentiator = profile.get('differentiator', '')
    brand_name   = profile.get('brand_name', '')
    brand_tagline = profile.get('brand_tagline', '')
    services_raw = profile.get('services_raw', '')
    headline     = profile.get('headline', '')
    tagline      = profile.get('tagline', '')
    status_text  = profile.get('status_text', '')
    work_type    = profile.get('work_type', '')

    # Gönderileri tek bir blok olarak birleştir (en fazla 30 gönderi, 200 kar/gönderi)
    posts_block = ''
    if posts:
        trimmed = [p[:200].strip() for p in posts[:30] if p and p.strip()]
        if trimmed:
            posts_block = '\n'.join(f'- {t}' for t in trimmed)

    prompt = f"""Sen bir dijital kimlik analisti ve zihin haritası uzmanısın.
Aşağıdaki kullanıcı verisini derinlemesine analiz et ve bu kişinin özgün dijital kimliğini
birbirine bağlı düğümler ve ilişkilerden oluşan bir Zihin Haritası olarak modelleştir.

═══ KULLANICI PROFİLİ ═══
İsim: {full_name}
Alan / Kategori: {category}
Unvan: {job_title}
Kendi anlatımı: {bio}
Uzmanlık / Beceriler: {skills}
Ton / Vibe: {vibe}
Hedef kitle: {target_aud}
En büyük başarısı: {achievement}
Rakiplerden ayıran özelliği: {differentiator}
Marka adı: {brand_name}
Marka sloganı: {brand_tagline}
Hizmetler: {services_raw}
Landing headline: {headline}
Landing tagline: {tagline}
Güncel durum: {status_text}
Çalışma biçimi: {work_type}

═══ PLATFORM GÖNDERİLERİ (son 30) ═══
{posts_block if posts_block else '(henüz gönderi yok)'}

═══ GÖREV ═══
Bu verilerden yola çıkarak:
1. 12-18 adet düğüm (node) belirle — her biri bu kişinin kimliğinin gerçek bir parçası olmalı.
2. Düğümleri 5 kategoriye dağıt:
   - identity  : Kim olduğu, ana unvanı, alanı (2-3 düğüm)
   - expertise : Somut beceriler, araçlar, teknik yetkinlikler (4-5 düğüm)
   - value     : Çalışma felsefesi, vibe, differentiator, değerler (2-3 düğüm)
   - goal      : Hedef kitle, kariyer yönü, misyon (2-3 düğüm)
   - interest  : Gönderilerden ve profilden çıkan ilgi alanları/tutkular (2-3 düğüm)
3. Her düğüme 1-10 arası weight ver (10 = en merkezi, en belirleyici).
4. Düğümler arasında anlamlı ilişkiler (edge) kur — en az 15, en fazla 25 edge.
   - label: ilişkiyi kısa ve Türkçe özetle (örn: "güçlendirir", "hedefler", "kullanır")
   - strength: 0.1-1.0 arası (1.0 = çok güçlü ilişki)
5. Merkezi düğümü (central_node) belirle: bu kişiyi en iyi tanımlayan tek düğüm.

═══ KURALLAR ═══
- Düğüm label'ları kısa ve net olsun (maks 4 kelime).
- description: o düğümün bu kişi için neden önemli olduğunu 1 cümleyle açıkla.
- Jenerik klişelerden kaç ("Çalışkanlık", "Başarı" gibi) — bu kişiye ÖZGÜ olsun.
- Gönderilerden ilgi alanları, tekrarlayan temalar ve tutkular çıkar.
- Tüm metin Türkçe olmalı.
- node id'leri: "n1", "n2", ... formatında.

═══ ÇIKTI FORMATI ═══
Sadece aşağıdaki JSON yapısını döndür:

{{
  "nodes": [
    {{"id": "n1", "label": "...", "category": "identity", "weight": 10, "description": "..."}},
    ...
  ],
  "edges": [
    {{"source": "n1", "target": "n2", "label": "...", "strength": 0.9}},
    ...
  ],
  "central_node": "n1"
}}"""

    client = get_client()

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen bir dijital kimlik analisti ve zihin haritası uzmanısın. '
                    'Her zaman sadece geçerli JSON döndürürsün, başka hiçbir şey yazmazsın.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.72,
        max_tokens=2400,
        response_format={'type': 'json_object'},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


# ─── Aura Analizi ─────────────────────────────────────────────────────────────

def generate_aura_analysis(
    profile_a: dict, map_a: dict,
    profile_b: dict, map_b: dict,
    common_follows: list[dict] | None = None,
) -> dict:
    """
    İki kullanıcının profil + zihin haritasını karşılaştırarak kapsamlı Aura Analizi üretir.

    Dönen yapı:
    {
        "aura_score": 87,
        "aura_label": "Derin Rezonans",
        "aura_subtitle": "...",
        "similarity_ratio": 74,
        "chemistry_tags": ["...", "..."],
        "synergies": [{"title": "...", "detail": "..."}, ...],          # Faz 2
        "common_activities": [                                           # Faz 3
            {"title": "...", "description": "...", "why": "...", "icon": "💡"}, ...
        ],
        "connection_analysis": {                                         # Faz 4
            "summary": "...",
            "insights": [{"title": "...", "detail": "..."}, ...]
        },
        "zitliklar": [                                                   # Faz 5
            {"title": "...", "detail": "...", "yorum": "...", "icon": "⚡"}
        ]
    }
    """

    def _fmt_map(m: dict) -> str:
        if not m or not m.get('nodes'):
            return '(zihin haritası yok)'
        return ', '.join(
            f'{n["label"]} [{n["category"]}, w={n["weight"]}]'
            for n in m.get('nodes', [])
        )

    def _fmt_profile(p: dict) -> str:
        lines = []
        if p.get('full_name'):           lines.append(f'İsim: {p["full_name"]}')
        if p.get('job_title'):           lines.append(f'Unvan: {p["job_title"]}')
        if p.get('profession_category'): lines.append(f'Alan: {p["profession_category"]}')
        if p.get('bio'):                 lines.append(f'Bio: {p["bio"][:300]}')
        if p.get('skills'):              lines.append(f'Beceriler: {p["skills"][:200]}')
        if p.get('vibe'):                lines.append(f'Vibe: {p["vibe"]}')
        if p.get('target_audience'):     lines.append(f'Hedef kitle: {p["target_audience"]}')
        if p.get('achievement'):         lines.append(f'Başarısı: {p["achievement"][:150]}')
        if p.get('differentiator'):      lines.append(f'Fark yaratan: {p["differentiator"][:150]}')
        if p.get('work_type'):           lines.append(f'Çalışma biçimi: {p["work_type"]}')
        return '\n'.join(lines) if lines else '(profil verisi yok)'

    # Ortak takip edilenler bloğu
    common_follows_block = '(ortak takip edilen profil bulunamadı)'
    if common_follows:
        rows = []
        for u in common_follows[:15]:
            parts = []
            if u.get('name'):     parts.append(u['name'])
            if u.get('title'):    parts.append(u['title'])
            if u.get('category'): parts.append(f'[{u["category"]}]')
            rows.append('- ' + ', '.join(parts))
        if rows:
            common_follows_block = '\n'.join(rows)

    prompt = f"""Sen iki profesyonelin dijital kimliğini, zihin haritalarını, profillerini ve
sosyal bağlantı örüntülerini derinlemesine karşılaştıran bir "Dijital Aura Analisti"sin.
Aşağıdaki verileri analiz ederek 5 katmanlı kapsamlı bir Aura Raporu oluştur.

══════════════════════════════════
KİŞİ A
══════════════════════════════════
{_fmt_profile(profile_a)}

Zihin Haritası Düğümleri:
{_fmt_map(map_a)}

══════════════════════════════════
KİŞİ B
══════════════════════════════════
{_fmt_profile(profile_b)}

Zihin Haritası Düğümleri:
{_fmt_map(map_b)}

══════════════════════════════════
ORTAK TAKİP EDİLEN PROFİLLER
══════════════════════════════════
{common_follows_block}

══════════════════════════════════
GÖREV — 7 KATMAN
══════════════════════════════════
1. AURA SKORU (0-100): İki insanın enerjik/profesyonel uyumunu, sinerji potansiyelini
   ve karşılıklı değer yaratma kapasitesini puanla.
   90-100: Nadir rezonans | 75-89: Güçlü sinerji | 60-74: Anlamlı bağ
   40-59: Tamamlayıcı farklılıklar | 0-39: Zıt enerjiler

2. AURA ETİKETİ: Skoru yansıtan poetik, özgün bir isim (örn: "Derin Rezonans",
   "Tamamlayıcı Güç", "Sessiz Anlayış", "Karşıt Mıknatıslar").

3. BENZERLİK ORANI: Düğüm ve profil örtüşmesine göre % (0-100).

4. SİNERJİLER: İki kişinin güçlü örtüşme noktaları (max 4 madde).

5. ORTAK FAALİYETLER: Birlikte yapabilecekleri gerçekçi, özgün aktiviteler/projeler
   (4-6 adet). Profillerine özel, klişelerden uzak öneriler.

6. BAĞLANTI ANALİZİ: Ortak takip ettikleri profiller üzerinden analiz yap.
   - Bu kişilerin ortak ilgi evreni ne söylüyor?
   - Hangi fikir liderlerini, toplulukları veya alanları birlikte takip ediyorlar?
   - Bu ortak bağlantılar iki profil arasında nasıl bir köprü kuruyor?
   Eğer ortak takip yoksa, dijital çevrelerinin nasıl kesişebileceğini öner.

7. ZITLIKLAR: Bu iki kişiyi birbirinden ayıran, ancak potansiyel olarak tamamlayıcı olan
   temel farklılıkları analiz et (3-4 madde). Her zıtlık için:
   - Ne bakımından farklılar?
   - Bu fark onları nasıl tamamlar veya çatıştırır?
   - AI yorumu: Bu zıtlık ilişkileri için ne anlama gelir?

══════════════════════════════════
ÇIKTI FORMATI — SADECE JSON DÖN
══════════════════════════════════
{{
  "aura_score": 87,
  "aura_label": "Derin Rezonans",
  "aura_subtitle": "Bu iki kişinin enerjisi birbirini tamamlar nitelikte...",
  "similarity_ratio": 74,
  "chemistry_tags": ["Yaratıcı Enerji", "Ortak Vizyon", "..."],
  "synergies": [
    {{"title": "Kısa başlık", "detail": "Açıklama cümlesi"}},
    {{"title": "...", "detail": "..."}}
  ],
  "common_activities": [
    {{
      "title": "Aktivite adı",
      "description": "Ne yapacaklar ve nasıl",
      "why": "Bu ikili için neden ideal",
      "icon": "🎯"
    }}
  ],
  "connection_analysis": {{
    "summary": "Ortak takip ettikleri profiller üzerinden 2-3 cümlelik genel yorum",
    "insights": [
      {{"title": "Ortak İlgi Evreni", "detail": "Açıklama"}},
      {{"title": "Köprü Bağlantılar", "detail": "Açıklama"}}
    ]
  }},
  "zitliklar": [
    {{
      "title": "Zıtlık adı (kısa)",
      "detail": "Bu iki kişi bu bakımdan nasıl farklı?",
      "yorum": "AI yorumu: Bu zıtlık ne anlama geliyor?",
      "icon": "⚡"
    }}
  ]
}}"""

    client = get_client()

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {
                'role': 'system',
                'content': (
                    'Sen iki profesyonelin dijital kimliğini karşılaştıran bir "Dijital Aura Analisti"sin. '
                    'Her zaman sadece geçerli JSON döndürürsün, başka hiçbir şey yazmazsın. '
                    'Analizin derin, özgün ve kişiye özel olmalı — jenerik klişelerden kaçın. '
                    'Zıtlıklar bölümünde cesur ve dürüst ol, olumlu bir çerçevede sun.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.78,
        max_tokens=3600,
        response_format={'type': 'json_object'},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)
