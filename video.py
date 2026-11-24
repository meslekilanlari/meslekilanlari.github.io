"""
Günlük kısa dikey video üreticisi (Instagram Reels / TikTok / YouTube Shorts, 1080x1920, ~15 sn).

Kullanım:
  python video.py --csv gunluk.csv --cikti KLASOR [--soru ogg_sinav kpss_gunluksoru ...] [--ilan ozelguvenlikilan_tr ...]

--soru: verilen kanalların o günkü İLK quiz'inden "Günün sorusu" videosu
        (soru + şıklar → 5 sn geri sayım → doğru cevap + açıklama → kanala katıl).
--ilan: verilen kanalların o günkü ilan kartlarından "Bugünün ilanları" videosu (en fazla 5 ilan).
Görünüm: defter kâğıdı + el yazısı; metni "📌 ÇIKMIŞ SORU (121. Dönem ÖGG): …" ile başlayan quiz varsa o seçilir ve "SINAVDA ÇIKTI!" etiketi eklenir.
Çıktı: KLASOR/<kanal>_soru.mp4, KLASOR/<kanal>_ilanlar.mp4; her video için <ad>.json {baslik, aciklama, hashtagler}
(liste.json'a aynen kopyalanır) ve okunabilir <ad>.txt (başlık + açıklama + en altta hashtag'ler).
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
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


# ---------- Günün sorusu (defter kâğıdı + el yazısı + kırmızı kalem) ----------
FONT_DIR = Path(__file__).resolve().parent / "fonts"
MUREKKEP, KALEM, KAGIT = (28, 48, 118), (214, 40, 40), (252, 249, 240)
CIKMIS_ON = re.compile(r"^\s*📌\s*ÇIKMIŞ SORU\s*(?:\(([^)]*)\))?\s*:?\s*", re.I)


def el(n, kalin=False):
    anahtar = ("el_k" if kalin else "el", n)
    if anahtar not in _fcache:
        yol = FONT_DIR / ("Caveat-Bold.ttf" if kalin else "PatrickHand.ttf")
        _fcache[anahtar] = ImageFont.truetype(str(yol), n) if yol.exists() else font("orta", n)
    return _fcache[anahtar]


def cikmis_bilgisi(metin):
    """'📌 ÇIKMIŞ SORU (121. Dönem ÖGG): …' → ('121. Dönem ÖGG', soru) ; değilse (None, metin)."""
    m = CIKMIS_ON.match(metin)
    return ((m.group(1) or "").strip() or "Çıkmış soru", metin[m.end():].strip()) if m else (None, metin)


def soru_kagidi(k, r, etiket=None, sticker=None, sayac_sn=5):
    """Defter kâğıdı karesi üreticisi: kare(asama, p) → Image. asama: giris | sayac | cevap."""
    cikmis, soru = cikmis_bilgisi(r["metin"].strip())
    sec = [s.strip() for s in r["secenekler"].split("|") if s.strip()][:5]
    dogru = int(r["dogru"]) - 1
    aciklama = (r.get("aciklama") or "").strip()
    harf = "ABCDE"
    X0, X1, Y0, Y1 = 50, W - 50, 450, H - 130
    tx, tw = 185, X1 - 185 - 60
    olcu = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for n in range(92, 39, -2):                     # soru + şıklar kâğıda sığacak en büyük el yazısı
        fs, fo = el(n), el(n - 6)
        adim_s, adim_o = int(n * 1.22), int((n - 6) * 1.22)
        ss = sar(olcu, soru, fs, tw)
        so = [sar(olcu, f"{harf[i]}) {s}", fo, tw)[:2] for i, s in enumerate(sec)]
        toplam = len(ss) * adim_s + 30 + sum(len(x) * adim_o + 18 for x in so)
        if toplam <= (Y1 - Y0) - 560:
            break
    sticker = sticker or ("SINAVDA ÇIKTI!" if cikmis else "10 saniyede çöz!")
    etiket = etiket or (f"ÇIKMIŞ SORU · {cikmis}"[:30] if cikmis else "GÜNÜN SORUSU")

    def kare(asama, p=0.0, acik=None):
        im = arkaplan(k)
        ust_bant(im, k, etiket)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([X0 + 10, Y0 + 14, X1 + 10, Y1 + 14], radius=26, fill=(0, 0, 0))  # gölge
        d.rounded_rectangle([X0, Y0, X1, Y1], radius=26, fill=KAGIT)
        # yerleşim: önce satır konumları, sonra çizgiler, en son mürekkep
        yazilar, cizgiler, kutular = [], [], []
        y = Y0 + 50
        for s in ss:
            yazilar.append((y, s, fs, -1)); cizgiler.append(y + int(fs.size * 1.08)); y += adim_s
        y += 30
        for oi, satir in enumerate(so):
            ust = y
            for s in satir:
                yazilar.append((y, s, fo, oi)); cizgiler.append(y + int(fo.size * 1.08)); y += adim_o
            kutular.append((ust, y))
            y += 18
        son = cizgiler[-1]
        while son + adim_o < Y1 - 30:
            son += adim_o
            cizgiler.append(son)
        for cy in cizgiler:
            d.line([(X0 + 20, cy), (X1 - 20, cy)], fill=(208, 222, 242), width=2)
        d.line([(150, Y0 + 20), (150, Y1 - 20)], fill=(238, 168, 168), width=3)
        for yy, s, f, oi in yazilar:
            if acik is None or oi < acik:               # kademeli açılış: önce soru, sonra şıklar tek tek
                d.text((tx, yy), s, font=f, fill=MUREKKEP)
        if asama in ("giris", "sayac"):
            fst = el(64, True)
            w = d.textlength(sticker, font=fst)
            st = Image.new("RGBA", (int(w) + 70, 120), (0, 0, 0, 0))
            ImageDraw.Draw(st).rounded_rectangle([0, 0, w + 70, 120], radius=24, fill=(255, 214, 64))
            ImageDraw.Draw(st).text((35, 14), sticker, font=fst, fill=(40, 30, 10))
            st = st.rotate(6, expand=True, resample=Image.BICUBIC)
            im.paste(st, (W - st.width - 40, Y0 - st.height // 2 - 10), st)
        if asama == "sayac":
            kalan = max(1, int((1 - p) * sayac_sn + 0.999))
            d.text((tx, Y1 - 200), f"Cevabını düşün… {kalan}", font=el(76, True), fill=KALEM)
            uz = int((X1 - 60 - tx) * (1 - p))
            d.line([(tx, Y1 - 90), (tx + uz, Y1 - 90)], fill=(70, 70, 80), width=8)
        if asama == "cevap":
            ust, alt = kutular[dogru]
            kutu = [tx - 30, ust - 14, X1 - 40, alt + 4]
            aci = 360 * min(1.0, p / 0.25)
            if aci > 0:
                for kalinlik, kay in ((7, 0), (5, 4)):
                    d.arc([kutu[0] - kay, kutu[1] - kay, kutu[2] + kay, kutu[3] + kay], -100, -100 + aci,
                          fill=KALEM, width=kalinlik)
            if p > 0.28:                              # ✓ işareti (kalemle)
                cx, cy = X1 - 120, (ust + alt) // 2
                d.line([(cx - 30, cy), (cx - 8, cy + 26), (cx + 36, cy - 34)], fill=(30, 150, 70), width=12, joint="curve")
            if p > 0.35 and aciklama:
                yaz(d, aciklama, el(62, True), tx, y + 40, tw, renk=KALEM, aralik=1.1, sinir=6)
        return im

    return kare, cikmis, soru


KANCALAR = [("BUNU BİLİYOR MUSUN?", "10 saniyen var!"), ("ÇOĞU KİŞİ BURADA TAKILIYOR", "Sen çözebilir misin?"),
            ("KAÇ KİŞİ DOĞRU BİLİR?", "Cevabını yoruma yaz"), ("SADECE 10 SANİYE!", "Hazır mısın?")]


def kanca(k, ust, alt, sinav=""):
    """Videonun ilk ~1.6 sn'si: iri başlık, 'pop' büyüme. İzleyici ilk saniyede kaydırmasın diye."""
    tek = {}

    def kare(t):
        im = arkaplan(k)
        d = ImageDraw.Draw(im)
        if sinav:
            f = font("kalin", 46)
            w = d.textlength(sinav, font=f)
            d.rounded_rectangle([(W - w) / 2 - 36, 330, (W + w) / 2 + 36, 420], radius=45, fill=(255, 214, 64))
            d.text(((W - w) / 2, 342), sinav, font=f, fill=(40, 30, 10))
        ol = min(1.0, t / 0.18)                         # ilk 0.3 sn'de büyüyerek gelir
        boy = int(156 * (0.72 + 0.28 * (1 - (1 - ol) ** 3)))
        satirlar = None
        for n in range(boy, 60, -4):
            f = font("kalin", n)
            satirlar = sar(d, ust, f, W - 140)
            if len(satirlar) <= 3:
                break
        y = 760 - len(satirlar) * int(f.size * 1.2) // 2
        for s_ in satirlar:
            w = d.textlength(s_, font=f)
            d.text(((W - w) / 2 + 4, y + 5), s_, font=f, fill=(0, 0, 0))
            d.text(((W - w) / 2, y), s_, font=f, fill="white")
            y += int(f.size * 1.2)
        if t > 0.35:
            f2 = font("orta", 62)
            w = d.textlength(alt, font=f2)
            d.rounded_rectangle([(W - w) / 2 - 40, y + 50, (W + w) / 2 + 40, y + 160], radius=50, fill="white")
            d.text(((W - w) / 2, y + 68), alt, font=f2, fill=hex2rgb(RENK[k][0]))
        return im
    return kare


