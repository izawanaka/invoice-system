#!/usr/bin/env python3
# =============================================================================
#  Invoice Generator — CV. KREASI KARYA SUKSES
#  Untuk docker-host (192.168.68.107)
#  PO Tracker: /home/izawa/po_tracker_kks.json
#  Output PDF: /mnt/media/D/SynologyDrive/PT/PT. Deliandra Karya Pratama/Inv-AI-KKS/
# =============================================================================

import os, sys, json, urllib.request, urllib.parse
import sys as _sys_path_fix
import os as _os_path_fix
# File ini DISALIN ke /tmp lalu dijalankan (lihat patch_and_run), jadi __file__
# menunjuk /tmp -- bukan folder kode. Pemanggil menyetel INVOICE_CODE ke folder
# kode yang benar (produksi ATAU sandbox). Fallback: folder file ini sendiri.
_sys_path_fix.path.insert(0, _os_path_fix.environ.get(
    "INVOICE_CODE", _os_path_fix.path.dirname(_os_path_fix.path.abspath(__file__))))
import config
import db_helper
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors

# ── KONFIGURASI ───────────────────────────────────────────────────────────────
# BUG LAMA (diperbaiki 14 Juli 2026): dua file ini dulu menunjuk /home/izawa/...,
# sementara bap_to_invoice_kks.py memakai yang di folder invoice-system. Jadi setelah
# invoice KKS terbit, refresh_po_tracker_json() memperbarui file yang SALAH -- tracker
# yang benar-benar dipakai untuk alokasi PO tidak pernah ikut diperbarui (saldo basi).
# DKP sudah benar; KKS terlewat. Sekarang keduanya satu sumber lewat config.
PO_FILE      = config.d("po_tracker_kks.json")
INV_NO_FILE  = config.d("last_invoice_no_kks.txt")
OUTPUT_DIR   = config.OUTPUT_DIR_KKS
TG_TOKEN     = config.tg_token()
TG_CHAT      = "1251069696"
WARNING_PCT  = 15

# ── INPUT DATA ────────────────────────────────────────────────────────────────
INV_NO      = "006/04/Senyiur/26"
INV_DATE    = "13 Juni 2026"
NO_BAP      = "001/0613/2026"
SITE        = "Senyiur"
NO_PO       = ""
PO_SPLITS   = [("", 0)]                # [(po_no, qty_m3_untuk_po_ini), ...] -- diisi ulang saat ada split 2 PO
CUSTOMER    = "PT. Berau Hutani Lestari"
CUST_ADDR   = [
    "Jl. Contoh Alamat No.1",
    "Berau, Kalimantan Timur",
    "00.000.000.0.000.000",
]
# Items: (no_item, deskripsi, qty_m3, rp_per_m3)
ITEMS = [
    (1, "Cocopeat", 100, 50000),
]

# ─────────────────────────────────────────────────────────────────────────────

def baca_po_tracker(no_po):
    try:
        with open(PO_FILE) as f:
            tracker = json.load(f)
    except Exception as e:
        print(f"  WARNING: Gagal baca PO Tracker: {e}")
        return None
    for po in tracker["po_list"]:
        if po["po_no"] == no_po and po["status"] == "aktif":
            sisa = po["total_m3"] - po.get("used_m3", 0)
            pct  = (sisa / po["total_m3"]) * 100
            return {**po, "sisa_m3": sisa, "pct_sisa": pct}
    print(f"  WARNING: PO {no_po} tidak ditemukan atau tidak aktif")
    return None


