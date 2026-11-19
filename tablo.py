"""
Taban puan / tercih / kadro tablosu görseli (1080x1350 PNG, Telegram ve Instagram için).

Kullanım:  python tablo.py tablo.json cikti_on_eki
  → cikti_on_eki_1.png, cikti_on_eki_2.png ... (14 satırdan uzun tablolar sayfalara bölünür)

tablo.json:
{
  "kanal": "kpsstercih_tr",
  "ust": "KPSS 2026/5 TERCİH",                (küçük etiket)
  "baslik": "Hemşire kadroları taban puanları",
  "alt_baslik": "Lisans · KPSSP3",            (isteğe bağlı)
  "sutunlar": ["Kurum", "İl", "Kontenjan", "Taban"],
  "hizala": ["sol", "sol", "sag", "sag"],     (isteğe bağlı)
  "satirlar": [["Sağlık Bakanlığı", "Ankara", "12", "78,45"], ...],
  "vurgu": [0],                               (isteğe bağlı: vurgulanacak satır sıraları)
  "kaynak": "ÖSYM, 2026-KPSS/5 Yerleştirme Sonuçları"   (ZORUNLU – resmi kaynak)
}
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pdf import RENK

W, H = 1080, 1350
SATIR_SAYFA = 14
F_KALIN = ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
F_ORTA = ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
F_NORMAL = ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(liste, n):
    return ImageFont.truetype(next(f for f in liste if Path(f).exists()), n)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def kisalt(d, s, f, w):
    s = str(s)
    if d.textlength(s, font=f) <= w:
        return s
    while s and d.textlength(s + "…", font=f) > w:
        s = s[:-1]
    return s + "…"


def uret(v, on_ek):
    k = v["kanal"].lstrip("@")
    c1, c2 = (rgb(x) for x in RENK.get(k, ("#13294B", "#2B5A8C")))
    sut, satir = v["sutunlar"], v["satirlar"]
    sayisal = lambda x: str(x).replace(",", "").replace(".", "").replace("-", "").strip().isdigit()
    hiza = v.get("hizala") or ["sag" if satir and all(sayisal(r[i]) for r in satir) else "sol" for i in range(len(sut))]
    vurgu = set(v.get("vurgu", []))
    sayfalar = [satir[i:i + SATIR_SAYFA] for i in range(0, len(satir), SATIR_SAYFA)] or [[]]
    olcum = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    fh, fb = font(F_NORMAL, 30), font(F_ORTA, 28)
    # sütun genişliği: içerik uzunluğuna göre
    ic = 1080 - 120
    agirlik = [max(olcum.textlength(str(x), font=fh) for x in [s] + [r[i] for r in satir]) + 30 for i, s in enumerate(sut)]
    gen = [ic * a / sum(agirlik) for a in agirlik]
    cikti = []
    for no, parca in enumerate(sayfalar, 1):
        im = Image.new("RGB", (W, H), (248, 248, 246))
        d = ImageDraw.Draw(im)
        for y in range(330):
            t = y / 330
            d.line([(0, y), (W, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
        fu = font(F_KALIN, 30)
        etiket = v.get("ust", "").upper()
        if etiket:
            d.rounded_rectangle([60, 50, 60 + d.textlength(etiket, font=fu) + 44, 104], radius=27, fill="white")
            d.text((82, 59), etiket, font=fu, fill=c1)
        fbas = font(F_KALIN, 54)
        y = 130
        kel, sat = v["baslik"].split(), ""
        for w in kel:
            dn = (sat + " " + w).strip()
            if d.textlength(dn, font=fbas) > 960 and sat:
                d.text((60, y), sat, font=fbas, fill="white"); y += 66; sat = w
            else:
                sat = dn
        d.text((60, y), sat, font=fbas, fill="white"); y += 70
        if v.get("alt_baslik"):
            d.text((60, y), v["alt_baslik"] + (f"  ·  {no}/{len(sayfalar)}" if len(sayfalar) > 1 else ""),
                   font=font(F_NORMAL, 32), fill=(230, 236, 250))
        # tablo
        y = 370
        d.rounded_rectangle([60, y, W - 60, y + 64], radius=14, fill=c1)
        x = 60
        for i, s in enumerate(sut):
            t = kisalt(d, s, fb, gen[i] - 24)
            tx = x + 14 if hiza[i] == "sol" else x + gen[i] - 14 - d.textlength(t, font=fb)
            d.text((tx, y + 16), t, font=fb, fill="white")
            x += gen[i]
        y += 72
        for j, r in enumerate(parca):
            gercek = (no - 1) * SATIR_SAYFA + j
            zemin = (255, 244, 214) if gercek in vurgu else ((255, 255, 255) if j % 2 == 0 else (240, 241, 238))
            d.rounded_rectangle([60, y, W - 60, y + 58], radius=10, fill=zemin)
            x = 60
            for i, hucre in enumerate(r):
                f = font(F_ORTA, 30) if gercek in vurgu else fh
                t = kisalt(d, hucre, f, gen[i] - 24)
                tx = x + 14 if hiza[i] == "sol" else x + gen[i] - 14 - d.textlength(t, font=f)
                d.text((tx, y + 13), t, font=f, fill=(30, 30, 35))
                x += gen[i]
            y += 64
        d.text((60, H - 200), "Kaynak: " + v["kaynak"], font=font(F_NORMAL, 26), fill=(90, 90, 95))
        d.rectangle([0, H - 140, W, H], fill=c1)
        d.text((60, H - 118), f"@{k}", font=font(F_KALIN, 52), fill="white")
        d.text((60, H - 52), f"t.me/{k}", font=font(F_NORMAL, 30), fill=(225, 230, 245))
        yol = f"{on_ek}_{no}.png"
        im.save(yol, optimize=True)
        cikti.append(yol)
    return cikti


if __name__ == "__main__":
    v = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not v.get("kaynak"):
        sys.exit("HATA: resmi kaynak zorunlu")
    print("Üretildi:", ", ".join(uret(v, sys.argv[2])))
