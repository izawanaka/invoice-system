"""
bap_arsip.py -- SATU implementasi arsip BAP + "nota cetak", dipakai DUA PINTU:
  1. Web   : webapp/routers/bap.py  (unggah foto/PDF lewat dashboard)
  2. Telegram: ocr_doc.py           (foto/PDF dikirim ke bot Izawa AI)

Keputusan owner (28 Juli 2026): "Kalau bisa, menggunakan 2 tempat, bisa telegram
juga bisa web." Jadi BAP yang masuk lewat jalur mana pun WAJIB tercatat di
`app_bap_nota`, karena tabel itulah yang dipakai Aturan Bisnis #9 (invoice hanya
boleh terbit setelah BAP ada).

Letak file: ROOT repo (bukan di webapp/), supaya bisa diimpor keduanya --
`ocr_doc.py` ada di root, dan `webapp/settings.py` sudah menyisipkan root ke
sys.path.

CATATAN PATH (penting): path disimpan di DB secara RELATIF terhadap folder
INVOICE_DATA (mis. "bap_nota/nota_x.pdf"), BUKAN absolut. Alasannya jalur web
berjalan DI DALAM container (INVOICE_DATA=/data) sedangkan jalur Telegram
berjalan di HOST (INVOICE_DATA=/home/izawa/invoice-sandbox-data) -- keduanya
menunjuk folder fisik yang sama, jadi path absolut dari satu sisi tidak bisa
dibuka sisi lain. Pakai jalur() untuk mengubahnya jadi absolut saat dibaca.
"""
import json
import os
import re
import uuid

import config
import db_helper

SUB_UPLOAD = "bap_uploads"
SUB_NOTA = "bap_nota"

_IMG_EXT = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}


def jalur(rel):
    """Path yang tersimpan di DB -> path absolut sesuai lingkungan saat ini.
    Path absolut lama (kalau ada) tetap diterima apa adanya."""
    if not rel:
        return None
    return rel if os.path.isabs(rel) else config.d(rel)


def _ext(filename):
    return (filename.rsplit(".", 1)[-1].lower()
            if filename and "." in filename else "bin")


def _aman(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "")).strip("_")[:60] or "tanpa_nomor"


def _simpan_asli(filename, data):
    folder = config.d(SUB_UPLOAD)
    os.makedirs(folder, exist_ok=True)
    rel = os.path.join(SUB_UPLOAD, f"{uuid.uuid4().hex}.{_ext(filename)}")
    with open(config.d(rel), "wb") as f:
        f.write(data)
    return rel


def _nota_pdf(rel_asli, filename, ocr):
    """Nota cetak: PDF asli disalin apa adanya; foto dibungkus halaman A4 berisi
    ringkasan hasil OCR + gambarnya. Kegagalan menyematkan gambar TIDAK membuat
    proses gagal -- nota tetap dibuat (berisi keterangan + rujukan ke berkas asli)."""
    folder = config.d(SUB_NOTA)
    os.makedirs(folder, exist_ok=True)
    rel = os.path.join(SUB_NOTA, f"nota_{_aman(ocr.get('no_bap'))}_{uuid.uuid4().hex[:8]}.pdf")
    dst = config.d(rel)
    src = config.d(rel_asli)

    if _ext(filename) not in _IMG_EXT:
        import shutil
        shutil.copyfile(src, dst)
        return rel

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    w, h = A4
    c = canvas.Canvas(dst, pagesize=A4)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "NOTA CETAK - BERITA ACARA PENYERAHAN (BAP)")
    c.setFont("Helvetica", 9)
    baris = [
        f"No. BAP   : {ocr.get('no_bap') or '-'}",
        f"Site      : {ocr.get('site') or '-'}",
        f"Tanggal   : {ocr.get('tanggal') or '-'}",
    ]
    qty_kg = float(ocr.get("qty_kg") or 0)
    qty_m3 = float(ocr.get("qty_m3") or 0)
    if qty_kg:
        baris.append(f"Qty (KG)  : {qty_kg:,.0f}".replace(",", "."))
    if qty_m3:
        baris.append(f"Qty (m3)  : {qty_m3:,.3f}".replace(",", "."))
    baris.append(f"Confidence OCR : {ocr.get('confidence') or '-'}"
                 "  (angka final tetap mengikuti dokumen asli di bawah)")
    y = h - 28 * mm
    for b in baris:
        c.drawString(20 * mm, y, b)
        y -= 5 * mm

    try:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(src)
        iw, ih = img.getSize()
        maks_w, maks_h = w - 30 * mm, y - 15 * mm
        skala = min(maks_w / iw, maks_h / ih)
        gw, gh = iw * skala, ih * skala
        c.drawImage(img, (w - gw) / 2, y - 5 * mm - gh, width=gw, height=gh,
                    preserveAspectRatio=True, anchor="n")
    except Exception as e:
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(20 * mm, y - 10 * mm,
                     f"(Gambar tidak bisa disematkan: {str(e)[:60]} -- berkas asli ada di arsip server)")
    c.showPage()
    c.save()
    return rel