def hikaye_kaydet(kare, hedef):
    """Instagram hikâyesi için 2 JPEG (1080x1920): soru ve cevap."""
    kare("giris").save(str(hedef).replace(".mp4", "_hikaye_soru.jpg"), quality=92)
    kare("cevap", 1.0).save(str(hedef).replace(".mp4", "_hikaye_cevap.jpg"), quality=92)


def soru_videosu(k, r, hedef):
    kare, cikmis, soru = soru_kagidi(k, r)
    hikaye_kaydet(kare, hedef)
    h = int(hashlib.md5((k + soru).encode()).hexdigest(), 16)
    ust, alt = ("BU SORU SINAVDA ÇIKTI!", "Sen doğru bilir miydin?") if cikmis else KANCALAR[h % len(KANCALAR)]
    n_sec = len([x for x in r["secenekler"].split("|") if x.strip()][:5])
    kaydet([
        (kanca(k, ust, alt, SINAV_ADI.get(k, KANAL[k][0].split("–")[0].strip())[:30]), 1.7),
        (lambda t: kare("giris", acik=int(t * (n_sec + 1))), 2.2),
        (lambda t: kare("sayac", t), 5),
        (lambda t: kare("cevap", t), 5.5),
        (kapanis(k, "Her gün yeni soru", "Telegram'da ücretsiz · çözümlü sorular, konu özetleri ve PDF'ler"), 3.5),
    ], hedef)
    return paylasim_metni(k, "soru", konu=r.get("_konu", ""), soru=soru, cikmis=cikmis)


