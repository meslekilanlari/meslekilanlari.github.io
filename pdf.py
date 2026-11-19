"""
Günlük çalışma PDF'i üreticisi: konu anlatımı (özet + gerektiğinde detay) + sorular + cevap anahtarı/çözümler.

Kullanım:  python pdf.py icerik.json cikti.pdf

icerik.json:
{
  "kanal": "kpss_gunluksoru",
  "baslik": "Osmanlı Kuruluş Dönemi",
  "alt_baslik": "KPSS Genel Kültür · Tarih",          (isteğe bağlı)
  "giris": "Bu konu sınavda ... (1-3 cümle)",           (isteğe bağlı)
  "bolumler": [
    {"baslik": "Orhan Bey Dönemi",
     "ozet": ["madde", "madde"],                        (kısa maddeler; her bölümde olmalı)
     "detay": ["paragraf", "paragraf"],                  (yalnızca detay gereken bölümlerde)
     "tablo": [["Başlık1","Başlık2"],["a","b"]],         (isteğe bağlı karşılaştırma tablosu)
     "dikkat": "Sınavda sık karıştırılan nokta ..."}     (isteğe bağlı uyarı kutusu)
  ],
  "sorular": [{"soru": "...", "secenekler": ["A şıkkı","B","C","D","E"], "dogru": 2, "aciklama": "..."}],
  "kaynaklar": ["mevzuat.gov.tr – 5188 sayılı Kanun"]   (isteğe bağlı)
}
"dogru" 1'den başlar. Sorular PDF'te cevapsız listelenir, son sayfada cevap anahtarı ve çözümler yer alır.
"""
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# Kanal renkleri (profil fotoğraflarıyla aynı)
RENK = {
    **{k: ("#13294B", "#2B5A8C") for k in ("ozelguvenlikilan_tr", "ogg_sinav", "ozelguvenliksinavi")},
    **{k: ("#B4541A", "#E8892E") for k in ("ogretmen_isilani", "ags_hazirlik", "evrak_ogretmen")},
    **{k: ("#0B6E70", "#18A2A0") for k in ("hemsire_isilanlari", "yurtdisi_hemsire", "saglik_atama")},
    **{k: ("#1F6B43", "#36A36A") for k in ("eczane_isilani", "devir_eczane")},
    **{k: ("#45297F", "#7A55C9") for k in ("mumessil_ilan", "utt_sinav")},
    "isguzmani_sinav": ("#B87A00", "#F2B705"),
    **{k: ("#8E1F1A", "#D2463B") for k in ("kpss_gunluksoru", "kpsstercih_tr")},
    **{k: ("#22313F", "#4A6278") for k in ("kamu_alimlari", "sinav_gorevi")},
}

