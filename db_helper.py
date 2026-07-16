"""
Helper koneksi Postgres (bisnis-db) untuk sistem invoice KKS/DKP.
Satu-satunya tempat baca kredensial DB -- jangan hardcode di file lain.
"""
import psycopg2
import os
import config

CRED_FILE = config.d(".bisnis_db_credentials")


def _read_creds():
    creds = {}
    with open(CRED_FILE) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line:
                k, v = line.split("=", 1)
                creds[k] = v
    return creds


def get_conn():
    c = _read_creds()
    conn = psycopg2.connect(
        host=c["DB_HOST"], port=c["DB_PORT"], dbname=c["DB_NAME"],
        user=c["DB_USER"], password=c["DB_PASSWORD"],
    )
    conn.autocommit = False
    return conn


def refresh_po_tracker_json(conn, badan_usaha_id, po_file_path, qty_field, used_field, price_field, unit):
    """
    Tulis ulang po_tracker.json / po_tracker_kks.json dari Postgres (source of truth).
    Dipanggil SETELAH commit sukses -- supaya file lokal selalu jadi cermin akurat dari DB,
    bukan disimpan independen lagi.
    """
    import json
    cur = conn.cursor()
    cur.execute(
        "SELECT po_no, site, customer, total_qty, used_qty, harga_satuan, status, cust_addr, payment_terms "
        "FROM purchase_orders WHERE badan_usaha_id = %s ORDER BY po_no",
        (badan_usaha_id,),
    )
    po_list = []
    for row in cur.fetchall():
        po_no, site, customer, total_qty, used_qty, harga, status, cust_addr, payment_terms = row
        entry = {
            "po_no": po_no,
            "site": site,
            "customer": customer,
            qty_field: float(total_qty),
            used_field: float(used_qty),
            price_field: float(harga) if harga is not None else 0,
            "status": status,
        }
        if cust_addr:
            entry["cust_addr"] = list(cust_addr)
        if payment_terms:
            entry["payment_terms"] = payment_terms
        po_list.append(entry)
    cur.close()
    with open(po_file_path, "w") as f:
        json.dump({"po_list": po_list}, f, indent=2, ensure_ascii=False)
