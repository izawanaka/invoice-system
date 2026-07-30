"""
print_packet.py -- "Paket Cetak" satu invoice: gabung Invoice + PO + Faktur Pajak
+ BAP jadi SATU file PDF untuk direview lalu dicetak sekali jalan.

Keputusan owner (28 Juli 2026):
- Isi paket: Invoice + PO + Faktur Pajak + BAP.
- Lembar PO yang dicetak = SCAN PO ASLI dari customer (diunggah lewat menu PO),
  BUKAN ringkasan buatan sistem. Kalau scan belum diunggah, paket tetap terbentuk
  tapi diberi halaman penanda "BELUM DIUNGGAH" supaya ketahuan sebelum dikirim.
- Preview = 1 PDF gabungan.

Prinsip: dokumen resmi TIDAK PERNAH digambar ulang di sini. Invoice memakai PDF
asli hasil invoice_dkp.py/invoice_kks.py apa adanya; faktur pajak & scan PO
memakai berkas asli yang diunggah. Modul ini hanya MENGGABUNG + menyisipkan
halaman penanda untuk bagian yang belum ada.
"""
import io
import os
import subprocess
import tempfile

import settings  # noqa: F401 -- import pertama, set sys.path ke folder induk
import config

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

# Urutan bagian dalam paket (juga dipakai frontend utk menampilkan checklist).
URUTAN_BAGIAN = ["invoice", "po", "faktur_pajak", "bap"]

JUDUL_BAGIAN = {
    "invoice": "INVOICE",
    "po": "PURCHASE ORDER (scan asli dari customer)",
    "faktur_pajak": "FAKTUR PAJAK",
    "bap": "BERITA ACARA PENYERAHAN (BAP)",
}


def _cari_berkas(path: str | None) -> str | None:
    """Path di DB bisa menunjuk lokasi lama (mis. mount CIFS ke PC) yang tidak
    terlihat dari dalam container. Kalau path apa adanya tidak ada, coba cari
    nama berkasnya di folder keluaran yang aktif sekarang."""
    if not path:
        return None
    if os.path.exists(path):
        return path
    nama = os.path.basename(path)
    for folder in (config.OUTPUT_DIR_DKP, config.OUTPUT_DIR_KKS, config.DATA):
        kandidat = os.path.join(folder, nama)
        if os.path.exists(kandidat):
            return kandidat
    return None


def _halaman_teks(judul: str, baris: list[str]) -> bytes:
    """Halaman A4 sederhana (sampul / penanda bagian hilang)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, h - 25 * mm, judul)
    c.setLineWidth(0.8)
    c.line(20 * mm, h - 28 * mm, w - 20 * mm, h - 28 * mm)
    c.setFont("Helvetica", 10)
    y = h - 38 * mm
    for b in baris:
        if y < 20 * mm:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - 25 * mm
        c.drawString(20 * mm, y, b)
        y -= 6 * mm
    c.showPage()
    c.save()
    return buf.getvalue()


def _gambar_ke_pdf(path: str) -> bytes | None:
    """Scan berupa foto -> 1 halaman PDF A4 (proporsi gambar dipertahankan)."""
    try:
        from PIL import Image
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img = Image.open(path)
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = A4
        margin = 28
        skala = min((w - 2 * margin) / img.width, (h - 2 * margin) / img.height)
        gw, gh = img.width * skala, img.height * skala
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.drawImage(ImageReader(img), (w - gw) / 2, (h - gh) / 2, width=gw, height=gh)
        c.showPage()
        c.save()
        return buf.getvalue()
    except Exception:
        return None


def _sebagai_pdf(path: str) -> bytes | None:
    """Kembalikan isi berkas sebagai PDF (gambar dikonversi lebih dulu)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMG_EXT:
        return _gambar_ke_pdf(path)
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data if data[:4] == b"%PDF" else None
    except Exception:
        return None


def _rapikan_pdf(data: bytes) -> bytes:
    """PDF hasil scan/pihak lain kadang rusak ringan sehingga pypdf menolak.
    qpdf (paket poppler/qpdf di image) dipakai sbg penyelamat, bukan wajib."""
    try:
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in.pdf"), os.path.join(d, "out.pdf")
            with open(src, "wb") as f:
                f.write(data)
            subprocess.run(["qpdf", "--decrypt", src, dst], check=True, capture_output=True)
            with open(dst, "rb") as f:
                return f.read()
    except Exception:
        return data


