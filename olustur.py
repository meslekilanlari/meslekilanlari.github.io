"""
Telegram meslek kanalları tanıtım sitesi üreticisi (GitHub Pages).

Kullanım:
  python olustur.py --taban https://KULLANICI.github.io [--csv gunluk.csv ...] [--davet davet_baglantilari.csv]

Ürettikleri:
  index.html                  ana sayfa (kanallar + bugünün ilanları)
  kanal/<ad>/index.html       her kanal: özgün tanıtım, SSS, güncel ilanlar, son paylaşımlar
  ilan/<kimlik>/index.html    her açık ilan için ayrı sayfa + Google JobPosting yapılandırılmış verisi
  sitemap.xml, robots.txt, 404.html, img/og/*.png (paylaşım önizlemeleri), favicon.png
Geçmiş: veri.json (son paylaşımlar), ilanlar.json (açık ilanlar). Süresi geçen ilan sayfaları silinir.
"""
import argparse
import csv
import hashlib
import html
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from icerik import ICERIK

KOK = Path(__file__).resolve().parent
SON_N = 15
ILAN_GUN = 30  # son başvuru tarihi olmayan ilanlar en fazla bu kadar gün yayında kalır
SITE_ADI = "Meslek ve İş İlanı Telegram Kanalları"

AILELER = [
    ("Özel Güvenlik", "#13294B", "#2B5A8C", ["ozelguvenlikilan_tr", "ogg_sinav", "ozelguvenliksinavi"]),
    ("Öğretmen", "#B4541A", "#E8892E", ["ogretmen_isilani", "ags_hazirlik", "evrak_ogretmen"]),
    ("Hemşire ve Sağlık", "#0B6E70", "#18A2A0", ["hemsire_isilanlari", "yurtdisi_hemsire", "saglik_atama"]),
    ("Eczane ve İlaç Sektörü", "#1F6B43", "#36A36A", ["eczane_isilani", "devir_eczane", "mumessil_ilan", "utt_sinav"]),
    ("İş Güvenliği", "#B87A00", "#F2B705", ["isguzmani_sinav"]),
    ("KPSS ve Kamu", "#8E1F1A", "#D2463B", ["kpss_gunluksoru", "kpsstercih_tr", "kamu_alimlari", "sinav_gorevi"]),
]
RENK = {k: (c1, c2, ad) for ad, c1, c2, lst in AILELER for k in lst}
KANAL = {
    "ozelguvenlikilan_tr": ("Özel Güvenlik İş İlanları – Türkiye", "Türkiye geneli özel güvenlik (ÖGG) iş ilanları: silahlı ve silahsız güvenlik görevlisi alımları, il, maaş ve son başvuru bilgisiyle. Her gün güncel ve reklamsız.", "özel güvenlik iş ilanları, güvenlik görevlisi alımı, ÖGG iş ilanı, silahsız güvenlik iş ilanları"),
    "ogg_sinav": ("ÖGG Sınav Hazırlık – Günlük Soru", "Özel güvenlik temel ve yenileme sınavına her gün çözümlü soru, quiz ve konu özeti. Sınav takvimi ve geri sayım.", "özel güvenlik sınav soruları, ÖGG sınavı, özel güvenlik test, yenileme sınavı"),
    "ozelguvenliksinavi": ("Özel Güvenlik Sınavı – Çıkmış Sorular ve PDF", "Özel güvenlik temel ve yenileme sınavı için ücretsiz konu özeti ve çözümlü soru PDF arşivi.", "özel güvenlik sınavı pdf, ÖGG soru bankası, özel güvenlik konu özeti"),
    "ogretmen_isilani": ("Öğretmen İş İlanları – Reklamsız", "Özel okul, kurs ve dershane öğretmen iş ilanları; branş ve il etiketli, reklamsız. Her gün güncel.", "öğretmen iş ilanları, özel okul öğretmen ilanı, ücretli öğretmenlik, dershane öğretmen ilanı"),
    "ags_hazirlik": ("AGS ve ÖABT Hazırlık – Günlük Soru", "MEB Akademi Giriş Sınavı (AGS) ve ÖABT için her gün çözümlü soru, konu özeti ve haftalık deneme.", "AGS soruları, akademi giriş sınavı, ÖABT soruları, MEB AGS hazırlık"),
    "evrak_ogretmen": ("Öğretmen Evrak ve Materyal", "Zümre tutanağı, veli toplantısı tutanağı, rehberlik formu ve yıllık plan gibi öğretmen evrakları; ücretsiz ve sınıf/branş etiketli.", "öğretmen evrakları, zümre tutanağı, veli toplantısı tutanağı, yıllık plan"),
    "hemsire_isilanlari": ("Hemşire ve Sağlık Personeli İş İlanları", "Hemşire, ebe, ATT, paramedik ve sağlık personeli iş ilanları; özel hastane, OSGB, huzurevi ve nöbet ilanları.", "hemşire iş ilanları, sağlık personeli alımı, ebe iş ilanı, ATT iş ilanı"),
    "yurtdisi_hemsire": ("Yurt Dışında Hemşirelik – Almanya ve İngiltere", "Almanya ve İngiltere'de hemşire olmak için denklik, dil sınavı, vize ve maaş rehberi.", "Almanya'da hemşirelik, İngiltere hemşire, hemşire denklik, yurt dışı hemşire"),
    "saglik_atama": ("Sağlıkçı Atama ve KPSS", "Sağlık Bakanlığı atama takvimi, KPSS taban puanları ve tercih rehberi.", "sağlık atama, hemşire ataması, KPSS sağlık taban puan"),
    "eczane_isilani": ("Eczacı ve Eczane Teknikeri İlanları", "İkinci eczacı, eczane teknikeri ve kalfa iş ilanları; SGK ve mevzuat özetleri.", "eczane teknikeri iş ilanı, eczacı iş ilanı, eczane kalfa ilanı"),
    "devir_eczane": ("Devir Eczane Vitrini", "Türkiye geneli devir ve satılık eczane ilanları; il, ciro aralığı ve reçete bilgisiyle.", "devir eczane, satılık eczane, eczane devri"),
    "mumessil_ilan": ("Tıbbi Mümessil ve Medikal Satış İlanları", "İlaç ve medikal firmalarının tıbbi tanıtım temsilcisi ve satış ilanları; firma, bölge ve yan haklarıyla.", "tıbbi mümessil iş ilanı, tıbbi tanıtım temsilcisi, medikal satış ilanı"),
    "utt_sinav": ("ÜTT Sınavı ve Mümessil Kariyer Rehberi", "Ürün Tanıtım Temsilcisi (ÜTT) yeterlilik belgesi, sınav notları ve tıbbi mümessillik kariyer rehberi.", "ÜTT sınavı, ürün tanıtım temsilcisi belgesi, mümessil olmak"),
    "isguzmani_sinav": ("İş Güvenliği (İSG) Uzmanlığı – Sınav ve İlan", "İSG uzmanlık sınavına günlük soru ve PDF, mevzuat özetleri, OSGB ve iş güvenliği uzmanı ilanları.", "İSG sınav soruları, iş güvenliği uzmanı ilanı, OSGB iş ilanı"),
    "kpss_gunluksoru": ("KPSS Günlük Soru ve Notlar", "Her gün 1 konu, madde madde özet ve sorular; KPSS genel kültür ve genel yetenek.", "KPSS soruları, KPSS günlük soru, KPSS notları, genel kültür soruları"),
    "kpsstercih_tr": ("KPSS Tercih ve Atama Takvimi", "KPSS tercih kılavuzu, taban puanları ve atama sonuçları.", "KPSS tercih, KPSS atama takvimi, KPSS taban puanlar"),
    "kamu_alimlari": ("Kamu Personel Alımları – Eğitim Düzeyine Göre", "Memur ve sözleşmeli personel alımları; lise, önlisans ve lisans etiketli, son başvuru tarihleriyle.", "kamu personel alımı, memur alımı, sözleşmeli personel ilanları, KPSS'siz alım"),
    "sinav_gorevi": ("Sınav Görevleri ve Ek Gelir", "ÖSYM, MEB ve AÖF sınav görevi başvuru tarihleri ve güncel ücret tabloları.", "sınav görevi, ÖSYM görevli başvurusu, MEB sınav görevi ücretleri"),
}