# ---------- Hızlı test: 5 soru · 30 saniye ----------
def hizli_video(k, quizler, hedef, konu=""):
    quizler = quizler[:5]
    sahneler = [(kanca(k, f"{len(quizler)} SORU · {len(quizler) * 5} SANİYE", "Kaç doğru yaparsın?", SINAV_ADI.get(k, KANAL[k][0].split("–")[0].strip())[:30]), 1.7)]
    for i, r in enumerate(quizler, 1):
        kare, _, _ = soru_kagidi(k, r, etiket=f"HIZLI TEST · {i}/{len(quizler)}", sticker=f"{len(quizler)} soru · {len(quizler) * 5} sn", sayac_sn=3)
        if i == 1:
            sahneler.append((kare("giris"), 1.0))
        sahneler += [(lambda t, kr=kare: kr("sayac", t), 3), (lambda t, kr=kare: kr("cevap", 0.3 + t * 0.7), 2.2)]
    sahneler.append((kapanis(k, "Kaç tanesini bildin?", "Yorumlara yaz · her gün yeni sorular Telegram'da"), 3.5))
    kaydet(sahneler, hedef)
    m = paylasim_metni(k, "soru", konu=konu, soru=quizler[0]["metin"])
    sinav = SINAV_ADI.get(k, KANAL[k][0].split("–")[0].strip())
    m["baslik"] = kisalt(f"{sinav} Hızlı Test: {len(quizler)} Soru {len(quizler) * 5} Saniye" + (f" – {konu}" if konu else ""), 80) + " #shorts"
    m["aciklama"] = m["aciklama"].replace(m["aciklama"].split("\n")[0], f"⚡ {sinav} – {len(quizler)} soru, {len(quizler) * 5} saniye! Kaç tanesini bildin? Yorumlara yaz 👇", 1)
    m["aciklama"] = "\n".join(x for x in m["aciklama"].split("\n") if not x.startswith("❓"))
    return m