def kumpulkan_bagian(conn, no_invoice: str) -> dict:
    """Kumpulkan SEMUA berkas yang membentuk paket cetak invoice ini.
    Tidak menulis apa pun -- dipakai juga oleh endpoint 'info' supaya frontend
    bisa menampilkan checklist sebelum mencetak."""
    cur = conn.cursor()
    cur.execute(
        "SELECT i.id, bu.kode, i.no_invoice, i.tgl_invoice, i.customer, i.site, "
        "i.total_qty, i.satuan, i.grand_total, i.pdf_path, i.no_faktur_pajak, "
        "i.paperless_doc_id, i.faktur_pajak_path "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    inv = cur.fetchone()
    if inv is None:
        return {"ok": False, "message": f"Invoice {no_invoice} tidak ditemukan"}

    (inv_id, kode, no_inv, tgl_invoice, customer, site, total_qty, satuan,
     grand_total, pdf_path, no_faktur, paperless_id, faktur_path) = inv

    bagian = {k: {"judul": JUDUL_BAGIAN[k], "berkas": [], "hilang": []} for k in URUTAN_BAGIAN}

    # --- 1. Invoice (PDF resmi hasil skrip generator) ---
    p = _cari_berkas(pdf_path)
    if p:
        bagian["invoice"]["berkas"].append({"label": f"Invoice {no_inv}", "path": p})
    else:
        bagian["invoice"]["hilang"].append(
            f"PDF invoice tidak ditemukan di server (tercatat: {pdf_path or '-'})")

    # --- 2. PO: scan asli, satu per PO yang dipotong invoice ini ---
    cur.execute(
        "SELECT DISTINCT po.id, po.po_no FROM invoice_items ii "
        "JOIN purchase_orders po ON po.id = ii.po_id WHERE ii.invoice_id = %s "
        "UNION "
        "SELECT po.id, po.po_no FROM invoices i JOIN purchase_orders po ON po.id = i.po_id "
        "WHERE i.id = %s "
        "ORDER BY 2",
        (inv_id, inv_id),
    )
    po_rows = cur.fetchall()
    for po_id, po_no in po_rows:
        cur.execute(
            "SELECT file_path, original_filename FROM app_po_doc "
            "WHERE po_id = %s ORDER BY created_at DESC, id DESC",
            (po_id,),
        )
        docs = cur.fetchall()
        if docs:
            for fp, orig in docs:
                if os.path.exists(fp):
                    bagian["po"]["berkas"].append({"label": f"PO {po_no} ({orig or 'scan'})", "path": fp})
                else:
                    bagian["po"]["hilang"].append(f"PO {po_no}: berkas hilang di server ({orig or fp})")
        else:
            bagian["po"]["hilang"].append(
                f"PO {po_no}: scan asli BELUM DIUNGGAH -- unggah di halaman rincian PO")
    if not po_rows:
        bagian["po"]["hilang"].append("Invoice ini tidak menunjuk PO mana pun di database")

    # --- 3. Faktur pajak (berkas yang diunggah owner, diarsipkan lokal) ---
    p = _cari_berkas(faktur_path)
    if p:
        bagian["faktur_pajak"]["berkas"].append(
            {"label": f"Faktur Pajak {no_faktur or no_inv}", "path": p})
    else:
        if paperless_id:
            bagian["faktur_pajak"]["hilang"].append(
                f"Faktur pajak sudah masuk Paperless (dok #{paperless_id}) tapi salinan cetaknya "
                f"tidak ada di server -- unggah ulang lewat menu invoice supaya ikut paket")
        else:
            bagian["faktur_pajak"]["hilang"].append(
                "Faktur pajak BELUM diunggah -- unggah lewat menu invoice (aksi Unggah Faktur Pajak)")

    # --- 4. BAP: nota cetak hasil unggahan, dicocokkan per nomor BAP di invoice ---
    cur.execute(
        "SELECT DISTINCT no_bap FROM invoice_items WHERE invoice_id = %s AND no_bap IS NOT NULL "
        "ORDER BY 1",
        (inv_id,),
    )
    bap_nos = [r[0] for r in cur.fetchall()]
    for nb in bap_nos:
        cur.execute(
            "SELECT nota_pdf_path, original_path FROM app_bap_nota WHERE no_bap = %s "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (nb,),
        )
        r = cur.fetchone()
        jalur = None
        if r:
            import bap_arsip
            for kandidat in (bap_arsip.jalur(r[0]), bap_arsip.jalur(r[1])):
                if kandidat and os.path.exists(kandidat):
                    jalur = kandidat
                    break
        if jalur:
            bagian["bap"]["berkas"].append({"label": f"BAP {nb}", "path": jalur})
        else:
            bagian["bap"]["hilang"].append(f"BAP {nb}: belum ada unggahan di sistem")
    if not bap_nos:
        bagian["bap"]["hilang"].append("Invoice ini tidak punya rincian nomor BAP di database")

    return {
        "ok": True,
        "invoice": {
            "no_invoice": no_inv, "badan_usaha_kode": kode, "tgl_invoice": tgl_invoice,
            "customer": customer, "site": site,
            "total_qty": float(total_qty) if total_qty is not None else None,
            "satuan": satuan,
            "grand_total": float(grand_total) if grand_total is not None else None,
            "no_faktur_pajak": no_faktur,
        },
        "po_list": [{"po_no": r[1]} for r in po_rows],
        "bap_list": bap_nos,
        "bagian": bagian,
    }


def _id_angka(n: float, desimal: int = 2) -> str:
    """Format angka gaya Indonesia: 115.000,00 (titik ribuan, koma desimal)."""
    return (f"{n:,.{desimal}f}".replace(",", "\x00").replace(".", ",").replace("\x00", "."))


def _sampul(info: dict) -> bytes:
    inv = info["invoice"]
    baris = [
        f"No. Invoice   : {inv['no_invoice']}",
        f"Badan Usaha   : {inv['badan_usaha_kode']}",
        f"Tanggal       : {inv['tgl_invoice'] or '-'}",
        f"Customer      : {inv['customer'] or '-'}",
        f"Site          : {inv['site'] or '-'}",
        f"Volume        : {_id_angka(inv['total_qty'] or 0)} {inv['satuan'] or ''}",
        f"Grand Total   : Rp {inv['grand_total'] or 0:,.0f}".replace(",", "."),
        f"No. Faktur Pajak : {inv['no_faktur_pajak'] or '-'}",
        "",
        "ISI PAKET:",
    ]
    for key in URUTAN_BAGIAN:
        b = info["bagian"][key]
        n = len(b["berkas"])
        tanda = "OK " if n and not b["hilang"] else ("SEBAGIAN" if n else "BELUM ADA")
        baris.append(f"  [{tanda}] {b['judul']} -- {n} berkas")
        for h in b["hilang"]:
            baris.append(f"        ! {h}")
    baris += ["", "Lembar ini dibuat otomatis oleh sistem sebagai daftar isi paket kirim."]
    return _halaman_teks(f"PAKET CETAK -- {inv['no_invoice']}", baris)


def bangun_pdf(conn, no_invoice: str) -> tuple[bytes, dict]:
    """Gabungkan seluruh bagian jadi satu PDF. Bagian yang hilang TIDAK membuat
    proses gagal -- diganti halaman penanda supaya ketahuan sebelum dikirim."""
    from pypdf import PdfReader, PdfWriter

    info = kumpulkan_bagian(conn, no_invoice)
    if not info.get("ok"):
        raise ValueError(info.get("message", "Gagal mengumpulkan berkas"))

    writer = PdfWriter()

    def tambah(data: bytes):
        try:
            for hal in PdfReader(io.BytesIO(data)).pages:
                writer.add_page(hal)
            return True
        except Exception:
            try:
                for hal in PdfReader(io.BytesIO(_rapikan_pdf(data))).pages:
                    writer.add_page(hal)
                return True
            except Exception:
                return False

    tambah(_sampul(info))

    for key in URUTAN_BAGIAN:
        b = info["bagian"][key]
        for berkas in b["berkas"]:
            data = _sebagai_pdf(berkas["path"])
            ok = tambah(data) if data else False
            if not ok:
                b["hilang"].append(f"{berkas['label']}: berkas tidak bisa dibaca sebagai PDF")
                tambah(_halaman_teks(
                    b["judul"],
                    [f"Berkas '{berkas['label']}' ADA di server tapi tidak bisa dibaca sebagai PDF.",
                     "Periksa berkasnya, lalu unggah ulang."]))
        for h in b["hilang"]:
            tambah(_halaman_teks(b["judul"], ["BAGIAN INI BELUM LENGKAP:", "", h, "",
                                              "Lengkapi dulu sebelum dokumen dikirim ke customer."]))

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), info