KOLOM = ("id, badan_usaha_kode, jenis, no_bap, site, tanggal, qty_kg, qty_m3, "
         "confidence, original_filename, downloaded_at, created_at, sumber")


def _deteksi_mitra_pt(cur, site, badan_usaha_kode=None):
    """Tebak BAP ini untuk PT/mitra mana, berdasar kolom app_mitra_pt.site yang
    cocok dengan site BAP (basis SITE, BUKAN pencocokan nama customer -- tahan
    thd variasi ejaan). Tepat 1 PT -> 'auto'; 0 atau >1 -> 'perlu_konfirmasi'
    (admin pilih di web). badan_usaha_kode dipertahankan di signature demi
    kompatibilitas pemanggil, tidak lagi dipakai memfilter."""
    if not site:
        return (None, "perlu_konfirmasi")
    cur.execute(
        "SELECT id FROM app_mitra_pt WHERE aktif AND site IS NOT NULL "
        "AND lower(site) = lower(%s)",
        (site,),
    )
    ids = [r[0] for r in cur.fetchall()]
    if len(ids) == 1:
        return (ids[0], "auto")
    return (None, "perlu_konfirmasi")


def daftarkan(filename, data, ocr, sumber, badan_usaha_kode=None,
              uploaded_by=None, conn=None):
    """Arsipkan berkas BAP + buat nota cetak + catat di app_bap_nota.

    sumber : "web" atau "telegram" -- supaya ketahuan BAP masuk lewat pintu mana.
    conn   : kalau diberikan, dipakai apa adanya dan TIDAK di-commit (pemanggil
             yang commit). Kalau None, koneksi dibuka & di-commit sendiri.
    Mengembalikan baris hasil INSERT sebagai tuple sesuai KOLOM.
    """
    rel_asli = _simpan_asli(filename, data)
    try:
        rel_nota = _nota_pdf(rel_asli, filename, ocr)
    except Exception:
        rel_nota = rel_asli  # nota gagal dibuat -> pakai berkas asli sbg nota

    sendiri = conn is None
    if sendiri:
        conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_bap_nota (badan_usaha_kode, jenis, no_bap, site, tanggal, "
            "qty_kg, qty_m3, confidence, original_filename, original_path, nota_pdf_path, "
            "ocr_json, uploaded_by, sumber) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) "
            f"RETURNING {KOLOM}",
            (
                (badan_usaha_kode or "").upper() or None,
                ocr.get("jenis"),
                ocr.get("no_bap") or None,
                ocr.get("site") or None,
                ocr.get("tanggal") or None,
                float(ocr.get("qty_kg") or 0) or None,
                float(ocr.get("qty_m3") or 0) or None,
                ocr.get("confidence"),
                filename,
                rel_asli,
                rel_nota,
                json.dumps(ocr, ensure_ascii=False),
                uploaded_by,
                sumber,
            ),
        )
        row = cur.fetchone()
        try:
            _pt_id, _deteksi = _deteksi_mitra_pt(cur, ocr.get("site"), badan_usaha_kode)
            cur.execute(
                "UPDATE app_bap_nota SET mitra_pt_id = %s, deteksi_status = %s WHERE id = %s",
                (_pt_id, _deteksi, row[0]),
            )
        except Exception as _e:
            import sys as _sys
            print(f"  [bap_arsip] deteksi mitra gagal: {_e}", file=_sys.stderr)
        if sendiri:
            conn.commit()
        return row
    finally:
        if sendiri:
            conn.close()


def daftarkan_dari_telegram(filename, data, ocr):
    """Dipanggil ocr_doc.py. GAGAL-AMAN: apa pun yang salah di sini TIDAK boleh
    mengganggu alur bot (balasan OCR tetap terkirim). Pesan kesalahan sengaja
    ke stderr -- stdout dipakai n8n untuk mem-parse JSON hasil OCR."""
    import sys
    try:
        row = daftarkan(filename, data, ocr, sumber="telegram")
        print(f"  [bap_arsip] BAP {ocr.get('no_bap')} tercatat (id={row[0]})", file=sys.stderr)
        return row
    except Exception as e:
        print(f"  [bap_arsip] PERINGATAN: gagal mengarsipkan BAP: {e}", file=sys.stderr)
        return None