CSS = """*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1d1d1f;background:#f6f6f4;line-height:1.6}
a{color:inherit}header.ust{padding:40px 20px 16px;max-width:960px;margin:auto}h1{font-size:2rem;line-height:1.25;margin:0 0 8px}h2{font-size:1.25rem;margin:28px 0 12px}
.alt{color:#555;margin:0}main{max-width:960px;margin:auto;padding:0 20px 60px}.aile{margin:24px 0}.aile h2{font-size:1.1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.kart{display:flex;gap:12px;align-items:center;background:#fff;border-radius:14px;padding:12px;text-decoration:none;border:1px solid #e6e6e2}
.kart:hover{border-color:#bbb}.kart img{width:56px;height:56px;border-radius:50%;flex:none}.kart b{display:block;font-size:.95rem}.kart span{font-size:.82rem;color:#666}
.bant{color:#fff;padding:36px 20px}.bant .ic{max-width:960px;margin:auto;display:flex;gap:20px;align-items:center}
.bant img{width:96px;height:96px;border-radius:50%;border:3px solid #fff;flex:none}.bant h1{color:#fff}.bant p{color:#eef;margin:4px 0 0}
.btn{display:inline-block;margin-top:14px;background:#fff;color:#111;padding:10px 18px;border-radius:999px;font-weight:600;text-decoration:none}
.btn.koyu{background:#111;color:#fff}.metin p{margin:0 0 12px}
.gonderi{background:#fff;border:1px solid #e6e6e2;border-radius:12px;padding:14px 16px;margin:10px 0;white-space:pre-wrap;font-size:.95rem}
.gonderi small{display:block;color:#888;margin-bottom:6px}.liste a{display:block;background:#fff;border:1px solid #e6e6e2;border-radius:12px;padding:12px 16px;margin:8px 0;text-decoration:none}
.liste a b{display:block}.liste a span{color:#666;font-size:.85rem}details{background:#fff;border:1px solid #e6e6e2;border-radius:12px;padding:12px 16px;margin:8px 0}
summary{font-weight:600;cursor:pointer}nav.yol{font-size:.85rem;color:#666;margin:14px 0}nav.yol a{text-decoration:none}
footer{text-align:center;color:#888;font-size:.85rem;padding:30px}"""


