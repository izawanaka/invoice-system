#!/usr/bin/env python3
"""
reissue_invoice.py -- Terbitkan ULANG (regenerate) PDF sebuah invoice yang SUDAH ADA,
dari database, TANPA menyentuh saldo PO, nomor invoice, counter, atau baris DB mana pun.

LATAR BELAKANG (16 Juli 2026):
Invoice 090 sempat diterbitkan ulang dengan tanggal SALAH -- tercetak 15 April 2026,
padahal itu tanggal BAP (031/1504/2026), bukan tanggal terbit invoice. Tool ini mengunci
aturan bisnis:

    Tanggal yang DICETAK di invoice = kolom invoices.tgl_invoice (TANGGAL TERBIT).
    BUKAN tanggal BAP. BUKAN tanggal PO. Berlaku untuk SEMUA invoice.

Karena tanggal cetak selalu diambil dari DB tgl_invoice di sini, bug "ikut tanggal BAP"
tidak bisa terulang lewat jalur reissue.

AMAN:
- Tidak ada UPDATE/INSERT ke database. Hanya menulis ulang file PDF.
- Backup PDF lama ke temp; kalau grand total hasil render != invoices.grand_total,
  PDF lama DIPULIHKAN dan proses gagal (exit != 0).

Pemakaian:
    python3 reissue_invoice.py "090/IV/Jembayan/2026"
"""
import sys
import os
import shutil
import tempfile
import db_helper

_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

# cust_addr TIDAK disimpan per-invoice di DB; default ini sama dengan bap_to_invoice.py
# (semua invoice DKP saat ini memakai customer/alamat yang sama).
_DEFAULT_CUST_ADDR = [
    "Jl. 1519 Simpang Empat Terunen Blok.000",
    "RT.010. RW.000 Bumi Harapan, Sepaku Kab. Penajam Paser Utara",
    "Kalimantan Timur 76184",
    "01.609.260.3.725.000",
]


def fmt_tgl(d):
    """date -> '16 Juli 2026' (tanpa nol di depan)."""
    return "%d %s %d" % (d.day, _BULAN[d.month], d.year)


def reissue(no_invoice):
    conn = db_helper.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, badan_usaha_id, tgl_invoice, no_po, site, customer, grand_total, pdf_path, po_id "
        "FROM invoices WHERE no_invoice = %s", (no_invoice,))
    inv = cur.fetchone()
    if not inv:
        cur.close(); conn.close()
        raise SystemExit("Invoice %s tidak ditemukan di database" % no_invoice)
    inv_id, bu_id, tgl_invoice, no_po, site, customer, grand_db, pdf_path, po_id = inv
    cur.execute(
        "SELECT no_bap, deskripsi, qty, harga_sat FROM invoice_items "
        "WHERE invoice_id = %s ORDER BY urutan", (inv_id,))
    rows = cur.fetchall()
    # Alamat customer dari PO invoice ini (purchase_orders.cust_addr). Fallback ke default DKP
    # hanya kalau PO tidak punya alamat (pelajaran Inv 015 KKS, 15 Sep 2026: alamat MPS pernah tercetak alamat DKP).
    cur.execute("SELECT cust_addr FROM purchase_orders WHERE id = %s", (po_id,))
    _row = cur.fetchone()
    cust_addr = list(_row[0]) if _row and _row[0] else _DEFAULT_CUST_ADDR
    cur.close(); conn.close()

    if not rows:
        raise SystemExit("invoice_items kosong untuk %s; regenerate dibatalkan demi keamanan" % no_invoice)

    # Format item persis seperti yang diharapkan generate_pdf: (no_bap, deskripsi, qty, harga)
    items = [(r[0], r[1], float(r[2]), float(r[3])) for r in rows]

    # >>> KUNCI PENCEGAHAN BUG: tanggal cetak = tgl_invoice dari DB (tanggal terbit) <<<
    inv_date = fmt_tgl(tgl_invoice)

    if bu_id == 4:
        import invoice_dkp as gen
    elif bu_id == 5:
        import invoice_kks as gen
    else:
        raise SystemExit("badan_usaha_id %s tidak didukung" % bu_id)

    # Backup PDF lama ke temp (bukan .bak di repo/mount) -> revert kalau verifikasi gagal.
    backup = None
    if pdf_path and os.path.exists(pdf_path):
        fd, backup = tempfile.mkstemp(suffix=".pdf", prefix="reissue_bak_")
        os.close(fd)
        shutil.copy2(pdf_path, backup)

    res = gen.generate_pdf(
        no_invoice, inv_date, items[0][0], site, no_po,
        customer, cust_addr, items)
    filepath = res[0]
    grand = float(res[-1])  # DKP: (fp,sub,dpp,vat,grand) | KKS: (fp,sub,grand)

    if abs(grand - float(grand_db)) > 1:
        if backup:
            shutil.copy2(backup, pdf_path)
            os.remove(backup)
        raise SystemExit(
            "GAGAL: grand render %s != DB %s. PDF lama sudah dipulihkan, tidak ada perubahan." % (grand, grand_db))

    if backup:
        os.remove(backup)
    print("OK reissue %s | tanggal=%s | grand=%s | file=%s" % (no_invoice, inv_date, grand, filepath))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Pemakaian: python3 reissue_invoice.py "<no_invoice>"')
    reissue(sys.argv[1])