def update_po_tracker(no_po, qty_m3):
    try:
        with open(PO_FILE) as f:
            tracker = json.load(f)
    except Exception as e:
        print(f"  WARNING: Gagal baca PO Tracker: {e}")
        return False

    updated = False
    for po in tracker["po_list"]:
        if po["po_no"] == no_po:
            po["used_m3"] = po.get("used_m3", 0) + qty_m3
            sisa = po["total_m3"] - po["used_m3"]
            pct  = (sisa / po["total_m3"]) * 100
            print(f"  OK Saldo diupdate: sisa {sisa:,.0f} M3 ({pct:.1f}%)")
            if pct < WARNING_PCT:
                kirim_warning(po, sisa, pct)
            updated = True
            break

    if updated:
        with open(PO_FILE, "w") as f:
            json.dump(tracker, f, indent=2, ensure_ascii=False)
    return updated


def kirim_warning(po, sisa, pct):
    msg = "PERINGATAN SALDO PO\n\n"
    msg += "Site     : " + po["site"] + "\n"
    msg += "No PO    : " + po["po_no"] + "\n"
    msg += "Total    : " + "{:,.0f}".format(po["total_m3"]) + " M3\n"
    msg += "Terpakai : " + "{:,.0f}".format(po["used_m3"]) + " M3\n"
    msg += "Sisa     : " + "{:,.0f}".format(sisa) + " M3 (" + "{:.1f}".format(pct) + "%)\n\n"
    msg += "Segera siapkan PO baru!"
    url  = "https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg}).encode()
    try:
        urllib.request.urlopen(url, data, timeout=10)
        print("  Warning Telegram terkirim!")
    except Exception as e:
        print(f"  WARNING: Gagal kirim Telegram: {e}")


def _parse_tgl(s):
    from datetime import datetime
    bulan_map = {"januari":1,"februari":2,"maret":3,"april":4,"mei":5,"juni":6,
                 "juli":7,"agustus":8,"september":9,"oktober":10,"november":11,"desember":12}
    try:
        if "-" in s:
            return datetime.strptime(s, "%Y-%m-%d").date()
        parts = s.lower().split()
        return datetime(int(parts[2]), bulan_map.get(parts[1], 1), int(parts[0])).date()
    except Exception:
        return datetime.now().date()


def format_rp(val):
    return "Rp{:,.0f}".format(val).replace(",", ".")