def e(s):
    return html.escape(s or "", quote=True)


def slug(s):
    tr = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
    s = (s or "").translate(tr).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def sayfa(baslik, aciklama, kanonik, govde, jsonld, gorsel, kelimeler="", robots="index,follow"):
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in jsonld)
    return (f'<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(baslik)}</title><meta name="description" content="{e(aciklama)}">'
            + (f'<meta name="keywords" content="{e(kelimeler)}">' if kelimeler else "")
            + f'<meta name="robots" content="{robots}"><link rel="canonical" href="{e(kanonik)}">'
            f'<link rel="icon" type="image/png" href="/favicon.png"><meta name="theme-color" content="#13294B">'
            f'<meta property="og:locale" content="tr_TR"><meta property="og:site_name" content="{e(SITE_ADI)}">'
            f'<meta property="og:title" content="{e(baslik)}"><meta property="og:description" content="{e(aciklama)}">'
            f'<meta property="og:type" content="website"><meta property="og:url" content="{e(kanonik)}">'
            f'<meta property="og:image" content="{e(gorsel)}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta name="twitter:card" content="summary_large_image">{ld}<style>{CSS}</style></head><body>{govde}'
            f'<footer>{e(SITE_ADI)} · son güncelleme {date.today():%d.%m.%Y}</footer></body></html>')


def temizle(metin):
    return re.sub(r"↪️.*", "", metin or "").strip()


