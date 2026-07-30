#!/usr/bin/env python3
import json, sys, os, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_helper
import os
import config

INPUT_FILE     = config.d("bap_input_kks.json")
PO_FILE        = config.d("po_tracker_kks.json")
INV_NO_FILE    = config.d("last_invoice_no_kks.txt")
OUTPUT_DIR     = config.OUTPUT_DIR_KKS
INVOICE_SCRIPT = config.INVOICE_KKS

BULAN = {1:"I",2:"II",3:"III",4:"IV",5:"V",6:"VI",
         7:"VII",8:"VIII",9:"IX",10:"X",11:"XI",12:"XII"}

def next_inv_no(site, date_str):
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
        _cur.execute("SELECT COALESCE(MAX(seq_no), 0) FROM invoices WHERE badan_usaha_id = 5")
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
            items.append((len(items) + 1, f"Cocopeat - PO.{po_no}", ambil, harga))
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
    cust_addr_str = "[\n"
    for addr in cust_addr:
        cust_addr_str += f'    "{addr}",\n'
    cust_addr_str += "]"
    src = re.sub(r'CUST_ADDR\s*=\s*\[.*?\]', f'CUST_ADDR = {cust_addr_str}', src, flags=re.MULTILINE|re.DOTALL)
    items_str = "[\n"
    for item in items:
        items_str += f"    ({item[0]}, \"{item[1]}\", {item[2]}, {item[3]}),\n"
    items_str += "]"
    src = re.sub(r'^ITEMS\s*=\s*\[.*?\]', f'ITEMS = {items_str}',
                 src, flags=re.MULTILINE|re.DOTALL)
    # Nama file per-lingkungan: sandbox dan produksi TIDAK BOLEH saling menimpa
    tmp = f"/tmp/invoice_kks_run_{config.ENV}.py"
    with open(tmp, "w") as f:
        f.write(src)
    # INVOICE_CODE: beri tahu script salinan di /tmp di mana folder kode berada.
    env = {**os.environ, "INVOICE_CODE": config.BASE}
    result = subprocess.run(["python3", tmp], capture_output=True, text=True, env=env)
    return result.stdout, result.stderr, result.returncode




def update_po_master_detail(wb, ws_pengiriman, no_po, inv_no, qty_m3, grand_total, tgl_invoice):
    from openpyxl.styles import Alignment
    # PO Master: update Used M3
    ws_master = wb["PO Master"]
    for rm in range(2, ws_master.max_row + 2):
        if ws_master.cell(row=rm, column=1).value == no_po:
            cur = ws_master.cell(row=rm, column=6).value or 0
            if isinstance(cur, (int, float)):
                ws_master.cell(row=rm, column=6).value = round(cur + qty_m3, 4)
            break
    # PO Detail: tambah/update baris invoice
    ws_detail = wb["PO Detail"]
    inv_row = None
    next_empty = None
    for rd in range(3, ws_detail.max_row + 2):
        v = ws_detail.cell(row=rd, column=1).value
        if v is None:
            if next_empty is None:
                next_empty = rd
            break
        if str(v).strip() == str(inv_no).strip():
            inv_row = rd
            break
    if inv_row:
        cur_qty = ws_detail.cell(row=inv_row, column=3).value or 0
        cur_total = ws_detail.cell(row=inv_row, column=4).value or 0
        ws_detail.cell(row=inv_row, column=3).value = round(cur_qty + qty_m3, 4)
        ws_detail.cell(row=inv_row, column=4).value = cur_total + grand_total
    else:
        rd_new = next_empty or (ws_detail.max_row + 1)
        ws_detail.cell(row=rd_new, column=1).value = inv_no
        ws_detail.cell(row=rd_new, column=2).value = tgl_invoice
        ws_detail.cell(row=rd_new, column=3).value = qty_m3
        ws_detail.cell(row=rd_new, column=3).number_format = "#,##0.00"
        ws_detail.cell(row=rd_new, column=4).value = grand_total
        ws_detail.cell(row=rd_new, column=4).number_format = "#,##0"
        ws_detail.cell(row=rd_new, column=5).value = None
        ws_detail.cell(row=rd_new, column=6).value = f'=IF(E{rd_new}="","BELUM","LUNAS")'
        ws_detail.cell(row=rd_new, column=6).alignment = Alignment(horizontal="center")