def generate_pdf(inv_no, inv_date, no_bap, site, no_po, customer, cust_addr, items):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe = inv_no.replace("/", "_").replace(" ", "_")
    filepath = os.path.join(OUTPUT_DIR, f"Inv_{safe}.pdf")

    PAGE = landscape(A4)
    W, H = PAGE
    c = canvas.Canvas(filepath, pagesize=PAGE)

    def text(x, y, s, size=9, bold=False, align="left", underline=False):
        if bold:
            c.setFont("Helvetica-Bold", size)
        else:
            c.setFont("Helvetica", size)
        if align == "center":
            c.drawCentredString(x, y, str(s))
        elif align == "right":
            c.drawRightString(x, y, str(s))
        else:
            c.drawString(x, y, str(s))
        if underline:
            tw = c.stringWidth(str(s), "Helvetica-Bold" if bold else "Helvetica", size)
            if align == "center":
                c.line(x - tw/2, y - 1*mm, x + tw/2, y - 1*mm)
            elif align == "right":
                c.line(x - tw, y - 1*mm, x, y - 1*mm)
            else:
                c.line(x, y - 1*mm, x + tw, y - 1*mm)

    def line(x1, y1, x2, y2, width=0.5):
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    margin_l  = 20*mm
    margin_r  = W - 20*mm
    content_w = margin_r - margin_l
    content_h = 175*mm
    top_y     = (H + content_h) / 2
    y         = top_y

    # ── HEADER ───────────────────────────────────────────────────────────────
    text(margin_l, y, "INVOICE", size=14, bold=True, underline=True)
    text(margin_r, y, "CV. KREASI KARYA SUKSES", size=14, bold=True, align="right", underline=True)
    y -= 8*mm

    col1_label = margin_l
    col1_val   = margin_l + 28*mm
    fields_left = [
        ("Inv No",         ": " + inv_no),
        ("Date",           ": " + inv_date),
        ("Payment Term",   ": 30 Days"),
        ("ORDER REF. NO.", ": " + no_po),
    ]
    y_left = y
    for label, val in fields_left:
        text(col1_label, y_left, label, size=9)
        text(col1_val,   y_left, val,   size=9)
        y_left -= 5*mm

    y_right = y
    addr_lines = [
        "General Suplier",
        "Jl.Tengku Umar No.43-B RT.003 RW.007",
        "Email  : kreasikarya@yahoo.com",
        "Phone : 0812 6818 9588",
    ]
    for addr in addr_lines:
        text(margin_r, y_right, addr, size=9, align="right")
        y_right -= 5*mm

    y = y_left - 2*mm

    text(col1_label, y, "Customer", size=9)
    text(col1_val,   y, ": " + customer, size=9)
    y -= 5*mm
    for addr_line in cust_addr:
        text(col1_val, y, "  " + addr_line, size=9)
        y -= 4.5*mm

    y -= 3*mm

    # ── TABEL (tanpa kolom DO NO) ─────────────────────────────────────────────
    tbl_top = y
    cols = {
        "no":     margin_l,
        "desc":   margin_l + 12*mm,
        "qty":    margin_l + 100*mm,
        "unit":   margin_l + 118*mm,
        "curr":   margin_l + 130*mm,
        "price":  margin_l + 142*mm,
        "amount": margin_l + 166*mm,
    }
    col_end = margin_r
    row_h   = 7*mm
    hdr_y   = tbl_top - row_h

    c.setLineWidth(0.8)
    c.rect(margin_l, hdr_y, content_w, row_h, fill=0)

    col_keys = ["no", "desc", "qty", "unit", "curr", "price", "amount"]
    headers  = [
        (cols["no"],     "NO",               "center"),
        (cols["desc"],   "ITEM DESCRIPTION", "center"),
        (cols["qty"],    "QTY",              "center"),
        (cols["unit"],   "UNIT",             "center"),
        (cols["curr"],   "CURR",             "center"),
        (cols["price"],  "UNIT PRICE",       "center"),
        (cols["amount"], "AMOUNT",           "center"),
    ]
    col_widths_map = {
        "no":     cols["desc"]   - cols["no"],
        "desc":   cols["qty"]    - cols["desc"],
        "qty":    cols["unit"]   - cols["qty"],
        "unit":   cols["curr"]   - cols["unit"],
        "curr":   cols["price"]  - cols["curr"],
        "price":  cols["amount"] - cols["price"],
        "amount": col_end        - cols["amount"],
    }
    for (hx, hlabel, halign), ckey in zip(headers, col_keys):
        cw = col_widths_map[ckey]
        text(hx + cw/2, hdr_y + 2.5*mm, hlabel, size=8, bold=True, align="center")

    for cx in [cols["desc"], cols["qty"], cols["unit"], cols["curr"], cols["price"], cols["amount"], col_end]:
        line(cx, hdr_y, cx, hdr_y + row_h)

    row_y     = hdr_y
    total_rows = 7
    sub_total  = 0

    for i in range(total_rows):
        row_y -= row_h
        c.setLineWidth(0.3)
        c.rect(margin_l, row_y, content_w, row_h, fill=0)
        for cx in [cols["desc"], cols["qty"], cols["unit"], cols["curr"], cols["price"], cols["amount"], col_end]:
            line(cx, row_y, cx, row_y + row_h, width=0.3)

        if i < len(items):
            item_no, item_desc, qty, harga = items[i]
            amount     = qty * harga
            sub_total += amount
            text(cols["no"]     + 6*mm,  row_y + 2.5*mm, str(i+1), align="center")
            text(cols["desc"]   + 2*mm,  row_y + 2.5*mm, item_desc)  # deskripsi SUDAH memuat nomor PO baris ini (lihat alokasi_po)
            qty_str = "{:,.2f}".format(qty).replace(",","X").replace(".",",").replace("X",".")
            text(cols["qty"]    + 1*mm,  row_y + 2.5*mm, qty_str)
            text(cols["unit"]   + 6*mm,  row_y + 2.5*mm, "M3",  align="center")
            text(cols["curr"]   + 6*mm,  row_y + 2.5*mm, "IDR", align="center")
            text(cols["price"]  + 12*mm, row_y + 2.5*mm, "Rp{:,.0f}".format(harga).replace(",","."), align="center")
            text(cols["amount"] + 37*mm, row_y + 2.5*mm, "Rp{:,.0f}".format(amount).replace(",","."), align="right")

    tbl_bot   = row_y
    grand     = sub_total  # KKS: tanpa PPN

    # ── FOOTER ───────────────────────────────────────────────────────────────
    y_foot = tbl_bot - 6*mm
    text(margin_l,          y_foot, "Term of Payment", size=9)
    y_foot -= 5*mm
    text(margin_l,          y_foot, "Payable to : CV. KREASI KARYA SUKSES", size=9)
    y_foot -= 5*mm
    text(margin_l + 18*mm,  y_foot, "BANK MANDIRI", size=9)
    y_foot -= 5*mm
    text(margin_l,          y_foot, "Account    : 108-00-2709-539-8", size=9)

    total_label_x = cols["price"] + (cols["amount"] - cols["price"]) / 2
    colon_x       = cols["price"] + (cols["amount"] - cols["price"]) / 2 + 38*mm
    amount_x      = col_end - 12*mm
    y_tot = tbl_bot - 6*mm

    text(total_label_x, y_tot, "Sub Total", size=9)
    text(colon_x,       y_tot, ":", size=9, align="right")
    text(amount_x,      y_tot, format_rp(sub_total), size=9, align="right")
    y_tot -= 5*mm

    c.setLineWidth(0.5)
    c.line(total_label_x, y_tot + 3*mm, amount_x, y_tot + 3*mm)
    y_tot -= 1.5*mm

    text(total_label_x, y_tot, "Grand Total", size=10, bold=True)
    text(colon_x,       y_tot, ":", size=10, bold=True, align="right")
    text(amount_x,      y_tot, format_rp(grand), size=10, bold=True, align="right")

    # ── TTD ──────────────────────────────────────────────────────────────────
    y_ttd        = tbl_bot - 35*mm
    ttd_center_x = col_end - 35*mm
    text(ttd_center_x, y_ttd, "CV. KREASI KARYA SUKSES", size=9, bold=True, align="center")
    y_ttd -= 4*mm
    text(ttd_center_x, y_ttd, "Materai 6.000", size=9, align="center")
    y_ttd -= 18*mm
    text(ttd_center_x, y_ttd, "Direktur", size=9, align="center")
    y_ttd -= 5*mm
    text(ttd_center_x, y_ttd, "HURJANTO", size=9, bold=True, align="center")

    c.save()
    return filepath, sub_total, grand