# ---------- Büyük alım duyurusu (tek kurum + büyük rakam) ----------
def tarih_tr(t):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else (t or "")


def alim_videosu(k, i, hedef):
    i = dict(i, son=tarih_tr(i.get("son")))
    sayi = max((int(x) for x in re.findall(r"\((\d+)\)", i["pozisyon"])), default=0)
    toplam = sum(int(x) for x in re.findall(r"\((\d+)\)", i["pozisyon"])) or sayi

    def kare(p):
        im = arkaplan(k)
        ust_bant(im, k, "YENİ ALIM")
        d = ImageDraw.Draw(im)
        y = 520
        for s in sar(d, i["firma"], font("kalin", 76), W - 160)[:3]:
            d.text((80, y), s, font=font("kalin", 76), fill="white"); y += 92
        y += 30
        n = str(int(toplam * min(1, p * 1.6))) if toplam else ""
        if n:
            d.text((80, y), n, font=font("kalin", 260), fill=(255, 214, 64)); y += 290
            d.text((80, y), "PERSONEL ALINACAK", font=font("kalin", 64), fill="white"); y += 110
        for s in sar(d, re.sub(r"\s*\(\d+\)", "", i["pozisyon"]), font("orta", 46), W - 160)[:4]:
            d.text((80, y), s, font=font("orta", 46), fill=(235, 240, 250)); y += 60
        y += 30
        alt = " · ".join(x for x in [i["il"], (f"Son başvuru {i['son']}" if i.get("son") else "")] if x)
        if alt:
            d.rounded_rectangle([80, y, 80 + d.textlength(alt, font=font("kalin", 44)) + 60, y + 84], radius=42, fill="white")
            d.text((110, y + 14), alt, font=font("kalin", 44), fill=hex2rgb(RENK[k][0]))
        return im

    kaydet([(lambda t: kare(t), 6), (kapanis(k, "Başvuru linki ve şartlar Telegram'da", "Her gün yeni kamu alımları · reklamsız"), 3.5)], hedef)
    ad = KANAL[k][0]
    baslik = kisalt(f"{i['firma']} {toplam} personel alacak" if toplam else f"{i['firma']} personel alımı", 80) + " #shorts"
    acik = (f"📢 {i['firma']} " + (f"{toplam} personel alacak!" if toplam else "personel alımı yapıyor!") + "\n"
            f"💼 {re.sub(r'[ ]*[(][0-9]+[)]', '', i['pozisyon'])}\n" + (f"📍 {i['il']}\n" if i["il"] else "") +
            (f"📅 Son başvuru: {i['son']}\n" if i.get("son") else "") +
            f"\nℹ️ Başvuru linki, şartlar ve her gün yeni alımlar \"{ad}\" Telegram kanalımızda:\n👉 https://t.me/{k}")
    seo = [hashtag(x) for x in KANAL[k][2].split(",")] + ["#" + i["il"], "#kamupersonelalımı", "#personelalımı", "#memuralımı", "#kpss", "#shorts"]
    return {"baslik": baslik[:90], "aciklama": acik, "hashtagler": [h.lstrip("#") for h in dict.fromkeys(h for h in seo if len(h) > 1)][:15]}


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
    return paylasim_metni(k, "ilan", ilanlar=ilanlar, tarih=tarih)


SINAV_ADI = {"kpss_gunluksoru": "KPSS", "ogg_sinav": "ÖGG", "ozelguvenliksinavi": "ÖGG", "ags_hazirlik": "AGS-ÖABT",
             "isguzmani_sinav": "İSG", "utt_sinav": "ÜTT", "saglik_atama": "KPSS P3", "sinav_gorevi": "KPSS"}


def kisalt(m, n):
    m = " ".join(m.split())
    return m if len(m) <= n else m[:n - 1].rsplit(" ", 1)[0] + "…"


def hashtag(x):
    x = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]", "", kucuk(x))
    return "#" + x if x else ""


