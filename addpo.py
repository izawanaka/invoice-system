#!/usr/bin/env python3
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_helper
import os
import config

STATE_FILE   = config.d("addpo_state.json")
PO_FILE      = config.d("po_tracker.json")
PO_FILE_KKS  = config.d("po_tracker_kks.json")
INPUT_FILE   = config.d("addpo_input.txt")

# Site -> (badan_usaha_id, satuan, label_qty)
SITE_INFO = {
    "Suring":   (4, "kg", "KG"),
    "Jembayan": (4, "kg", "KG"),
    "Sebakis":  (4, "kg", "KG"),
    "Sesayap":  (4, "kg", "KG"),
    "Senyiur":  (5, "m3", "M3"),   # CV. KKS
    "MPS":      (5, "m3", "M3"),   # CV. KKS -- PT Mahakam Persada Sakti, site baru 15 Juli 2026
}
SITES    = list(SITE_INFO.keys())
SITE_MAP = {str(i+1): s for i, s in enumerate(SITES)}

FIELDS = ["po_no", "site", "customer", "total_qty", "harga"]
FIELD_LABEL = {
    "po_no":     "Nomor PO",
    "site":      "Site",
    "customer":  "Nama Customer",
    "total_qty": "Total QTY",
    "harga":     "Harga per satuan",
}
# Sinonim label yang diterima dari pesan user (lowercase, tanpa spasi)
ALIASES = {
    "po": "po_no", "nopo": "po_no", "nomorpo": "po_no", "po_no": "po_no",
    "site": "site", "lokasi": "site",
    "customer": "customer", "cust": "customer", "pelanggan": "customer",
    "totalkg": "total_qty", "totalm3": "total_qty", "total": "total_qty",
    "qty": "total_qty", "totalqty": "total_qty", "kg": "total_qty", "m3": "total_qty",
    "rpkg": "harga", "rp/kg": "harga", "rpm3": "harga", "rp/m3": "harga",
    "harga": "harga", "hargasatuan": "harga", "rp": "harga",
}


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"step": "idle", "data": {}}


def write_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def norm_site(v):
    if not v:
        return None
    v = str(v).strip()
    if v in SITE_MAP:
        return SITE_MAP[v]
    for s in SITES:
        if s.lower() == v.lower():
            return s
    return None


def parse_number(v):
    try:
        n = float(str(v).replace(",", "").replace(".", "").strip()
                  if str(v).count(".") > 1 else str(v).replace(",", "").strip())
        return n if n > 0 else None
    except Exception:
        return None


def parse_labeled(text):
    """Ambil field dari pesan berlabel, contoh:
         /addpo
         PO: 4500270001
         Site: Jembayan
         Customer: PT Ichi Hutani Manunggal
         Total KG: 140000
         Rp/Kg: 3200
       Urutan bebas. Baris tanpa ':' diabaikan."""
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        raw_key, raw_val = line.split(":", 1)
        key = raw_key.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        key = key.lstrip("/")
        val = raw_val.strip()
        if not val:
            continue
        field = ALIASES.get(key)
        if not field:
            continue
        if field == "site":
            s = norm_site(val)
            if s:
                data["site"] = s
        elif field in ("total_qty", "harga"):
            n = parse_number(val)
            if n is not None:
                data[field] = n
        else:
            data[field] = val
    return data


def missing_fields(data):
    return [f for f in FIELDS if f not in data or data[f] in (None, "")]


def ask_for(field, data):
    if field == "po_no":
        return "Masukkan Nomor PO:\n(contoh: 4500270001)"
    if field == "site":
        opts = "\n".join(f"{i+1}. {s}" for i, s in enumerate(SITES))
        return f"Pilih Site:\n{opts}\n\nKetik nama atau angka 1-{len(SITES)}"
    if field == "customer":
        return "Masukkan Nama Customer:"
    unit = SITE_INFO.get(data.get("site", ""), (4, "kg", "KG"))[2]
    if field == "total_qty":
        contoh = "132500" if unit == "KG" else "730"
        return f"Masukkan Total {unit} PO:\n(contoh: {contoh})"
    if field == "harga":
        contoh = "3150" if unit == "KG" else "758700"
        return f"Masukkan Rp/{unit}:\n(contoh: {contoh})"
    return f"Masukkan {FIELD_LABEL.get(field, field)}:"


def summary(data):
    bu_id, satuan, unit = SITE_INFO[data["site"]]
    badan = "CV. Kreasi Karya Sukses" if bu_id == 5 else "PT. Deliandra Karya Pratama"
    return (
        "Konfirmasi PO Baru\n\n"
        f"Badan Usaha : {badan}\n"
        f"No PO       : {data['po_no']}\n"
        f"Site        : {data['site']}\n"
        f"Customer    : {data['customer']}\n"
        f"Total {unit:<4}  : {data['total_qty']:,.0f} {unit}\n"
        f"Rp/{unit:<6}  : Rp{data['harga']:,.0f}\n\n"
        "Ketik YA untuk simpan atau BATAL untuk membatalkan"
    )