def main():
    print("=" * 55)
    print("  INVOICE GENERATOR -- CV. KREASI KARYA SUKSES")
    print("=" * 55)

    print("Membaca PO Tracker...")
    po_data = baca_po_tracker(NO_PO)
    if po_data:
        print(f"  PO ditemukan : {po_data['po_no']} ({po_data['site']})")
        print(f"  Sisa saldo   : {po_data['sisa_m3']:,.0f} M3 ({po_data['pct_sisa']:.1f}%)")
        total_qty = sum(item[2] for item in ITEMS)
        if total_qty > po_data["sisa_m3"]:
            print(f"  PERINGATAN: QTY {total_qty:,.0f} M3 melebihi sisa PO {po_data['sisa_m3']:,.0f} M3!")

    # ===== TRANSAKSI ATOMIK (lihat DESIGN.md) =====
    # Kunci baris PO -> generate PDF -> commit semua bareng.
    # Kalau PDF gagal, SEMUA perubahan DB di-rollback: saldo PO tidak berkurang,
    # tidak ada invoice/bap nyangkut setengah jalan.
    # KKS = Non-PKP: dpp & ppn selalu 0, grand_total = sub_total.
    total_qty = sum(item[2] for item in ITEMS)
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        for po_no_x, qty_x in PO_SPLITS:
            if qty_x <= 0:
                continue
            cur.execute(
                "SELECT id, total_qty, used_qty FROM purchase_orders "
                "WHERE po_no=%s AND badan_usaha_id=5 AND status='aktif' FOR UPDATE",
                (po_no_x,)
            )
            row_po = cur.fetchone()
            if row_po is None:
                raise RuntimeError(f"PO {po_no_x} tidak ditemukan / tidak aktif di database (badan_usaha_id=5)")
            # PENJAGA SALDO (aturan owner 14 Juli 2026): baris PO sudah dikunci FOR UPDATE,
            # jadi angka ini adalah kebenaran terakhir. Kalau QTY melebihi sisa -> BATALKAN
            # seluruh transaksi. Tidak ada PDF, tidak ada invoice, saldo PO tidak berubah.
            # Dicek di DATABASE (bukan cuma po_tracker.json) karena JSON bisa basi.
            _sisa_po = float(row_po[1]) - float(row_po[2] or 0)
            if float(qty_x) > _sisa_po + 1e-6:
                raise RuntimeError(
                    f"QTY {float(qty_x):,.2f} melebihi sisa PO {po_no_x} ({_sisa_po:,.2f}). "
                    f"Invoice DIBATALKAN, tidak ada data yang berubah. Daftarkan PO baru dulu."
                )

        print("Generating PDF...")
        filepath, sub_total, grand = generate_pdf(
            INV_NO, INV_DATE, NO_BAP, SITE, NO_PO,
            CUSTOMER, CUST_ADDR, ITEMS
        )

        print("-" * 55)
        print(f"  Invoice    : {INV_NO}")
        print(f"  No. BAP    : {NO_BAP}")
        print(f"  Site       : {SITE}")
        print(f"  Customer   : {CUSTOMER}")
        print(f"  Tanggal    : {INV_DATE}")
        print(f"  No. PO     : {NO_PO}")
        print("-" * 55)
        for item in ITEMS:
            print(f"  Item {item[0]}     : {item[2]:,} M3 x Rp{item[3]:,} = {format_rp(item[2]*item[3])}")
        print("-" * 55)
        print(f"  Sub Total  : {format_rp(sub_total)}")
        print(f"  Grand Total: {format_rp(grand)}")
        print("-" * 55)
        print(f"  File: {filepath}")

        for po_no_x, qty_x in PO_SPLITS:
            if qty_x > 0:
                cur.execute(
                    "UPDATE purchase_orders SET used_qty = used_qty + %s WHERE po_no=%s AND badan_usaha_id=5",
                    (qty_x, po_no_x)
                )
        cur.execute(
            "INSERT INTO bap (badan_usaha_id, no_bap, site, tgl_bap, total_qty, satuan, status) "
            "VALUES (5, %s, %s, %s, %s, 'm3', 'invoiced') ON CONFLICT DO NOTHING",
            (NO_BAP, SITE, _parse_tgl(INV_DATE), total_qty)
        )
        try:
            inv_seq = int(INV_NO.split("/")[0])
        except Exception:
            inv_seq = None
        # BUG (ditemukan di sandbox, 14 Juli 2026): po_id dulu dicari pakai NO_PO. Saat
        # invoice terpecah 2 PO, NO_PO berisi "A / B" -> subquery tidak menemukan apa pun
        # -> po_id NULL -> INSERT DITOLAK (kolom NOT NULL). Artinya invoice split TIDAK
        # PERNAH bisa tersimpan ke database. po_id sekarang = PO UTAMA (PO tertua dalam
        # split); rincian tiap PO dicatat lengkap di tabel invoice_items di bawah.
        po_utama = PO_SPLITS[0][0] if PO_SPLITS else NO_PO
        cur.execute(
            "INSERT INTO invoices (badan_usaha_id, no_invoice, seq_no, tgl_invoice, tgl_bap, po_id, no_po, "
            "site, customer, total_qty, satuan, sub_total, dpp, ppn, grand_total, pdf_path, status) "
            "VALUES (5, %s, %s, CURRENT_DATE, %s, "
            "(SELECT id FROM purchase_orders WHERE po_no=%s AND badan_usaha_id=5 LIMIT 1), "
            "%s, %s, %s, %s, 'm3', %s, 0, 0, %s, %s, 'generated') "
            "ON CONFLICT (no_invoice) DO NOTHING RETURNING id",
            (INV_NO, inv_seq, _parse_tgl(INV_DATE), po_utama, NO_PO, SITE, CUSTOMER,
             total_qty, sub_total, grand, filepath)
        )
        _r = cur.fetchone()
        if _r:
            invoice_id = _r[0]
        else:
            cur.execute("SELECT id FROM invoices WHERE no_invoice=%s", (INV_NO,))
            invoice_id = cur.fetchone()[0]

        # Rincian baris invoice -- satu baris per PO kalau split. Tabel invoice_items
        # sebelumnya KOSONG (tidak pernah diisi): rincian split cuma hidup di PDF, tidak
        # di database. Padahal Postgres yang jadi sumber kebenaran, bukan PDF.
        # po_id WAJIB diisi: Penjaga Konsistensi menjumlahkan pemakaian PO dari
        # invoice_items.po_id. Kalau dijumlahkan dari invoices.total_qty per invoices.po_id,
        # invoice SPLIT akan salah dibaca -- invoices.po_id cuma menyimpan PO UTAMA sementara
        # total_qty memuat SELURUH kiriman, jadi luberan ke PO kedua tak terlihat dan penjaga
        # menyalak tiap hari untuk data yang sebenarnya benar.
        # ITEMS dan PO_SPLITS sejajar urutannya (keduanya keluaran alokasi_po).
        for _urut, ((_no, _desc, _qty, _harga), (_po, _)) in enumerate(zip(ITEMS, PO_SPLITS), start=1):
            if _qty <= 0:
                continue
            cur.execute(
                "INSERT INTO invoice_items (invoice_id, urutan, no_bap, deskripsi, qty, "
                "satuan, harga_sat, subtotal, po_id) VALUES (%s, %s, %s, %s, %s, 'm3', %s, %s, "
                "(SELECT id FROM purchase_orders WHERE po_no=%s AND badan_usaha_id=5)) "
                "ON CONFLICT (invoice_id, urutan) DO NOTHING",
                (invoice_id, _urut, NO_BAP, _desc, _qty, _harga, _qty * _harga, _po)
            )

        conn.commit()
        print("Update saldo PO Tracker (dari Postgres, sudah commit)...")
        db_helper.refresh_po_tracker_json(conn, 5, PO_FILE, "total_m3", "used_m3", "rp_m3", "m3")
    except Exception as e:
        conn.rollback()
        # PDF ditulis SEBELUM commit. Kalau transaksi batal, PDF harus ikut dihapus --
        # kalau tidak, ada PDF invoice yang tidak punya catatan di database sama sekali
        # (invoice "hantu" nyangkut di folder PC).
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
        print(json.dumps({"status":"error","message": f"Transaksi database gagal, PDF/invoice DIBATALKAN total: {e}"}))
        sys.exit(1)
    finally:
        conn.close()

    try:
        inv_num = int(INV_NO.split("/")[0])
        with open(INV_NO_FILE, "w") as f:
            f.write(str(inv_num).zfill(3))
    except:
        pass

    print("Selesai!")
    print("=" * 55)


if __name__ == "__main__":
    main()