def paylasim_metni(k, tur, konu="", soru="", ilanlar=None, tarih="", cikmis=None):
    """Instagram/YouTube için {baslik, aciklama, hashtagler}. aciklama: videoya özel bilgi + kanal bilgisi + link
    (hashtag'ler ayrı listede; paylaşım sırasında en alta eklenir)."""
    ad = KANAL[k][0]
    seo = [hashtag(x) for x in KANAL[k][2].split(",")]
    if tur == "soru":
        sinav = SINAV_ADI.get(k, ad.split("–")[0].strip())
        if cikmis:
            baslik = kisalt(f"{sinav} Çıkmış Soru ({cikmis})" + (f": {konu}" if konu else ""), 80) + " #shorts"
            ust = [f"📌 {sinav} – Sınavda çıkmış soru ({cikmis})! Cevabını yorumlara yaz 👇"]
        else:
            baslik = kisalt(f"{sinav} Günün Sorusu" + (f": {konu}" if konu else ""), 80) + " #shorts"
            ust = [f"🧠 {sinav} – Günün sorusu! Cevabını yorumlara yaz 👇"]
        if konu:
            ust.append(f"📚 Konu: {konu}")
        ust.append(f"❓ {kisalt(soru, 160)}")
        alt = (f"📄 Konu özeti + 10 soruluk PDF'i istiyorsan yoruma \"PDF\" yaz, linki gönderelim.\n\n"
               f"ℹ️ Doğru cevap ve açıklaması, konunun madde madde özeti ve 10 soruluk ücretsiz PDF "
               f"\"{ad}\" Telegram kanalımızda. Her gün yeni sorular ve konu anlatımlarıyla devam ediyoruz:\n"
               f"👉 https://t.me/{k}")
        seo += ["#" + kucuk(sinav).replace("-", "").replace(" ", ""), "#sınavhazırlık", "#gününsorusu", "#soruçözümü",
                "#sınavsoruları", "#shorts"] + (["#çıkmışsorular"] if cikmis else [])
        if konu:
            seo.append(hashtag(konu.split("(")[0])[:40])
    else:
        ilanlar = ilanlar or []
        baslik = kisalt(f"Bugünün {ad.split('–')[0].strip()} ({tarih[8:10]}.{tarih[5:7]})", 80) + " #shorts"
        ust = [f"📍 Bugünün {kucuk(ad.split('–')[0].strip())} – {len(ilanlar)} yeni ilan"]
        for i in ilanlar:
            yer = i["il"] + (f"/{i['ilce']}" if i.get("ilce") else "")
            ust.append(f"• {i['pozisyon']} – {i['firma']} ({yer})" + (f" · {i['maas']}" if i.get("maas") else ""))
        alt = (f"ℹ️ Başvuru linkleri, şartlar ve son başvuru tarihleri \"{ad}\" Telegram kanalımızda. "
               f"Her gün yeni ilanlarla devam ediyoruz:\n👉 https://t.me/{k}")
        seo += list(dict.fromkeys("#" + i["il"] for i in ilanlar)) + ["#işilanı", "#işilanları", "#iş", "#işarıyorum",
                                                                        "#elemanaranıyor", "#shorts"]
    hashtagler = [h.lstrip("#") for h in dict.fromkeys(h for h in seo if len(h) > 1)][:15]
    return {"baslik": baslik[:90], "aciklama": "\n".join(ust) + "\n\n" + alt, "hashtagler": hashtagler}


def yaz_paylasim(hedef, m):
    hedef.with_suffix(".json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    hedef.with_suffix(".txt").write_text(m["baslik"] + "\n\n" + m["aciklama"] + "\n\n" +
                                         " ".join("#" + h for h in m["hashtagler"]), encoding="utf-8")


