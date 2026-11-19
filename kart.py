"""
Instagram "kaydedilecek bilgi kartı" (carousel) üreticisi – 1080x1350 PNG sayfalar.

Kullanım:
  python kart.py kart.json cikti_on_eki
  → cikti_on_eki_1.jpg (kapak), _2.jpg … (içerik), son sayfa (kanala davet) – JPEG, 4:5 (Instagram carousel şartı)

kart.json:
{
  "kanal": "kpsstercih_tr",
  "baslik": "Ortaöğretim KPSS puanınla başvurabileceğin kadrolar",
  "alt_baslik": "KPSS-2026/x yerleştirme sonuçlarına göre",        (isteğe bağlı)
  "sayfalar": [
     {"baslik": "90 – 100 puan", "maddeler": ["Adalet Bakanlığı – zabıt kâtibi", "…"]},
     {"baslik": "Taban puanlar", "tablo": [["Kadro", "Taban"], ["Zabıt kâtibi", "84,12"]]}
  ],
  "kaynak": "ÖSYM, KPSS-2026/x yerleştirme sonuçları",            (zorunlu)
  "kapanis": "Her gün güncel alımlar ve taban puanlar"            (isteğe bağlı)
}
Bir sayfada en fazla 8 madde veya 12 tablo satırı; fazlası otomatik yeni sayfaya geçer. En fazla 10 sayfa (Instagram sınırı).
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from olustur import KANAL, RENK
from video import font, hex2rgb, sar

W, H = 1080, 1350
KOK = Path(__file__).resolve().parent


def zemin(k, acik=False):
    a, b = hex2rgb(RENK[k][0]), hex2rgb(RENK[k][1])
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    if acik:
        d.rounded_rectangle([40, 170, W - 40, H - 130], radius=36, fill=(250, 250, 252))
    return im, d


def alt_serit(im, d, k, n, toplam):
    prof = KOK / "img" / f"{k}.jpg"
    if prof.exists():
        p = Image.open(prof).convert("RGB").resize((70, 70))
        m = Image.new("L", (70, 70), 0)
        ImageDraw.Draw(m).ellipse([0, 0, 70, 70], fill=255)
        im.paste(p, (50, H - 105), m)
    d.text((140, H - 95), f"@{k}", font=font("kalin", 38), fill="white")
    t = f"{n}/{toplam}"
    d.text((W - 50 - d.textlength(t, font=font("orta", 34)), H - 90), t, font=font("orta", 34), fill=(230, 235, 245))


def ust_baslik(d, k, metin):
    f = font("kalin", 46)
    satir = sar(d, metin, f, W - 120)[:2]
    y = 60 if len(satir) == 1 else 40
    for s in satir:
        d.text((60, y), s, font=f, fill="white")
        y += 56


def kapak(v):
    k = v["kanal"]
    im, d = zemin(k)
    d.rounded_rectangle([60, 90, 60 + d.textlength("KAYDET, LAZIM OLACAK", font=font("kalin", 38)) + 60, 160],
                        radius=35, fill=(255, 214, 64))
    d.text((90, 103), "KAYDET, LAZIM OLACAK", font=font("kalin", 38), fill=(40, 30, 10))
    for n in range(104, 55, -4):
        satir = sar(d, v["baslik"], font("kalin", n), W - 140)
        if len(satir) * n * 1.15 <= 620:
            break
    y = 300
    for s in satir:
        d.text((70, y), s, font=font("kalin", n), fill="white")
        y += int(n * 1.15)
    if v.get("alt_baslik"):
        y += 30
        for s in sar(d, v["alt_baslik"], font("normal", 44), W - 140)[:3]:
            d.text((70, y), s, font=font("normal", 44), fill=(235, 240, 250))
            y += 58
    d.text((70, H - 230), "Kaydır  →", font=font("kalin", 54), fill="white")
    return im


def icerik_sayfalari(v):
    k = v["kanal"]
    renk = hex2rgb(RENK[k][0])
    parcalar = []
    for s in v["sayfalar"]:
        if s.get("maddeler"):
            m = s["maddeler"]
            for i in range(0, len(m), 8):
                parcalar.append(("madde", s["baslik"], m[i:i + 8]))
        elif s.get("tablo"):
            bas, govde = s["tablo"][0], s["tablo"][1:]
            for i in range(0, len(govde), 12):
                parcalar.append(("tablo", s["baslik"], [bas] + govde[i:i + 12]))
    out = []
    for tur, baslik, veri in parcalar:
        im, d = zemin(k, acik=True)
        ust_baslik(d, k, baslik)
        y = 215
        if tur == "madde":
            f = font("orta", 40)
            for m in veri:
                tum = sar(d, m, f, W - 230)
                satir = tum[:3]
                if len(tum) > 3:
                    satir[-1] = satir[-1].rstrip(" ,;") + "…"
                yuk = len(satir) * 50 + 30
                d.ellipse([80, y + 14, 104, y + 38], fill=renk)
                yy = y
                for s in satir:
                    d.text((130, yy), s, font=f, fill=(30, 32, 40))
                    yy += 50
                y += yuk
                d.line([(80, y - 12), (W - 80, y - 12)], fill=(225, 228, 235), width=2)
        else:
            sut = len(veri[0])
            gen = [(W - 160) * (0.55 if sut > 1 and j == 0 else (0.45 / (sut - 1) if sut > 1 else 1)) for j in range(sut)]
            for r, satir in enumerate(veri):
                x = 80
                f = font("kalin" if r == 0 else "normal", 34)
                if r == 0:
                    d.rectangle([60, y - 8, W - 60, y + 52], fill=renk)
                elif r % 2 == 0:
                    d.rectangle([60, y - 8, W - 60, y + 52], fill=(240, 242, 247))
                for j, hucre in enumerate(satir):
                    t = str(hucre)
                    while d.textlength(t, font=f) > gen[j] - 16 and len(t) > 3:
                        t = t[:-2] + "…"
                    sag = j > 0 and t.replace(",", "").replace(".", "").strip().isdigit()
                    tx = x + gen[j] - 16 - d.textlength(t, font=f) if sag else x
                    d.text((tx, y), t, font=f, fill="white" if r == 0 else (30, 32, 40))
                    x += gen[j]
                y += 64
        d.text((80, H - 175), "Kaynak: " + v["kaynak"][:70], font=font("normal", 28), fill=(110, 115, 130))
        out.append(im)
    return out


def son_sayfa(v):
    k = v["kanal"]
    im, d = zemin(k)
    prof = KOK / "img" / f"{k}.jpg"
    if prof.exists():
        p = Image.open(prof).convert("RGB").resize((280, 280))
        m = Image.new("L", (280, 280), 0)
        ImageDraw.Draw(m).ellipse([0, 0, 280, 280], fill=255)
        im.paste(p, ((W - 280) // 2, 180), m)
    y = 520
    for s in sar(d, v.get("kapanis") or "Her gün güncel bilgi ve ilanlar", font("kalin", 64), W - 160):
        d.text(((W - d.textlength(s, font=font("kalin", 64))) / 2, y), s, font=font("kalin", 64), fill="white")
        y += 80
    y += 30
    t = f"t.me/{k}"
    f = font("kalin", 56)
    w = d.textlength(t, font=f)
    d.rounded_rectangle([(W - w) / 2 - 40, y, (W + w) / 2 + 40, y + 104], radius=52, fill="white")
    d.text(((W - w) / 2, y + 20), t, font=f, fill=hex2rgb(RENK[k][0]))
    y += 170
    for s in ["Ücretsiz Telegram kanalımız", "Linki profilimizde"]:
        d.text(((W - d.textlength(s, font=font("normal", 42))) / 2, y), s, font=font("normal", 42), fill=(235, 240, 250))
        y += 60
    return im


def main():
    v = json.load(open(sys.argv[1], encoding="utf-8"))
    if not v.get("kaynak"):
        sys.exit("kaynak zorunlu")
    if v["kanal"] not in RENK:
        sys.exit(f"bilinmeyen kanal: {v['kanal']}")
    sayfalar = [kapak(v)] + icerik_sayfalari(v) + [son_sayfa(v)]
    sayfalar = sayfalar[:9] + [sayfalar[-1]] if len(sayfalar) > 10 else sayfalar
    for i, im in enumerate(sayfalar, 1):
        if i > 1:
            alt_serit(im, ImageDraw.Draw(im), v["kanal"], i, len(sayfalar))
        im.convert("RGB").save(f"{sys.argv[2]}_{i}.jpg", quality=92, optimize=True)
    print(f"{len(sayfalar)} sayfa yazıldı: {sys.argv[2]}_1..{len(sayfalar)}.jpg")


if __name__ == "__main__":
    main()
