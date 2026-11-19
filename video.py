"""
Günlük kısa dikey video üreticisi (Instagram Reels / TikTok / YouTube Shorts, 1080x1920, ~15 sn).

Kullanım:
  python video.py --csv gunluk.csv --cikti KLASOR [--soru ogg_sinav kpss_gunluksoru ...] [--ilan ozelguvenlikilan_tr ...]

--soru: verilen kanalların o günkü İLK quiz'inden "Günün sorusu" videosu
        (soru + şıklar → 5 sn geri sayım → doğru cevap + açıklama → kanala katıl).
--ilan: verilen kanalların o günkü ilan kartlarından "Bugünün ilanları" videosu (en fazla 5 ilan).
Çıktı: KLASOR/<kanal>_soru.mp4, KLASOR/<kanal>_ilanlar.mp4 ve her video için paylaşım açıklaması (.txt).
"""
import argparse
import csv
import hashlib
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from PIL import Image, ImageDraw, ImageFont

from olustur import KANAL, RENK, ilan_ayristir

W, H, FPS = 1080, 1920, 30
SR = 44100
# Sakin fon müziği için akor dizileri (yarım ton, A4=440 Hz'e göre MIDI numaraları); tamamen üretilmiş, telifsiz
DIZILER = [
    [[48, 55, 59, 64], [45, 52, 55, 60], [41, 48, 52, 57], [43, 50, 55, 59]],   # Cmaj7 · Am7 · Fmaj7 · G
    [[50, 57, 60, 65], [46, 53, 57, 62], [41, 48, 53, 57], [48, 55, 60, 64]],   # Dm7 · Bbmaj7 · F · C
    [[45, 52, 57, 60], [41, 48, 53, 57], [48, 55, 60, 64], [43, 50, 55, 59]],   # Am · F · C · G
]
FONT_YOLLARI = {
    "kalin": ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "orta": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "normal": ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
_fcache = {}


def font(tur, n):
    if (tur, n) not in _fcache:
        yol = next((f for f in FONT_YOLLARI[tur] if Path(f).exists()), None)
        _fcache[(tur, n)] = ImageFont.truetype(yol, n) if yol else ImageFont.load_default()
    return _fcache[(tur, n)]


def kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def etiketler(k, n):
    return " ".join("#" + kucuk(x).replace(" ", "").replace("'", "") for x in KANAL[k][2].split(",")[:n])


def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def arkaplan(k):
    c1, c2, _ = RENK[k]
    a, b = hex2rgb(c1), hex2rgb(c2)
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    return im


def sar(d, metin, f, genislik):
    satirlar = []
    for paragraf in metin.split("\n"):
        satir = ""
        for k in paragraf.split():
            dene = (satir + " " + k).strip()
            if d.textlength(dene, font=f) > genislik and satir:
                satirlar.append(satir)
                satir = k
            else:
                satir = dene
        satirlar.append(satir)
    return satirlar


def yaz(d, metin, f, x, y, genislik, renk="white", aralik=1.25, sinir=None):
    satirlar = sar(d, metin, f, genislik)
    if sinir and len(satirlar) > sinir:
        satirlar = satirlar[:sinir]
        satirlar[-1] = satirlar[-1].rstrip(".,;:") + "…"
    for s in satirlar:
        d.text((x, y), s, font=f, fill=renk)
        y += int(f.size * aralik)
    return y


def uygun_font(d, metin, tur, buyuk, kucuk, genislik, max_satir):
    for n in range(buyuk, kucuk - 1, -4):
        if len(sar(d, metin, font(tur, n), genislik)) <= max_satir:
            return font(tur, n)
    return font(tur, kucuk)


def ust_bant(im, k, etiket):
    d = ImageDraw.Draw(im)
    prof = Path(__file__).resolve().parent / "img" / f"{k}.jpg"
    if prof.exists():
        p = Image.open(prof).convert("RGB").resize((150, 150))
        m = Image.new("L", (150, 150), 0)
        ImageDraw.Draw(m).ellipse([0, 0, 150, 150], fill=255)
        im.paste(p, (80, 130), m)
    d.text((260, 150), KANAL[k][0][:34], font=font("orta", 40), fill="white")
    d.text((260, 205), f"@{k}", font=font("normal", 36), fill=(225, 230, 245))
    f = font("kalin", 44)
    w = d.textlength(etiket, font=f)
    d.rounded_rectangle([80, 330, 80 + w + 60, 410], radius=40, fill="white")
    d.text((110, 342), etiket, font=f, fill=hex2rgb(RENK[k][0]))


def kapanis(k, ust, alt):
    im = arkaplan(k)
    d = ImageDraw.Draw(im)
    prof = Path(__file__).resolve().parent / "img" / f"{k}.jpg"
    if prof.exists():
        p = Image.open(prof).convert("RGB").resize((360, 360))
        m = Image.new("L", (360, 360), 0)
        ImageDraw.Draw(m).ellipse([0, 0, 360, 360], fill=255)
        im.paste(p, ((W - 360) // 2, 480), m)
    y = 920
    for s in sar(d, ust, font("kalin", 72), W - 160):
        w = d.textlength(s, font=font("kalin", 72))
        d.text(((W - w) / 2, y), s, font=font("kalin", 72), fill="white")
        y += 90
    y += 40
    f = font("kalin", 54)
    t = f"t.me/{k}"
    w = d.textlength(t, font=f)
    d.rounded_rectangle([(W - w) / 2 - 40, y, (W + w) / 2 + 40, y + 100], radius=50, fill="white")
    d.text(((W - w) / 2, y + 20), t, font=f, fill=hex2rgb(RENK[k][0]))
    y += 160
    for s in sar(d, alt, font("normal", 40), W - 200):
        w = d.textlength(s, font=font("normal", 40))
        d.text(((W - w) / 2, y), s, font=font("normal", 40), fill=(230, 235, 250))
        y += 56
    return im


def muzik(sure, tohum, yol):
    """Sakin, telifsiz fon müziği üretir (yumuşak akor dokusu + hafif arpej), WAV olarak yazar."""
    rng = np.random.default_rng(int(hashlib.md5(tohum.encode()).hexdigest()[:8], 16))
    dizi = DIZILER[rng.integers(len(DIZILER))]
    n = int(sure * SR)
    t = np.arange(n) / SR
    sol, sag = np.zeros(n), np.zeros(n)
    akor_s = 4.0
    frek = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    for i in range(int(np.ceil(sure / akor_s)) + 1):
        bas = i * akor_s
        notalar = dizi[i % len(dizi)]
        a, b = int(max(0, bas - 0.6) * SR), min(n, int((bas + akor_s + 1.2) * SR))
        if a >= n:
            break
        tt = t[a:b] - (bas - 0.6)
        zarf = np.clip(tt / 1.4, 0, 1) * np.clip((akor_s + 1.8 - tt) / 1.4, 0, 1)
        for j, m in enumerate(notalar):
            f = frek(m)
            ses = (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt + 0.3)
                   + 0.5 * np.sin(2 * np.pi * f * 1.003 * tt)) * zarf * 0.12
            pan = 0.35 + 0.3 * (j / 3)
            sol[a:b] += ses * (1 - pan)
            sag[a:b] += ses * pan
        # hafif arpej (yüksek oktav, yavaş sönen notalar)
        for k2 in range(8):
            ba = bas + k2 * 0.5
            m = notalar[(k2 * 2 + i) % 4] + 24
            c, d = int(ba * SR), min(n, int((ba + 1.6) * SR))
            if c >= n:
                break
            tt2 = t[c:d] - ba
            nota = np.sin(2 * np.pi * frek(m) * tt2) * np.exp(-tt2 * 2.6) * np.clip(tt2 / 0.02, 0, 1) * 0.05
            pan = 0.2 + 0.6 * ((k2 % 4) / 3)
            sol[c:d] += nota * (1 - pan)
            sag[c:d] += nota * pan
    for gec, kat in ((0.21, 0.28), (0.37, 0.18), (0.61, 0.1)):   # yumuşak yankı
        g = int(gec * SR)
        sol[g:] += sol[:-g] * kat
        sag[g:] += sag[:-g] * kat
    karisim = np.stack([sol, sag], axis=1)
    karisim *= np.clip(t / 1.0, 0, 1)[:, None] * np.clip((sure - t) / 1.8, 0, 1)[:, None]
    karisim *= 0.32 / (np.abs(karisim).max() or 1)
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((karisim * 32767).astype("<i2").tobytes())


def kaydet(sahneler, hedef):
    """sahneler: [(PIL.Image | callable(t)->Image, saniye)] → yüksek kaliteli mp4 (H.264 + sakin fon müziği)."""
    sure = sum(s for _, s in sahneler)
    wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    muzik(sure, Path(hedef).stem, wav)
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(wav), "-shortest",
         "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-tune", "stillimage",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), str(hedef)], stdin=subprocess.PIPE)
    for sahne, sure in sahneler:
        n = int(sure * FPS)
        sabit = None if callable(sahne) else sahne.tobytes()
        for i in range(n):
            p.stdin.write(sabit if sabit else sahne(i / n).tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink(missing_ok=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg hatası: {hedef}")


# ---------- Günün sorusu ----------
def soru_videosu(k, r, hedef):
    soru = r["metin"].strip()
    sec = [s.strip() for s in r["secenekler"].split("|") if s.strip()][:5]
    dogru = int(r["dogru"]) - 1
    aciklama = (r.get("aciklama") or "").strip()
    harf = "ABCDE"

    def soru_karesi(cevap=False, kalan=None):
        im = arkaplan(k)
        ust_bant(im, k, "GÜNÜN SORUSU")
        d = ImageDraw.Draw(im)
        fs = uygun_font(d, soru, "kalin", 64, 44, W - 160, 7)
        y = yaz(d, soru, fs, 80, 480, W - 160, sinir=7) + 40
        fo = uygun_font(d, max(sec, key=len), "orta", 46, 34, W - 300, 2)
        for i, s in enumerate(sec):
            satir = sar(d, s, fo, W - 300)[:2]
            yuk = 50 + len(satir) * int(fo.size * 1.25)
            if cevap and i == dogru:
                kutu, yazi = (46, 160, 90), "white"
            elif cevap:
                kutu, yazi = (255, 255, 255, 0), (210, 215, 230)
            else:
                kutu, yazi = "white", (25, 25, 35)
            if cevap and i != dogru:
                d.rounded_rectangle([80, y, W - 80, y + yuk], radius=28, outline=(210, 215, 230), width=3)
            else:
                d.rounded_rectangle([80, y, W - 80, y + yuk], radius=28, fill=kutu)
            d.text((115, y + 25), harf[i], font=font("kalin", fo.size), fill=yazi)
            yaz(d, "\n".join(satir), fo, 190, y + 25, W - 300, renk=yazi)
            if cevap and i == dogru:
                d.text((W - 160, y + 20), "✓", font=font("kalin", 60), fill="white")
            y += yuk + 22
        if kalan is not None:
            d.rounded_rectangle([80, H - 260, W - 80, H - 230], radius=15, fill=(255, 255, 255), outline="white", width=2)
            d.rounded_rectangle([82, H - 258, W - 82, H - 232], radius=13, fill=hex2rgb(RENK[k][0]))
            d.rounded_rectangle([80, H - 260, 80 + max(30, int((W - 160) * kalan)), H - 230], radius=15, fill="white")
            t = f"Cevabını düşün… {max(1, int(kalan * 5 + 0.999))}"
            d.text((80, H - 340), t, font=font("orta", 44), fill="white")
        elif cevap and aciklama:
            yaz(d, aciklama, font("normal", 38), 80, max(y + 20, H - 470), W - 160,
                renk=(235, 240, 250), sinir=5)
        return im

    kaydet([
        (soru_karesi(), 1.5),
        (lambda t: soru_karesi(kalan=1 - t), 5),
        (soru_karesi(cevap=True), 5),
        (kapanis(k, "Her gün yeni soru", "Telegram'da ücretsiz · çözümlü sorular, konu özetleri ve sınav takvimi"), 3.5),
    ], hedef)
    return (f"🧠 Günün sorusu – cevabını yorumlara yaz!\n\n"
            f"✅ Doğru cevap ve açıklaması, her gün yeni sorular, konu özetleri ve ücretsiz PDF'ler "
            f"Telegram'daki \"{KANAL[k][0]}\" kanalımızda:\n👉 t.me/{k}\n\n"
            + etiketler(k, 4) + " #sınavhazırlık #gününsorusu")


# ---------- Bugünün ilanları ----------
def ilan_videosu(k, ilanlar, hedef, tarih):
    ilanlar = ilanlar[:5]

    def kare(n):
        im = arkaplan(k)
        ust_bant(im, k, f"BUGÜNÜN İLANLARI · {tarih[8:10]}.{tarih[5:7]}")
        d = ImageDraw.Draw(im)
        y = 480
        for i in ilanlar[:n]:
            yer = i["il"] + (f" / {i['ilce']}" if i["ilce"] else "")
            bas = f"{i['pozisyon']}"
            alt = i["firma"] + (f" · {i['maas']}" if i["maas"] else "")
            d.rounded_rectangle([80, y, W - 80, y + 230], radius=30, fill="white")
            d.text((120, y + 25), yer.upper(), font=font("orta", 34), fill=hex2rgb(RENK[k][0]))
            yaz(d, bas, font("kalin", 46), 120, y + 72, W - 240, renk=(25, 25, 35), sinir=1)
            yaz(d, alt, font("normal", 36), 120, y + 140, W - 240, renk=(90, 90, 100), sinir=1)
            y += 255
        return im

    sahneler = [(kare(0), 1.0)] + [(kare(n), 2.2) for n in range(1, len(ilanlar) + 1)]
    sahneler.append((kapanis(k, "Başvuru linkleri Telegram'da", "Her gün yeni ilan · il etiketiyle · reklamsız"), 3.5))
    kaydet(sahneler, hedef)
    iller = " ".join(dict.fromkeys("#" + i["il"] for i in ilanlar))
    return (f"📍 Bugünün {kucuk(KANAL[k][0].split('–')[0].strip())}\n\n"
            f"🔗 Başvuru linkleri, şartlar ve her gün yeni ilanlar Telegram'daki \"{KANAL[k][0]}\" kanalımızda:\n"
            f"👉 t.me/{k}\n\n{iller} " + etiketler(k, 3) + " #işilanı #iş")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", nargs="+", required=True)
    p.add_argument("--cikti", required=True)
    p.add_argument("--soru", nargs="*", default=[])
    p.add_argument("--ilan", nargs="*", default=[])
    a = p.parse_args()
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    satirlar = []
    for yol in a.csv:
        with open(yol, encoding="utf-8-sig") as f:
            satirlar += list(csv.DictReader(f))
    for r in satirlar:
        r["kanal"] = r.get("kanal", "").lstrip("@").lower()
    tarih = min((r["tarih"] for r in satirlar), default="")
    uretilen = []
    for k in a.soru:
        r = next((r for r in satirlar if r["kanal"] == k and r.get("tur") == "quiz" and r.get("dogru")), None)
        if not r or k not in RENK:
            print(f"ATLANDI {k}: quiz yok")
            continue
        hedef = cikti / f"{k}_soru.mp4"
        hedef.with_suffix(".txt").write_text(soru_videosu(k, r, hedef), encoding="utf-8")
        uretilen.append(hedef.name)
    for k in a.ilan:
        ilanlar = [i for i in (ilan_ayristir(r) for r in satirlar if r["kanal"] == k) if i]
        if len(ilanlar) < 2 or k not in RENK:
            print(f"ATLANDI {k}: yeterli ilan yok ({len(ilanlar)})")
            continue
        hedef = cikti / f"{k}_ilanlar.mp4"
        hedef.with_suffix(".txt").write_text(ilan_videosu(k, ilanlar, hedef, tarih), encoding="utf-8")
        uretilen.append(hedef.name)
    print("Üretilen videolar:", ", ".join(uretilen) or "yok")


if __name__ == "__main__":
    main()