def save_po(data):
    """Simpan PO ke Postgres (SUMBER KEBENARAN, lihat DESIGN.md I5), lalu regenerate
    po_tracker*.json sebagai turunan. Kalau DB gagal -> raise, PO TIDAK tersimpan
    di mana pun (tidak boleh ada PO yang cuma ada di JSON tapi tidak di DB, karena
    invoice generator cek PO di DB dan akan menolak.)"""
    bu_id, satuan, unit = SITE_INFO[data["site"]]
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM purchase_orders WHERE po_no=%s AND badan_usaha_id=%s",
            (data["po_no"], bu_id),
        )
        if cur.fetchone():
            raise ValueError(f"PO {data['po_no']} sudah ada di database")
        cur.execute(
            "INSERT INTO purchase_orders "
            "(badan_usaha_id, po_no, site, customer, total_qty, used_qty, satuan, harga_satuan, status, tgl_masuk) "
            "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, 'aktif', CURRENT_DATE)",
            (bu_id, data["po_no"], data["site"], data["customer"],
             data["total_qty"], satuan, data["harga"]),
        )
        conn.commit()
        try:
            import pt_site
            pt_site.remember(data.get("customer", ""), data["site"])
        except Exception:
            pass  # memori PT->site bukan kritikal
        if bu_id == 5:
            db_helper.refresh_po_tracker_json(conn, 5, PO_FILE_KKS, "total_m3", "used_m3", "rp_m3", "m3")
        else:
            db_helper.refresh_po_tracker_json(conn, 4, PO_FILE, "total_kg", "used_kg", "rp_kg", "kg")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return bu_id, unit


def handle_addpo(text, state):
    """Alur /addpo: terima format satu-pesan berlabel; hanya tanya field yang kosong."""
    data = parse_labeled(text)
    miss = missing_fields(data)
    if not miss:
        write_state({"step": "confirm", "data": data})
        return summary(data)
    write_state({"step": f"wait_{miss[0]}", "data": data})
    header = "Tambah PO Baru\n\n"
    if data:
        terisi = ", ".join(f"{FIELD_LABEL[k]}: {data[k]}" for k in FIELDS if k in data)
        header = f"Tambah PO Baru\n\nSudah terbaca -> {terisi}\n\n"
    return header + ask_for(miss[0], data)


def handle_wait_field(field, text, state):
    data = state.get("data", {})
    if field == "site":
        s = norm_site(text)
        if not s:
            return "Site tidak valid. Pilih: " + ", ".join(SITES)
        data["site"] = s
    elif field in ("total_qty", "harga"):
        n = parse_number(text)
        if n is None:
            return f"{FIELD_LABEL[field]} tidak valid. Masukkan angka, contoh: 132500"
        data[field] = n
    else:
        data[field] = text.strip()

    miss = missing_fields(data)
    if not miss:
        write_state({"step": "confirm", "data": data})
        return summary(data)
    write_state({"step": f"wait_{miss[0]}", "data": data})
    return ask_for(miss[0], data)


