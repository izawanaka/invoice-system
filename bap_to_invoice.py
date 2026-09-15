#!/usr/bin/env python3
import json, sys, os, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_helper
import os
import config

INPUT_FILE     = config.d("bap_input.json")
PO_FILE        = config.d("po_tracker.json")
INV_NO_FILE    = config.d("last_invoice_no.txt")
OUTPUT_DIR     = config.OUTPUT_DIR_DKP
INVOICE_SCRIPT = config.INVOICE_DKP

BULAN = {1:"I",2:"II",3:"III",4:"IV",5:"V",6:"VI",
         7:"VII",8:"VIII",9:"IX",10:"X",11:"XI",12:"XII"}

def next_inv_no(site, date_str):
    # Baca next_seq dari bap_input.json jika sudah diset oleh n8n Postgres node.
    # PENTING: jangan tulis ke INV_NO_FILE di sini -- nomor baru boleh dipersist
    # ke disk HANYA setelah PDF beneran berhasil dibuat (lihat main(), setelah
    # pengecekan stderr). Ini mencegah counter maju duluan padahal generate gagal.
    # Nomor invoice = TERTINGGI antara (MAX seq_no di Postgres) dan (counter file).
    # Kenapa max(): tabel invoices di DB baru mulai diisi 13 Juli 2026, riwayat lama
    # tidak bisa direkonstruksi -- jadi DB saja tidak cukup (bisa mundur ke 001).
    # Counter file jadi lantai bawah, DB jadi pengaman kalau file hilang/rusak.
    # LIHAT DESIGN.md sebelum mengubah ini.
    file_last = None
    try:
        with open(INV_NO_FILE) as f:
            file_last = int(f.read().strip())
    except Exception:
        pass

    db_last = None
    try:
        _conn = db_helper.get_conn()
        _cur = _conn.cursor()
        _cur.execute("SELECT COALESCE(MAX(seq_no), 0) FROM invoices WHERE badan_usaha_id = 4")
        db_last = int(_cur.fetchone()[0])
        _cur.close()
        _conn.close()
    except Exception:
        pass

    candidates = [x for x in (file_last, db_last) if x is not None]
    last = max(candidates) if candidates else 86
    next_no = last + 1
    from datetime import datetime
    try:
        if "-" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            bulan_map = {"januari":1,"februari":2,"maret":3,"april":4,
                "mei":5,"juni":6,"juli":7,"agustus":8,
                "september":9,"oktober":10,"november":11,"desember":12}
            parts = date_str.lower().split()
            month = bulan_map.get(parts[1], datetime.now().month)
            year  = int(parts[2])
            dt    = datetime(year, month, int(parts[0]))
    except:
        dt = datetime.now()
    roman  = BULAN[dt.month]
    inv_no = f"{next_no:03d}/{roman}/{site}/{dt.year}"
    return inv_no, next_no

def get_po_list(site):
    """SEMUA PO aktif untuk site ini, urut nomor PO (PO lama dihabiskan duluan)."""
    with open(PO_FILE) as f:
        tracker = json.load(f)
    active = [p for p in tracker["po_list"]
              if p["site"].lower() == site.lower() and p["status"] == "aktif"]
    active.sort(key=lambda p: p["po_no"])
    return active


def get_po(site):
    """Kompatibilitas: 2 PO pertama. Alokasi sebenarnya pakai get_po_list + alokasi_po."""
    lst = get_po_list(site)
    if not lst:
        return None, None
    return lst[0], (lst[1] if len(lst) > 1 else None)