FONTLAR = [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
for n, b in FONTLAR:
    if Path(n).exists():
        pdfmetrics.registerFont(TTFont("TR", n))
        pdfmetrics.registerFont(TTFont("TRB", b))
        break

HARF = "ABCDE"


def e(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def uret(veri, cikti):
    k = veri["kanal"].lstrip("@")
    c1, c2 = RENK.get(k, ("#13294B", "#2B5A8C"))
    ana, ikinci = colors.HexColor(c1), colors.HexColor(c2)
    acik = colors.Color(ana.red, ana.green, ana.blue, alpha=0.08)

    st = {
        "kapak": ParagraphStyle("kapak", fontName="TRB", fontSize=24, leading=30, textColor=ana, spaceAfter=6),
        "alt": ParagraphStyle("alt", fontName="TR", fontSize=12, leading=16, textColor=colors.HexColor("#555555"), spaceAfter=10),
        "giris": ParagraphStyle("giris", fontName="TR", fontSize=10.5, leading=15, spaceAfter=10),
        "h": ParagraphStyle("h", fontName="TRB", fontSize=14, leading=18, textColor=ana, spaceBefore=10, spaceAfter=6),
        "madde": ParagraphStyle("madde", fontName="TR", fontSize=10.5, leading=14.5, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "detay": ParagraphStyle("detay", fontName="TR", fontSize=10.5, leading=15, spaceAfter=6),
        "etiket": ParagraphStyle("etiket", fontName="TRB", fontSize=9, leading=12, textColor=ikinci, spaceBefore=4, spaceAfter=2),
        "dikkat": ParagraphStyle("dikkat", fontName="TR", fontSize=10, leading=14),
        "soru": ParagraphStyle("soru", fontName="TRB", fontSize=10.5, leading=14.5, spaceBefore=8, spaceAfter=3),
        "sik": ParagraphStyle("sik", fontName="TR", fontSize=10.5, leading=14, leftIndent=14),
        "cozum": ParagraphStyle("cozum", fontName="TR", fontSize=10, leading=14, spaceAfter=6),
        "kaynak": ParagraphStyle("kaynak", fontName="TR", fontSize=8.5, leading=11, textColor=colors.HexColor("#666666")),
        "hucre": ParagraphStyle("hucre", fontName="TR", fontSize=9.5, leading=12.5),
        "hucreb": ParagraphStyle("hucreb", fontName="TRB", fontSize=9.5, leading=12.5, textColor=colors.white),
    }

    def sayfa(cv, doc):
        w, h = A4
        cv.saveState()
        cv.setFillColor(ana)
        cv.rect(0, h - 10 * mm, w, 10 * mm, fill=1, stroke=0)
        cv.setFillColor(colors.white)
        cv.setFont("TRB", 9)
        cv.drawString(15 * mm, h - 6.5 * mm, veri["baslik"][:70])
        cv.drawRightString(w - 15 * mm, h - 6.5 * mm, f"@{k}")
        cv.setFillColor(ana)
        cv.rect(0, 0, w, 11 * mm, fill=1, stroke=0)
        cv.setFillColor(colors.white)
        cv.setFont("TRB", 10)
        cv.drawCentredString(w / 2, 4 * mm, f"@{k} · t.me/{k}")
        cv.setFont("TR", 8)
        cv.drawRightString(w - 15 * mm, 4 * mm, f"Sayfa {doc.page}")
        cv.restoreState()

    def kutu(icerik, zemin, cizgi):
        t = Table([[icerik]], colWidths=[175 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), zemin), ("LINEBEFORE", (0, 0), (0, -1), 3, cizgi),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return t

    h = []
    # kapak bloğu
    h.append(Paragraph(f"@{k}", ParagraphStyle("k", fontName="TRB", fontSize=11, textColor=ikinci, spaceAfter=4)))
    h.append(Paragraph(e(veri["baslik"]), st["kapak"]))
    if veri.get("alt_baslik"):
        h.append(Paragraph(e(veri["alt_baslik"]), st["alt"]))
    icindekiler = " · ".join(e(b["baslik"]) for b in veri["bolumler"])
    sor = len(veri.get("sorular", []))
    h.append(kutu(Paragraph(f"<b>Bu PDF'te:</b> {icindekiler}" + (f" · <b>{sor} soru</b> (cevap anahtarı son sayfada)" if sor else ""),
                            st["dikkat"]), acik, ana))
    h.append(Spacer(1, 8))
    if veri.get("giris"):
        h.append(Paragraph(e(veri["giris"]), st["giris"]))

    for n, b in enumerate(veri["bolumler"], 1):
        blok = [Paragraph(f"{n}. {e(b['baslik'])}", st["h"])]
        if b.get("ozet"):
            blok.append(Paragraph("ÖZET", st["etiket"]))
            blok += [Paragraph(e(m), st["madde"], bulletText="•") for m in b["ozet"]]
        h.append(KeepTogether(blok))
        if b.get("detay"):
            h.append(Paragraph("DETAYLI ANLATIM", st["etiket"]))
            for p in ([b["detay"]] if isinstance(b["detay"], str) else b["detay"]):
                h.append(Paragraph(e(p), st["detay"]))
        if b.get("tablo"):
            rows = [[Paragraph(e(str(x)), st["hucreb" if i == 0 else "hucre"]) for x in r] for i, r in enumerate(b["tablo"])]
            sut = len(b["tablo"][0])
            t = Table(rows, colWidths=[175 * mm / sut] * sut, repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ana), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, acik]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            h += [Spacer(1, 4), t, Spacer(1, 6)]
        if b.get("dikkat"):
            h += [Spacer(1, 4), kutu(Paragraph(f"<b>⚠ Dikkat:</b> {e(b['dikkat'])}", st["dikkat"]),
                                     colors.HexColor("#FFF6E0"), colors.HexColor("#E0A100")), Spacer(1, 4)]

    if veri.get("sorular"):
        h.append(PageBreak())
        h.append(Paragraph("Sorular", st["kapak"]))
        h.append(Paragraph("Önce kendiniz çözün; cevap anahtarı ve çözümler son sayfada.", st["alt"]))
        for i, s in enumerate(veri["sorular"], 1):
            blok = [Paragraph(f"{i}. {e(s['soru'])}", st["soru"])]
            blok += [Paragraph(f"{HARF[j]}) {e(x)}", st["sik"]) for j, x in enumerate(s["secenekler"])]
            h.append(KeepTogether(blok))
        h.append(PageBreak())
        h.append(Paragraph("Cevap Anahtarı ve Çözümler", st["kapak"]))
        anahtar = "   ".join(f"{i}-{HARF[s['dogru'] - 1]}" for i, s in enumerate(veri["sorular"], 1))
        h.append(kutu(Paragraph(f"<b>{anahtar}</b>", st["dikkat"]), acik, ana))
        h.append(Spacer(1, 8))
        for i, s in enumerate(veri["sorular"], 1):
            h.append(Paragraph(f"<b>{i}. Cevap {HARF[s['dogru'] - 1]}</b> – {e(s.get('aciklama', ''))}", st["cozum"]))

    if veri.get("kaynaklar"):
        h += [Spacer(1, 10), Paragraph("Kaynaklar: " + " · ".join(e(x) for x in veri["kaynaklar"]), st["kaynak"])]
    h += [Spacer(1, 10), Paragraph(f"Her gün yeni konu ve sorular: t.me/{k}", st["kaynak"])]

    doc = SimpleDocTemplate(str(cikti), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                            topMargin=17 * mm, bottomMargin=17 * mm, title=veri["baslik"], author=f"@{k}")
    doc.build(h, onFirstPage=sayfa, onLaterPages=sayfa)


def dogrula(veri):
    hatalar = []
    if not veri.get("bolumler"):
        hatalar.append("bolumler boş")
    for b in veri.get("bolumler", []):
        if not b.get("ozet"):
            hatalar.append(f"'{b.get('baslik')}' bölümünde özet yok")
    for i, s in enumerate(veri.get("sorular", []), 1):
        if not 2 <= len(s["secenekler"]) <= 5:
            hatalar.append(f"soru {i}: 2-5 seçenek olmalı")
        if not 1 <= s["dogru"] <= len(s["secenekler"]):
            hatalar.append(f"soru {i}: dogru aralık dışı")
    return hatalar


if __name__ == "__main__":
    veri = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    h = dogrula(veri)
    if h:
        sys.exit("HATA: " + "; ".join(h))
    uret(veri, sys.argv[2])
    print("PDF üretildi:", sys.argv[2])