def process(text):
    text = text.strip()
    state = read_state()
    step  = state.get("step", "idle")
    data  = state.get("data", {})
    reply = ""
    action = "reply"

    first = text.split()[0].lower() if text.split() else ""

    if first == "/addpo":
        reply = handle_addpo(text, state)

    elif step.startswith("wait_"):
        field = step[len("wait_"):]
        if field in FIELDS:
            reply = handle_wait_field(field, text, state)
        else:
            write_state({"step": "idle", "data": {}})
            reply = "Sesi tidak dikenali, dibatalkan. Ketik /addpo untuk mulai lagi."

    elif step == "confirm":
        if text.upper() == "YA":
            try:
                bu_id, unit = save_po(data)
                write_state({"step": "idle", "data": {}})
                reply = (
                    f"PO {data['po_no']} berhasil disimpan!\n\n"
                    f"Site      : {data['site']}\n"
                    f"Total {unit:<4}: {data['total_qty']:,.0f} {unit}\n"
                    f"Rp/{unit:<6}: Rp{data['harga']:,.0f}\n\n"
                    "Tersimpan di database (bisnis-db) dan PO tracker."
                )
            except Exception as e:
                write_state({"step": "idle", "data": {}})
                reply = f"GAGAL simpan PO: {e}\n\nPO TIDAK tersimpan. Coba lagi dengan /addpo"
        elif text.upper() == "BATAL":
            write_state({"step": "idle", "data": {}})
            reply = "Dibatalkan."
        else:
            reply = "Ketik YA untuk simpan atau BATAL untuk membatalkan"

    elif text.lower() == '/syncpo':
        try:
            lines = ["Saldo PO (dari database):\n"]
            conn = db_helper.get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT badan_usaha_id, po_no, site, total_qty, used_qty, satuan "
                "FROM purchase_orders WHERE status='aktif' ORDER BY badan_usaha_id, po_no"
            )
            for bu_id, po_no, site, total, used, satuan in cur.fetchall():
                sisa = float(total) - float(used)
                pct  = sisa / float(total) * 100 if float(total) else 0
                tag  = "KKS" if bu_id == 5 else "DKP"
                lines.append(f"[{tag}] {site} {po_no[-4:]}: {sisa:,.0f} {satuan.upper()} ({pct:.0f}%)")
            cur.close()
            # regenerate file turunan dari DB
            db_helper.refresh_po_tracker_json(conn, 4, PO_FILE, "total_kg", "used_kg", "rp_kg", "kg")
            db_helper.refresh_po_tracker_json(conn, 5, PO_FILE_KKS, "total_m3", "used_m3", "rp_m3", "m3")
            conn.close()
            reply = "\n".join(lines)
        except Exception as e:
            reply = "Sync gagal: " + str(e)
        write_state({"step": "idle", "data": {}})

    elif text.upper() == 'TAMBAH':
        try:
            with open(config.d("multi_bap_state.json")) as f2:
                st = json.load(f2)
        except Exception:
            st = {"active": False}
        if not st.get("active"):
            reply = "Tidak ada sesi BAP aktif. Kirim PDF BAP terlebih dahulu."
        else:
            bap_nos = ", ".join(b["no_bap"] for b in st.get("bap_list", []))
            total   = sum(b.get("qty_kg", 0) for b in st.get("bap_list", []))
            site_val = st.get('site', '')
            reply = f"Sesi BAP aktif:\nSite: {site_val}\nBAP: {bap_nos}\nTotal: {total:,.0f} KG\n\nKirim PDF BAP berikutnya atau ketik SELESAI"
        write_state({"step": "idle", "data": {}})

    elif text.upper() == 'SELESAI':
        import subprocess
        try:
            with open(config.d("multi_bap_state.json")) as f2:
                st = json.load(f2)
        except Exception:
            st = {"active": False}
        if not st.get("active") or not st.get("bap_list"):
            reply = "Tidak ada sesi BAP aktif."
        else:
            site_val  = st["site"]
            bap_nos   = ", ".join(b["no_bap"] for b in st["bap_list"])
            inv_date  = st["inv_date"]

            if site_val == "Senyiur":
                total_qty = sum(b.get("qty_m3", b.get("qty_kg", 0)) for b in st["bap_list"])
                items = [{"no_bap": b["no_bap"], "qty_m3": b.get("qty_m3", 0)} for b in st["bap_list"]]
                bap_input = {"site": site_val, "qty_m3": total_qty,
                             "no_bap": bap_nos, "inv_date": inv_date, "items": items}
                with open(config.d("bap_input_kks.json"), "w") as f2:
                    json.dump(bap_input, f2, ensure_ascii=False)
                r2 = subprocess.run(["python3", config.k("bap_to_invoice_kks.py")],
                                    capture_output=True, text=True)
                unit_label = "M3"
                qty_key = "qty_m3"
            else:
                total_qty = sum(b["qty_kg"] for b in st["bap_list"])
                bap_input = {"site": site_val, "qty_kg": total_qty,
                             "no_bap": bap_nos, "inv_date": inv_date}
                with open(config.d("bap_input.json"), "w") as f2:
                    json.dump(bap_input, f2, ensure_ascii=False)
                r2 = subprocess.run(["python3", config.k("bap_to_invoice.py")],
                                    capture_output=True, text=True)
                unit_label = "KG"
                qty_key = "qty_kg"

            stdout = r2.stdout.strip()
            json_line = next((l for l in stdout.split("\n") if l.startswith("{")), "{}")
            try:
                res = json.loads(json_line)
                if res.get("status") == "success":
                    inv_no  = res.get('inv_no', '')
                    site_r  = res.get('site', '')
                    qty_r   = res.get(qty_key, res.get('qty_kg', res.get('qty_m3', 0)))
                    grand_r = res.get('grand_total', 0)
                    reply = (f"Invoice berhasil!\n\nNo Invoice: {inv_no}\nSite: {site_r}\n"
                             f"QTY: {qty_r:,.0f} {unit_label}\nGrand Total: Rp{grand_r:,.0f}")
                else:
                    reply = f"Gagal: {res.get('message', 'error')}"
            except Exception:
                reply = f"Error: {stdout[:200]}"
            with open(config.d("multi_bap_state.json"), "w") as f2:
                json.dump({"active": False, "bap_list": [], "site": "", "inv_date": ""}, f2)
        write_state({"step": "idle", "data": {}})

    else:
        action = "ignore"

    return json.dumps({"reply": reply, "action": action}, ensure_ascii=False)


if __name__ == "__main__":
    try:
        with open(INPUT_FILE) as f:
            text = f.read().strip()
    except Exception:
        text = sys.argv[1] if len(sys.argv) > 1 else ""
    print(process(text))