def alokasi_po(qty_list, po_list, qty_field, used_field, price_field):
    """Alokasikan QTY (satu BAP atau banyak BAP) ke PO aktif secara berurutan.

    Aturan bisnis (ditetapkan owner, 14 Juli 2026):
      - PO lama (nomor terkecil) DIHABISKAN dulu, baru pindah ke PO berikutnya.
        Berlaku untuk SEMUA PO aktif, bukan cuma 2 pertama.
      - Tiap potongan jadi SATU BARIS item, deskripsinya mencantumkan nomor PO-nya
        SENDIRI: "Cocopeat - PO.<no_po>", dikali HARGA PO TERSEBUT.
      - Kalau total QTY MELEBIHI sisa seluruh PO aktif -> ValueError.
        Invoice TIDAK diterbitkan. Nol perubahan data. (Dulu: invoice tetap terbit
        dan saldo PO jadi minus diam-diam -- hanya dicetak "PERINGATAN" ke stdout
        yang tidak pernah sampai ke Telegram.)
    """
    if not po_list:
        raise ValueError("Tidak ada PO aktif untuk site ini. Daftarkan PO dulu.")

    sisa = [[p["po_no"],
             float(p[qty_field]) - float(p.get(used_field, 0) or 0),
             float(p[price_field])] for p in po_list]
    total_sisa  = sum(s[1] for s in sisa if s[1] > 0)
    total_minta = sum(float(q) for q in qty_list)

    if total_minta > total_sisa + 1e-6:
        rincian = ", ".join(f"PO.{s[0]}: {s[1]:,.2f}" for s in sisa if s[1] > 0) or "(semua PO habis)"
        raise ValueError(
            f"QTY {total_minta:,.2f} melebihi sisa seluruh PO aktif ({total_sisa:,.2f}). "
            f"Sisa per PO -> {rincian}. Daftarkan PO baru dulu (kirim foto PO atau /addpo)."
        )

    items, splits, urutan = [], {}, []
    idx = 0
    for q in qty_list:
        q = float(q)
        while q > 1e-9:
            if idx >= len(sisa):
                raise ValueError("Sisa PO habis di tengah alokasi (seharusnya sudah ditolak di atas).")
            po_no, tersedia, harga = sisa[idx]
            if tersedia <= 1e-9:
                idx += 1
                continue
            ambil = round(min(q, tersedia), 4)
            # Kalau nomor PO sudah berawalan "PO" (mis. PO-12-000...), jangan tambah "PO." lagi
            label_po = po_no if str(po_no).upper().startswith("PO") else f"PO.{po_no}"
            items.append((len(items) + 1, f"Cocopeat - {label_po}", ambil, harga))
            if po_no not in splits:
                urutan.append(po_no)
            splits[po_no] = round(splits.get(po_no, 0) + ambil, 4)
            sisa[idx][1] = tersedia - ambil
            q = round(q - ambil, 6)

    po_splits = [(p, splits[p]) for p in urutan]
    order_ref = " / ".join(urutan)
    return items, po_splits, order_ref

def patch_and_run(inv_no, inv_date, no_bap, site, no_po, customer, cust_addr, items, po_splits=None):
    with open(INVOICE_SCRIPT) as f:
        src = f.read()
    def replace_var(s, var, new_val):
        return re.sub(rf'^({var}\s*=\s*).*$', rf'\g<1>{new_val}', s, flags=re.MULTILINE)
    src = replace_var(src, 'INV_NO',   f'"{inv_no}"')
    src = replace_var(src, 'INV_DATE', f'"{inv_date}"')
    src = replace_var(src, 'NO_BAP',   f'"{no_bap}"')
    src = replace_var(src, 'SITE',     f'"{site}"')
    src = replace_var(src, 'NO_PO',    f'"{no_po}"')
    src = replace_var(src, 'CUSTOMER', f'"{customer}"')
    if po_splits:
        splits_str = "[" + ", ".join(f'(\"{p}\", {q})' for p, q in po_splits) + "]"
        src = re.sub(r'^PO_SPLITS\s*=\s*\[.*?\]', f'PO_SPLITS = {splits_str}',
                     src, flags=re.MULTILINE|re.DOTALL)
    items_str = "[\n"
    for item in items:
        items_str += f"    ({item[0]}, \"{item[1]}\", {item[2]}, {item[3]}),\n"
    items_str += "]"
    src = re.sub(r'^ITEMS\s*=\s*\[.*?\]', f'ITEMS = {items_str}',
                 src, flags=re.MULTILINE|re.DOTALL)
    # Nama file per-lingkungan: sandbox dan produksi TIDAK BOLEH saling menimpa
    tmp = f"/tmp/invoice_run_{config.ENV}.py"
    with open(tmp, "w") as f:
        f.write(src)
    # INVOICE_CODE: beri tahu script salinan di /tmp di mana folder kode berada.
    env = {**os.environ, "INVOICE_CODE": config.BASE}
    result = subprocess.run(["python3", tmp], capture_output=True, text=True, env=env)
    return result.stdout, result.stderr, result.returncode