def update_excel_log(inv_no, site, no_bap, baris_po, inv_date):
    """Tulis invoice KKS ke sheet Pengiriman -- SATU BARIS PER PO.

    baris_po = [(po_no, qty_m3, harga), ...]  -- cerminan invoice_items di Postgres.

    CATATAN PENTING -- Excel KKS TIDAK sama dengan Excel DKP:

    - Kolom C di KKS ditulis POLOS ("14-0001-12883"), TANPA awalan "PO-". Itu memang konvensi
      sheet ini. Di DKP awalan itu wajib karena PO Master memakai SUMIF(C:C,"PO-"&A2,...);
      di KKS PO Master memakai ANGKA KETIKAN, bukan formula. Menambahkan awalan "PO-" di sini
      justru akan memutus kecocokan dengan baris-baris lama. Jadi: jangan disamakan.

    - Karena PO Master & PO Detail KKS berisi angka ketikan (bukan formula), sheet ini TIDAK
      menghitung ulang dirinya sendiri. Saldo PO di Excel KKS harus dirawat manual; Postgres
      tetap sumber kebenaran (I5).

    Yang diperbaiki di sini: invoice split dulu dijejalkan ke SATU baris dengan SATU harga
    rata-rata, sehingga formula G*H meleset dari nilai invoice sebenarnya dan kolom C berisi
    "A / B" yang bukan nomor PO manapun. Sekarang tiap PO dapat barisnya sendiri dengan harga
    aslinya. Hari ini KKS baru punya satu PO aktif sehingga split belum pernah terjadi -- ini
    supaya tidak meledak diam-diam saat PO KKS kedua ditambahkan.
    """
    import openpyxl, subprocess
    from openpyxl.styles import Alignment
    from datetime import datetime

    EXCEL = config.EXCEL_KKS
    SMB   = config.SMB_KKS

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

            # Tambahkan di BAWAH baris terakhir yang terisi (data KKS mulai baris 2), jangan
            # mengisi lubang di tengah -- baris kosong bekas hapusan bisa membuat penghitung
            # O/P/Q salah hitung.
            r, terakhir = 2, 1
            while r <= ws.max_row:
                if ws.cell(row=r, column=5).value not in (None, ""):
                    terakhir = r
                r += 1
            r = terakhir + 1

            po_val = str(po_no)   # POLOS -- tanpa awalan "PO-" (lihat penjelasan di atas)

            data = [inv_date, tgl_invoice, po_val, site, inv_no, no_bap, qty, harga]
            for k, val in enumerate(data, 1):
                c = ws.cell(row=r, column=k, value=val)
                c.alignment = Alignment(horizontal="center" if k != 5 else "left")
                if k in (7, 8):
                    c.number_format = "#,##0"

            # KKS TIDAK KENA PPN -- ini bukan salinan DKP.
            #
            # BUG (ditemukan 14 Juli 2026): kode lama memakai formula DKP di sini --
            #   I = G*H*11/12 ; J = I*12%% ; K = G*H + J
            # -- sehingga Excel menambahkan PPN yang TIDAK ADA di invoice KKS. Bandingkan dengan
            # baris ketikan owner (baris 2): I = G*H, J = 0, K = G*H. Database juga tegas:
            # invoice 009 grand_total = 50 x 758.700 = Rp37.935.000, PERSIS sub_total, tanpa PPN.
            # Akibat bug ini tiap invoice KKS di Excel dilebihkan sekitar Rp5 juta.
            ws.cell(row=r, column=9).value  = '=IF(G%d="","",G%d*H%d)' % (r, r, r)
            ws.cell(row=r, column=9).number_format = "#,##0"
            ws.cell(row=r, column=10).value = 0
            ws.cell(row=r, column=10).number_format = "#,##0"
            ws.cell(row=r, column=11).value = '=IF(G%d="","",G%d*H%d)' % (r, r, r)
            ws.cell(row=r, column=11).number_format = "#,##0"
            ws.cell(row=r, column=12).value = '=IF(E%d="","",SUMIF(E:E,E%d,K:K))' % (r, r)
            ws.cell(row=r, column=12).number_format = "#,##0"
            ws.cell(row=r, column=13).value = ""
            ws.cell(row=r, column=14).value = '=IF(E%d="","",IF(M%d="","BELUM","LUNAS"))' % (r, r)
            ws.cell(row=r, column=14).alignment = Alignment(horizontal="center")

            # O/P/Q di KKS memang angka, bukan formula (mengikuti baris-baris lama). Tapi
            # dihitung dari SELURUH sheet, bukan cuma baris di atas r -- kalau ada baris kosong
            # di tengah, cara lama menghasilkan angka yang salah.
            rows_po = [rx for rx in range(2, ws.max_row + 1)
                       if ws.cell(row=rx, column=3).value == po_val]
            ws.cell(row=r, column=15).value = len(rows_po)
            ws.cell(row=r, column=16).value = po_val + "_" + str(len(rows_po))

            # Q hanya di baris PERTAMA invoice ini untuk PO ini -- invoice split menempati
            # beberapa baris dan tidak boleh terhitung dua kali.
            inv_lain, sudah_ada = set(), False
            for rx in rows_po:
                if rx == r:
                    continue
                nilai = ws.cell(row=rx, column=5).value
                if nilai == inv_no:
                    sudah_ada = True
                elif nilai:
                    inv_lain.add(nilai)
            ws.cell(row=r, column=17).value = "" if sudah_ada else len(inv_lain) + 1

        wb.save(EXCEL)

        try:
            if not config.SMB_AKTIF:
                raise RuntimeError("SMB dimatikan (sandbox) -- Excel TIDAK disalin ke PC")
            subprocess.run(["sudo", "cp", EXCEL, SMB], check=True)
            print("  Excel KKS updated & synced: Inv %s (%d baris)" % (inv_no, len(baris_po)))
        except Exception as e2:
            print("  Excel KKS saved locally, sync gagal: %s" % e2)

    except Exception as e:
        print("  Excel KKS update gagal: %s" % e)