# ---------- ilan ayrıştırma ----------
def ilan_ayristir(r):
    """İlan kartından JobPosting için gereken alanları çıkarır; ilan değilse None."""
    m = r.get("metin") or ""
    if "💼" not in m or "📍" not in m:
        return None
    satir = {s.strip()[:2]: s.strip() for s in m.splitlines() if s.strip()}
    yer = next((s for s in m.splitlines() if "📍" in s), "")
    is_ = next((s for s in m.splitlines() if "💼" in s), "")
    etiketler = re.findall(r"#(\w+)", yer.split("·")[0])
    if not etiketler:
        return None
    pozisyon, _, firma = is_.replace("💼", "").strip().partition("—")
    pozisyon, firma = pozisyon.strip(), firma.strip()
    if not pozisyon or not firma:
        return None
    url = (re.search(r"https?://\S+", next((s for s in m.splitlines() if "🔗" in s), "")) or [None])[0]
    if not url:
        return None
    yayin = r["tarih"]
    son = None
    sb = re.search(r"Son başvuru:\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", m)
    if sb:
        g, a, y = int(sb.group(1)), int(sb.group(2)), sb.group(3)
        yil = int(y) if y else int(yayin[:4])
        if not y and a < int(yayin[5:7]):
            yil += 1
        try:
            son = f"{date(yil, a, g)}"
        except ValueError:
            son = None
    maas = next((s.replace("💰", "").strip() for s in m.splitlines() if "💰" in s), "")
    kimlik = hashlib.sha1(f"{r['kanal']}|{pozisyon}|{firma}|{url}".encode()).hexdigest()[:8]
    return {
        "kimlik": f"{yayin}-{slug(pozisyon)}-{slug(firma)}-{kimlik}"[:110],
        "kanal": r["kanal"].lstrip("@").lower(), "yayin": yayin, "son": son,
        "il": etiketler[0], "ilce": etiketler[1] if len(etiketler) > 1 else "",
        "pozisyon": pozisyon, "firma": firma, "maas": maas, "url": url,
        "etiketler": re.findall(r"#(\w+)", yer.split("·")[1]) if "·" in yer else [],
        "metin": temizle(m),
    }


def ilan_acik_mi(i, bugun):
    if i["son"]:
        return i["son"] >= f"{bugun}"
    return i["yayin"] >= f"{bugun - timedelta(days=ILAN_GUN)}"