def update_excel_log(inv_no, site, no_bap, baris_po, inv_date):
    """Tulis invoice ke sheet Pengiriman -- SATU BARIS PER PO.

    baris_po = [(po_no, qty, harga), ...]  -- sama persis dengan invoice_items di Postgres.

    DUA BUG LAMA yang diperbaiki di sini (14 Juli 2026):

    1. Kolom C ditulis TANPA awalan 'PO-'. Padahal PO Master menghitung terpakai lewat
         Used KG = SUMIF(Pengiriman!C:C, "PO-"&A2, Pengiriman!G:G)
       yang mencocokkan kolom C PERSIS dengan "PO-4500264734". Tanpa awalan itu SUMIF tidak
       menemukan apa pun -> saldo PO di Excel TIDAK PERNAH BERKURANG, dan sheet PO Detail
       (yang juga mencari "PO-<nomor>") tidak menampilkan invoicenya. Database benar, Excel buta.

    2. Invoice split dijejalkan ke SATU baris dengan SATU harga rata-rata. Dua PO berharga beda
       (mis. Rp3.100 dan Rp3.520) jadi "Rp3.223", sehingga formula G*H meleset dari nilai
       invoice sebenarnya, dan kolom C berisi "4500264734 / 4500268584" yang tidak cocok dengan
       PO manapun. Sekarang tiap PO dapat barisnya sendiri dengan harga aslinya. Sheet ini memang
       sudah biasa memuat beberapa baris untuk satu invoice (kolom L menjumlahkannya lewat
       SUMIF), jadi ini mengikuti pola yang sudah ada.
    """
    import openpyxl, subprocess
    from openpyxl.styles import Alignment
    from datetime import datetime

    EXCEL = config.EXCEL_DKP
    SMB   = config.SMB_DKP

    try:
        wb = openpyxl.load_workbook(EXCEL)
        ws = wb["Pengiriman"]

        tgl_invoice = datetime.now().strftime("%d %B %Y").lstrip("0")
        bulan_en = ["January","February","March","April","May","June",
                    "July","August","September","October","November","December"]
        bulan_id = ["Januari","Februari","Maret","April","Mei","Juni",
                    "Juli","Agustus","September","Oktober","November","Desember"]
        for en, id_ in zip(bulan_en, bulan_id):
            tgl_invoice = tgl_invoice.replace(en, id_)

        for po_no, qty, harga in baris_po:
            if qty <= 0:
                continue

            # MULAI DARI BARIS 4, bukan 2.
            # Baris 1 = header, baris 2-3 = celah kosong yang memang dibiarkan. Sheet PO Detail
            # hanya membaca Pengiriman!$C$4:$C$501 -- apa pun yang ditulis di baris 2-3 TIDAK
            # TERLIHAT olehnya. Kode lama mulai memindai dari baris 2, jadi invoice 089 mendarat
            # di baris 2 dan hilang dari laporan. Baris kosong di tengah (bekas invoice hantu yang
            # dihapus) juga dilewati: cari baris kosong di PALING BAWAH, jangan isi lubang.
            r = 4
            terakhir = 3
            while r <= ws.max_row:
                if ws.cell(row=r, column=5).value not in (None, ""):
                    terakhir = r
                r += 1
            r = terakhir + 1

            po_val = "PO-" + str(po_no)   # WAJIB pakai awalan -- lihat penjelasan di atas

            data = [inv_date, tgl_invoice, po_val, site, inv_no, no_bap, qty, harga]
            for k, val in enumerate(data, 1):
                c = ws.cell(row=r, column=k, value=val)
                c.alignment = Alignment(horizontal="center" if k != 5 else "left")
                if k in (7, 8):
                    c.number_format = "#,##0"

            ws.cell(row=r, column=9).value  = '=IF(G%d="","",G%d*H%d*11/12)' % (r, r, r)
            ws.cell(row=r, column=9).number_format = "#,##0"
            ws.cell(row=r, column=10).value = '=IF(I%d="","",I%d*12%%)' % (r, r)
            ws.cell(row=r, column=10).number_format = "#,##0"
            ws.cell(row=r, column=11).value = '=IF(G%d="","",G%d*H%d+J%d)' % (r, r, r, r)
            ws.cell(row=r, column=11).number_format = "#,##0"
            ws.cell(row=r, column=12).value = '=IF(E%d="","",SUMIF(E:E,E%d,K:K))' % (r, r)
            ws.cell(row=r, column=12).number_format = "#,##0"
            ws.cell(row=r, column=13).value = ""
            ws.cell(row=r, column=14).value = '=IF(E%d="","",IF(M%d="","BELUM","LUNAS"))' % (r, r)
            ws.cell(row=r, column=14).alignment = Alignment(horizontal="center")

            # O / P / Q ditulis sebagai FORMULA, bukan angka mati.
            #
            # Baris buatan owner (mulai baris 8) memakai formula ini, dan formula itulah yang
            # membuat sheet mengurus dirinya sendiri: ia sudah benar untuk invoice yang menempati
            # BEBERAPA baris (Q hanya terisi di baris pertama tiap pasangan PO+invoice, sehingga
            # PO Detail tidak menghitung satu invoice dua kali). Kode lama menulis angka mati yang
            # dihitung dari baris di atasnya saja -- begitu ada baris kosong di tengah, angkanya
            # salah dan PO Detail memilih baris yang keliru. Menyerahkannya ke Excel jauh lebih aman
            # daripada meniru logikanya di Python.
            ws.cell(row=r, column=15).value = (
                '=IF(E%d="","",COUNTIFS($C$4:C%d,$C%d,$E$4:E%d,$E%d))' % (r, r, r, r, r))
            ws.cell(row=r, column=16).value = '=IF(E%d="","",E%d&"_"&O%d)' % (r, r, r)
            ws.cell(row=r, column=17).value = (
                '=IF(C%d="","",IF(COUNTIFS($C$4:C%d,$C%d,$E$4:E%d,$E%d)=1,COUNTIF($C$4:C%d,$C%d),""))'
                % (r, r, r, r, r, r, r))

        wb.save(EXCEL)

        try:
            if not config.SMB_AKTIF:
                raise RuntimeError("SMB dimatikan (sandbox) -- Excel TIDAK disalin ke PC")
            subprocess.run(["sudo", "cp", EXCEL, SMB], check=True)
            print("  Excel updated & synced: Inv %s (%d baris)" % (inv_no, len(baris_po)))
        except Exception as e2:
            print("  Excel saved locally, sync gagal: %s" % e2)

    except Exception as e:
        print("  Excel update gagal: %s" % e)