def main():
    try:
        with open(INPUT_FILE) as f:
            data = json.load(f)
    except Exception as e:
        print(json.dumps({"status":"error","message":f"Gagal baca input: {e}"}))
        sys.exit(1)
    site     = data.get("site","")
    qty_m3   = float(data.get("qty_m3",0))
    no_bap   = data.get("no_bap","")
    bap_items = data.get("items", [])
    inv_date = data.get("inv_date","")
    if not site or not qty_m3:
        print(json.dumps({"status":"error","message":"Site dan QTY wajib diisi"}))
        sys.exit(1)
    po1, po2 = get_po(site)
    if not po1:
        print(json.dumps({"status":"error","message":f"Tidak ada PO aktif untuk site {site}"}))
        sys.exit(1)
    # Ambil customer dari PO tracker
    customer = po1.get("customer", "PT. Permata Borneo Abadi")
    cust_addr = po1.get("cust_addr", [
        "Jl. Syarifuddin Yoes No. 68A-68B RT.45",
        "Sepinggan Baru Balikpapan Selatan",
        "Kota Balikpapan Kalimantan Timur",
        "02.505.000.6-722.000"])
    inv_no, next_no = next_inv_no(site, inv_date)

    po_list = get_po_list(site)
    qty_list = [float(b["qty_m3"]) for b in bap_items] if bap_items else [qty_m3]
    try:
        items, po_splits, order_ref = alokasi_po(
            qty_list, po_list, "total_m3", "used_m3", "rp_m3")
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
    dpp   = 0
    vat   = 0
    grand = sub_total
    safe  = inv_no.replace("/","_").replace(" ","_")
    pdf_path = os.path.join(OUTPUT_DIR, f"Inv_{safe}.pdf")
    result = {
        "status":"success","inv_no":inv_no,"site":site,
        "no_bap":no_bap,"no_po":order_ref,"qty_m3":qty_m3,
        "sub_total":sub_total,"grand_total":grand,"pdf_path":pdf_path,
        "items":[{"no":i[0],"desc":i[1],"qty":i[2],"harga":i[3]} for i in items]
    }
    print(json.dumps(result, ensure_ascii=False))
    # Satu baris Excel per PO -- cerminan invoice_items di Postgres.
    # Dibungkus try: Excel catatan SEKUNDER (I5). Invoice sudah di-commit; masalah Excel
    # tidak boleh membuat script keluar dengan kode gagal, karena n8n akan melaporkan
    # invoice yang BERHASIL sebagai GAGAL dan owner mengira tidak terjadi apa-apa.
    try:
        baris_po = [(po_splits[k][0], items[k][2], items[k][3]) for k in range(len(items))]
        update_excel_log(inv_no, site, no_bap, baris_po, inv_date)
    except Exception as e:
        print("  PERINGATAN: invoice SUDAH terbit, tapi baris Excel gagal ditulis: %s" % e)

if __name__ == "__main__":
    main()