# ---------- görseller ----------
def gorselleri_hazirla(taban):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    og = KOK / "img" / "og"
    og.mkdir(parents=True, exist_ok=True)
    fontlar = ["/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    fyol = next((f for f in fontlar if Path(f).exists()), None)

    def font(n):
        return ImageFont.truetype(fyol, n) if fyol else ImageFont.load_default()

    def degrade(c1, c2, w, h):
        a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
        im = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(im)
        for x in range(w):
            t = x / w
            d.line([(x, 0), (x, h)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
        return im

    def yaz_sar(d, metin, f, x, y, genislik, renk):
        kelime, satir = metin.split(), ""
        for k in kelime:
            dene = (satir + " " + k).strip()
            if d.textlength(dene, font=f) > genislik and satir:
                d.text((x, y), satir, font=f, fill=renk)
                y += f.size + 12
                satir = k
            else:
                satir = dene
        d.text((x, y), satir, font=f, fill=renk)

    for k, (c1, c2, _) in RENK.items():
        hedef = og / f"{k}.png"
        if hedef.exists():
            continue
        im = degrade(c1, c2, 1200, 630)
        d = ImageDraw.Draw(im)
        prof = KOK / "img" / f"{k}.jpg"
        if prof.exists():
            p = Image.open(prof).convert("RGB").resize((300, 300))
            mask = Image.new("L", (300, 300), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 300, 300], fill=255)
            im.paste(p, (70, 165), mask)
        yaz_sar(d, KANAL[k][0], font(58), 420, 190, 720, "white")
        d.text((420, 470), f"t.me/{k}", font=font(36), fill=(255, 255, 255))
        im.save(hedef, optimize=True)
    ana = og / "ana.png"
    if not ana.exists():
        im = degrade("#13294B", "#2B5A8C", 1200, 630)
        d = ImageDraw.Draw(im)
        yaz_sar(d, SITE_ADI, font(70), 80, 200, 1040, "white")
        d.text((80, 470), "Özel güvenlik · Öğretmen · Hemşire · Eczane · KPSS · Kamu", font=font(32), fill=(220, 230, 255))
        im.save(ana, optimize=True)
    fav = KOK / "favicon.png"
    if not fav.exists():
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([0, 0, 63, 63], fill="#13294B")
        f = font(30)
        w = d.textlength("İŞ", font=f)
        d.text(((64 - w) / 2, 14), "İŞ", font=f, fill="white")
        im.save(fav)


# ---------- ana akış ----------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--taban", required=True)
    p.add_argument("--csv", nargs="*", default=[])
    p.add_argument("--davet")
    a = p.parse_args()
    taban = a.taban.rstrip("/")
    bugun = date.today()

    katil = {k: f"https://t.me/{k}" for k in KANAL}
    if a.davet and Path(a.davet).exists():
        with open(a.davet, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = r["kanal"].lstrip("@").lower()
                if r["kaynak"] == "google" and k in katil:
                    katil[k] = r["baglanti"]

    # verileri oku ve geçmişle birleştir
    son = {k: [] for k in KANAL}
    ilanlar = {i["kimlik"]: i for i in json.loads((KOK / "ilanlar.json").read_text(encoding="utf-8"))} \
        if (KOK / "ilanlar.json").exists() else {}
    for yol in sorted(a.csv):
        with open(yol, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = r.get("kanal", "").lstrip("@").lower()
                if k not in KANAL or r.get("tur") not in ("metin", "quiz", "anket") or not r.get("metin"):
                    continue
                if "@ihsantayfun" in r["metin"]:
                    continue
                son[k].append((r["tarih"], r["saat"], r["tur"], temizle(r["metin"])))
                i = ilan_ayristir(r)
                if i:
                    ilanlar.setdefault(i["kimlik"], i)
    gecmis = KOK / "veri.json"
    eski = json.loads(gecmis.read_text(encoding="utf-8")) if gecmis.exists() else {}
    for k in KANAL:
        birlesik = {tuple(x) for x in eski.get(k, [])} | set(son[k])
        son[k] = sorted(birlesik, key=lambda x: (x[0], x[1]), reverse=True)[:SON_N]
    gecmis.write_text(json.dumps(son, ensure_ascii=False), encoding="utf-8")
    acik = sorted((i for i in ilanlar.values() if ilan_acik_mi(i, bugun)), key=lambda i: i["yayin"], reverse=True)
    (KOK / "ilanlar.json").write_text(json.dumps(acik, ensure_ascii=False), encoding="utf-8")

    gorselleri_hazirla(taban)
    org = {"@type": "Organization", "name": SITE_ADI, "url": f"{taban}/", "logo": f"{taban}/favicon.png"}

    # ilan sayfaları (süresi geçenler silinir)
    shutil.rmtree(KOK / "ilan", ignore_errors=True)
    for i in acik:
        k = i["kanal"]
        c1, c2, aile = RENK.get(k, ("#13294B", "#2B5A8C", ""))
        baslik = f"{i['pozisyon']} – {i['firma']} ({i['il']})"
        aciklama = f"{i['firma']} {i['il']}{' ' + i['ilce'] if i['ilce'] else ''} için {i['pozisyon']} arıyor." + \
                   (f" Son başvuru {i['son'][8:10]}.{i['son'][5:7]}.{i['son'][:4]}." if i["son"] else "")
        jp = {"@context": "https://schema.org", "@type": "JobPosting", "title": i["pozisyon"],
              "description": "<p>" + "<br>".join(e(s) for s in i["metin"].splitlines()) + "</p>",
              "datePosted": i["yayin"], "hiringOrganization": {"@type": "Organization", "name": i["firma"]},
              "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": i["ilce"] or i["il"],
                                                             "addressRegion": i["il"], "addressCountry": "TR"}},
              "directApply": False, "url": f"{taban}/ilan/{i['kimlik']}/"}
        if i["son"]:
            jp["validThrough"] = f"{i['son']}T23:59:59+03:00"
        yol = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Ana sayfa", "item": f"{taban}/"},
            {"@type": "ListItem", "position": 2, "name": KANAL.get(k, (k,))[0], "item": f"{taban}/kanal/{k}/"},
            {"@type": "ListItem", "position": 3, "name": baslik}]}
        govde = (f'<div class="bant" style="background:linear-gradient(135deg,{c1},{c2})"><div class="ic"><div>'
                 f'<h1>{e(i["pozisyon"])}</h1><p>{e(i["firma"])} · {e(i["il"])}{" / " + e(i["ilce"]) if i["ilce"] else ""}</p>'
                 f'<a class="btn" href="{e(i["url"])}" rel="nofollow noopener" target="_blank">İlana başvur (kaynak site)</a></div></div></div>'
                 f'<main><nav class="yol"><a href="/">Ana sayfa</a> › <a href="/kanal/{k}/">{e(KANAL.get(k, (k,))[0])}</a></nav>'
                 f'<article class="gonderi">{e(i["metin"])}</article>'
                 f'<p>Yayın tarihi: {i["yayin"][8:10]}.{i["yayin"][5:7]}.{i["yayin"][:4]}'
                 + (f' · Son başvuru: {i["son"][8:10]}.{i["son"][5:7]}.{i["son"][:4]}' if i["son"] else "") + '</p>'
                 f'<p>Bu ilan kaynağından doğrulanarak derlenmiştir; başvuru kaynak site üzerinden yapılır.</p>'
                 f'<a class="btn koyu" href="{e(katil.get(k, "https://t.me/" + k))}">Benzer ilanlar için Telegram kanalına katıl</a></main>')
        hedef = KOK / "ilan" / i["kimlik"]
        hedef.mkdir(parents=True, exist_ok=True)
        (hedef / "index.html").write_text(sayfa(f"{baslik} | İş İlanı", aciklama, f"{taban}/ilan/{i['kimlik']}/",
                                                govde, [jp, yol], f"{taban}/img/og/{k}.png"), encoding="utf-8")

    def ilan_listesi(lst):
        return '<div class="liste">' + "".join(
            f'<a href="/ilan/{i["kimlik"]}/"><b>{e(i["pozisyon"])} – {e(i["firma"])}</b>'
            f'<span>{e(i["il"])}{" / " + e(i["ilce"]) if i["ilce"] else ""} · {i["yayin"][8:10]}.{i["yayin"][5:7]}'
            + (f' · son başvuru {i["son"][8:10]}.{i["son"][5:7]}' if i["son"] else "") + '</span></a>' for i in lst) + "</div>"

    # kanal sayfaları
    for ad, c1, c2, liste in AILELER:
        for k in liste:
            bas, aciklama, kelime = KANAL[k]
            ic = ICERIK[k]
            kanal_ilan = [i for i in acik if i["kanal"] == k][:20]
            gonderiler = "".join(
                f'<article class="gonderi"><small>{t[0][8:10]}.{t[0][5:7]}.{t[0][:4]} {t[1]}'
                f'{" · soru" if t[2] in ("quiz", "anket") else ""}</small>{e(t[3])}</article>' for t in son[k]
            ) or '<p>İlk paylaşımlar çok yakında burada.</p>'
            kardes = "".join(f'<a class="kart" href="/kanal/{x}/"><img src="/img/{x}.jpg" alt="{e(KANAL[x][0])} logosu" width="56" height="56" loading="lazy">'
                             f'<div><b>{e(KANAL[x][0])}</b><span>@{x}</span></div></a>' for x in liste if x != k)
            sss_html = "".join(f"<details><summary>{e(s)}</summary><p>{e(c)}</p></details>" for s, c in ic["sss"])
            govde = (f'<div class="bant" style="background:linear-gradient(135deg,{c1},{c2})"><div class="ic">'
                     f'<img src="/img/{k}.jpg" alt="{e(bas)} logosu" width="96" height="96"><div><h1>{e(ic["baslik"])}</h1><p>{e(aciklama)}</p>'
                     f'<a class="btn" href="{e(katil[k])}">Telegram\'da katıl · @{k}</a></div></div></div>'
                     f'<main><nav class="yol"><a href="/">Ana sayfa</a> › {e(ad)} › {e(bas)}</nav>'
                     f'<section class="metin">{"".join(f"<p>{e(x)}</p>" for x in ic["giris"])}</section>'
                     + (f'<h2>Güncel ilanlar</h2>{ilan_listesi(kanal_ilan)}' if kanal_ilan else "")
                     + f'<h2>Son paylaşımlar</h2>{gonderiler}'
                     f'<h2>Sık sorulan sorular</h2>{sss_html}'
                     + (f'<h2>Aynı aileden kanallar</h2><div class="grid">{kardes}</div>' if kardes else "")
                     + '<p><a href="/">← Tüm kanallar</a></p></main>')
            jsonld = [
                {"@context": "https://schema.org", "@type": "WebPage", "name": ic["baslik"], "description": aciklama,
                 "url": f"{taban}/kanal/{k}/", "inLanguage": "tr", "publisher": org,
                 "about": {"@type": "Thing", "name": bas, "sameAs": f"https://t.me/{k}"}},
                {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Ana sayfa", "item": f"{taban}/"},
                    {"@type": "ListItem", "position": 2, "name": bas, "item": f"{taban}/kanal/{k}/"}]},
                {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": s, "acceptedAnswer": {"@type": "Answer", "text": c}} for s, c in ic["sss"]]},
            ]
            hedef = KOK / "kanal" / k
            hedef.mkdir(parents=True, exist_ok=True)
            (hedef / "index.html").write_text(sayfa(f"{ic['baslik']} | Telegram", aciklama, f"{taban}/kanal/{k}/",
                                                    govde, jsonld, f"{taban}/img/og/{k}.png", kelime), encoding="utf-8")

    # ana sayfa
    bloklar = []
    for ad, c1, c2, liste in AILELER:
        kartlar = "".join(
            f'<a class="kart" href="/kanal/{k}/"><img src="/img/{k}.jpg" alt="{e(KANAL[k][0])} logosu" width="56" height="56" loading="lazy">'
            f'<div><b>{e(KANAL[k][0])}</b><span>@{k}</span></div></a>' for k in liste)
        bloklar.append(f'<section class="aile"><h2 style="color:{c1}">{e(ad)} Telegram kanalları</h2><div class="grid">{kartlar}</div></section>')
    govde = ('<header class="ust"><h1>Meslek ve İş İlanı Telegram Kanalları</h1>'
             '<p class="alt">Özel güvenlik, öğretmen, hemşire, eczane, tıbbi mümessil, iş güvenliği, KPSS ve kamu personel alımları için '
             'her gün güncellenen, reklamsız Telegram kanalları. İlanlar kaynağından doğrulanır, sınav kanallarında her gün çözümlü soru paylaşılır.</p></header><main>'
             + (f'<h2>Son eklenen ilanlar</h2>{ilan_listesi(acik[:12])}' if acik else "")
             + "".join(bloklar) + "</main>")
    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_ADI, "url": f"{taban}/", "inLanguage": "tr", "publisher": org},
        {"@context": "https://schema.org", **org},
        {"@context": "https://schema.org", "@type": "ItemList", "name": SITE_ADI, "itemListElement": [
            {"@type": "ListItem", "position": n + 1, "url": f"{taban}/kanal/{k}/", "name": KANAL[k][0]} for n, k in enumerate(KANAL)]},
    ]
    (KOK / "index.html").write_text(sayfa(
        "İş İlanı Telegram Kanalları | Özel Güvenlik, Öğretmen, Hemşire, KPSS",
        "Özel güvenlik, öğretmen, hemşire, eczane, tıbbi mümessil, İSG, KPSS ve kamu alımları için her gün güncellenen, reklamsız Telegram kanalları ve iş ilanları.",
        f"{taban}/", govde, jsonld, f"{taban}/img/og/ana.png",
        "telegram iş ilanları, iş ilanı telegram kanalı, özel güvenlik iş ilanları, öğretmen iş ilanları, hemşire iş ilanları, kpss soru"), encoding="utf-8")

    # 404
    (KOK / "404.html").write_text(sayfa(
        "Sayfa bulunamadı", "Aradığınız sayfa bulunamadı; ilan süresi dolmuş olabilir.", f"{taban}/404.html",
        '<header class="ust"><h1>Sayfa bulunamadı</h1><p class="alt">Aradığınız ilanın süresi dolmuş olabilir. '
        'Güncel ilanlar için <a href="/">ana sayfaya</a> dönün.</p></header>', [], f"{taban}/img/og/ana.png",
        robots="noindex"), encoding="utf-8")

    # site haritası ve robots
    urls = [(f"{taban}/", f"{bugun}", "daily", "1.0")]
    urls += [(f"{taban}/kanal/{k}/", f"{bugun}", "daily", "0.8") for k in KANAL]
    urls += [(f"{taban}/ilan/{i['kimlik']}/", i["yayin"], "weekly", "0.6") for i in acik]
    (KOK / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>"
                  for u, m, c, p in urls) + "</urlset>", encoding="utf-8")
    (KOK / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {taban}/sitemap.xml\n", encoding="utf-8")
    print(f"Site üretildi: {len(urls)} sayfa ({len(acik)} açık ilan)")


if __name__ == "__main__":
    main()