def main():
    try:
        with open(INPUT_FILE) as f:
            data = json.load(f)
    except Exception as e:
        print(json.dumps({"status":"error","message":f"Gagal baca input: {e}"}))
        sys.exit(1)
    site     = data.get("site","")
    qty_kg   = float(data.get("qty_kg",0))
    no_bap   = data.get("no_bap","")
    bap_items = data.get("items", [])
    inv_date = data.get("inv_date","")
    if not site or not qty_kg:
        print(json.dumps({"status":"error","message":"Site dan QTY wajib diisi"}))
        sys.exit(1)
    po1, _po2 = get_po(site)
    if not po1:
        print(json.dumps({"status":"error","message":f"Tidak ada PO aktif untuk site {site}"}))
        sys.exit(1)
    # Ambil customer dari PO tracker (pola sama dgn bap_to_invoice_kks.py,
    # 31 Jul 2026 -- owner: "desain DKP dan KKS itu 1 dan baku, yang berbeda
    # hanya isinya saja, itupun admin dan owner yang isi" -- customer/alamat
    # diisi admin/owner SEKALI saat PO didaftarkan (form Tambah PO / OCR PO),
    # BUKAN diketik ulang tiap kali generate invoice. data.get("customer")
    # tetap dihormati sbg override eksplisit kalau ada, demi kompatibilitas
    # pemanggilan lama/manual.
    customer = data.get("customer") or po1.get("customer","PT.Itci Hutani Manunggal")
    # Aturan owner 15 Sep 2026: alamat customer WAJIB ada di PO (purchase_orders.cust_addr).
    # Tidak ada lagi alamat default diam-diam -- dulu default ini (alamat ITCI) ikut
    # tercetak di invoice Adindo (Inv 094-101) tanpa ada yang sadar.
    cust_addr = data.get("cust_addr") or po1.get("cust_addr")
    if not cust_addr:
        print(json.dumps({"status":"error","message":
            f"PO {po1.get('po_no')} ({site}) belum punya alamat customer. "
            f"Isi alamat + NPWP di data PO dulu (form Edit PO), baru invoice bisa dibuat."}))
        sys.exit(1)
    po_list = get_po_list(site)
    inv_no, next_no = next_inv_no(site, inv_date)

    # Satu jalur untuk SEMUA kasus (1 BAP maupun banyak BAP): alokasi_po memecah
    # QTY ke PO-PO aktif berurutan, dan MENOLAK kalau tidak cukup.
    qty_list = [float(b["qty_kg"]) for b in bap_items] if bap_items else [qty_kg]
    try:
        items, po_splits, order_ref = alokasi_po(
            qty_list, po_list, "total_kg", "used_kg", "rp_kg")
    except ValueError as e:
        print(json.dumps({"status":"error","message":str(e)}))
        sys.exit(1)
    no_po = order_ref
    stdout, stderr, rc = patch_and_run(inv_no, inv_date, no_bap, site, no_po, customer, cust_addr, items, po_splits)

    # BUG BESAR (ditemukan 14 Juli 2026 lewat uji nyata owner):
    # Dulu baris ini HANYA memeriksa stderr. Padahal invoice_dkp.py / invoice_kks.py
    # melaporkan kegagalan lewat STDOUT (json {"status":"error"}) + EXIT CODE 1,
    # dengan stderr KOSONG. Akibatnya kegagalan dianggap SUKSES: counter file maju,
    # Telegram membalas "Invoice berhasil!" lengkap dengan Grand Total yang dihitung
    # SENDIRI di sini (bukan dari script), padahal PDF tidak pernah jadi dan seluruh
    # transaksi DB sudah di-rollback. Nomor invoice jadi hangus (089 kosong).
    # Sekarang: EXIT CODE adalah hakim utama. Pesan gagal diambil dari stdout script.
    gagal = (rc != 0) or (stderr and "Error" in stderr)
    if gagal:
        pesan = ""
        for baris in (stdout or "").strip().split("\n"):
            b = baris.strip()
            if b.startswith("{"):
                try:
                    j = json.loads(b)
                    if j.get("status") == "error":
                        pesan = j.get("message", "")
                except Exception:
                    pass
        if not pesan:
            pesan = (stderr or stdout or "penyebab tidak diketahui").strip()[:500]
        print(json.dumps({"status":"error","message": pesan}))
        sys.exit(1)
    with open(INV_NO_FILE,"w") as f:
        f.write(str(next_no).zfill(3))
    sub_total = sum(i[2]*i[3] for i in items)
    dpp   = sub_total*11/12
    vat   = dpp*0.12
    grand = sub_total+vat
    safe  = inv_no.replace("/","_").replace(" ","_")
    pdf_path = os.path.join(OUTPUT_DIR, f"Inv_{safe}.pdf")
    result = {
        "status":"success","inv_no":inv_no,"site":site,
        "no_bap":no_bap,"no_po":order_ref,"qty_kg":qty_kg,
        "sub_total":sub_total,"grand_total":grand,"pdf_path":pdf_path,
        "items":[{"no":i[0],"desc":i[1],"qty":i[2],"harga":i[3]} for i in items]
    }
    print(json.dumps(result, ensure_ascii=False))
    # Satu baris Excel per PO -- cerminan invoice_items di Postgres.
    # po_splits = [(po_no, qty)] dan items = [(no, desc, qty, harga)] sejajar urutannya.
    #
    # Dibungkus try: Excel adalah catatan SEKUNDER (Postgres yang jadi sumber kebenaran, I5).
    # Invoice sudah terbit dan sudah di-commit di atas; kalau penulisan Excel bermasalah, itu
    # TIDAK boleh membuat script keluar dengan kode gagal -- n8n akan melaporkan invoice yang
    # sebenarnya BERHASIL sebagai GAGAL, dan owner akan mengira tidak ada apa-apa yang terjadi.
    try:
        baris_po = [(po_splits[k][0], items[k][2], items[k][3]) for k in range(len(items))]
        update_excel_log(inv_no, site, no_bap, baris_po, inv_date)
    except Exception as e:
        print("  PERINGATAN: invoice SUDAH terbit, tapi baris Excel gagal ditulis: %s" % e)

if __name__ == "__main__":
    main()