def youtube_notu(m, saat, video_adi):
    """Kullanıcının YouTube'a yüklerken yapıştıracağı metin (yalnızca yazması gerekenler)."""
    bolum = "SABAH" if saat < "15:00" else "AKŞAM"
    return (f"YOUTUBE'A YÜKLEME – {bolum} {saat}\nVideo: {video_adi}\n\n"
            f"1) BAŞLIK (Title) kutusuna:\n{m['baslik']}\n\n"
            f"2) AÇIKLAMA (Description) kutusuna:\n{m['aciklama']}\n\n" + " ".join("#" + h for h in m["hashtagler"]) + "\n\n"
            f"3) ETİKETLER (Daha fazla göster → Tags) kutusuna:\n" + ", ".join(h for h in m["hashtagler"] if h != "shorts") + "\n\n"
            f"4) Kategori: Education (Eğitim)\n"
            f"5) Görünürlük → Planla (Schedule): bugün {saat}\n\n"
            f"Instagram'a {saat}'de otomatik paylaşılıyor; orada bir şey yapmanız gerekmiyor.\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", nargs="+", required="--youtube-notu" not in sys.argv)
    p.add_argument("--cikti", required="--youtube-notu" not in sys.argv)
    p.add_argument("--soru", nargs="*", default=[])
    p.add_argument("--ilan", nargs="*", default=[])
    p.add_argument("--hizli", nargs="*", default=[], help="kanalların günün quiz'lerinden 5 soru/30 sn hızlı test videosu")
    p.add_argument("--alim", nargs="*", default=[], help="kanalın en büyük kontenjanlı ilanından büyük alım duyuru videosu")
    p.add_argument("--youtube-notu", nargs=3, metavar=("JSON", "SAAT", "VIDEO_ADI"),
                   help="<ad>.json'dan kullanıcının YouTube'a yapıştıracağı metni yazdırır")
    a = p.parse_known_args()[0] if "--youtube-notu" in sys.argv else p.parse_args()
    if a.youtube_notu:
        j, saat, ad = a.youtube_notu
        print(youtube_notu(json.load(open(j, encoding="utf-8")), saat, ad), end="")
        return
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
        quizler = [r for r in satirlar if r["kanal"] == k and r.get("tur") == "quiz" and r.get("dogru")]
        r = next((q for q in quizler if cikmis_bilgisi(q["metin"])[0]), quizler[0] if quizler else None)
        if not r or k not in RENK:
            print(f"ATLANDI {k}: quiz yok")
            continue
        hedef = cikti / f"{k}_soru.mp4"
        konu = next((x["metin"].split("\n")[0].split(":", 1)[1].strip() for x in satirlar
                     if x["kanal"] == k and x.get("tur") == "metin" and x["metin"].lstrip().startswith("📚") and ":" in x["metin"].split("\n")[0]), "")
        r["_konu"] = konu
        yaz_paylasim(hedef, soru_videosu(k, r, hedef))
        uretilen.append(hedef.name)
    for k in a.ilan:
        ilanlar = [i for i in (ilan_ayristir(r) for r in satirlar if r["kanal"] == k) if i]
        if len(ilanlar) < 2 or k not in RENK:
            print(f"ATLANDI {k}: yeterli ilan yok ({len(ilanlar)})")
            continue
        hedef = cikti / f"{k}_ilanlar.mp4"
        yaz_paylasim(hedef, ilan_videosu(k, ilanlar, hedef, tarih))
        uretilen.append(hedef.name)
    for k in a.hizli:
        qs = [r for r in satirlar if r["kanal"] == k and r.get("tur") == "quiz" and r.get("dogru")]
        if len(qs) < 3 or k not in RENK:
            print(f"ATLANDI {k}: hızlı test için en az 3 quiz gerekli ({len(qs)})")
            continue
        konu = next((x["metin"].split("\n")[0].split(":", 1)[1].strip() for x in satirlar
                     if x["kanal"] == k and x.get("tur") == "metin" and x["metin"].lstrip().startswith("📚") and ":" in x["metin"].split("\n")[0]), "")
        hedef = cikti / f"{k}_hizli.mp4"
        yaz_paylasim(hedef, hizli_video(k, qs, hedef, konu))
        uretilen.append(hedef.name)
    for k in a.alim:
        ilanlar = [i for i in (ilan_ayristir(r) for r in satirlar if r["kanal"] == k) if i]
        enb = max(ilanlar, key=lambda i: sum(int(x) for x in re.findall(r"\((\d+)\)", i["pozisyon"])), default=None)
        if not enb or k not in RENK:
            print(f"ATLANDI {k}: ilan yok")
            continue
        hedef = cikti / f"{k}_alim.mp4"
        yaz_paylasim(hedef, alim_videosu(k, enb, hedef))
        uretilen.append(hedef.name)
    print("Üretilen videolar:", ", ".join(uretilen) or "yok")


if __name__ == "__main__":
    main()
