#!/usr/bin/env python3
"""Dump READ-ONLY isi database ke satu file JSON (aman, hanya SELECT)."""
import sys, json, datetime
from decimal import Decimal
import db_helper

TABLES = ["invoices", "invoice_items", "purchase_orders", "bap"]


def _jsonable(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else str(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


def rows_as_dicts(cur):
    cols = [c[0] for c in cur.description]
    return [{c: _jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def main(argv):
    seqs = [int(a) for a in argv if a.isdigit()]
    conn = db_helper.get_conn()
    cur = conn.cursor()
    out = {"exported_at": datetime.datetime.now().isoformat(), "tables": {}}
    for t in TABLES:
        try:
            if t == "invoices" and seqs:
                cur.execute("SELECT * FROM invoices WHERE seq_no = ANY(%s) ORDER BY badan_usaha_id, seq_no", (seqs,))
            elif t == "invoice_items" and seqs:
                cur.execute("SELECT ii.* FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id WHERE i.seq_no = ANY(%s) ORDER BY ii.invoice_id, ii.urutan", (seqs,))
            elif t == "invoices":
                cur.execute("SELECT * FROM invoices ORDER BY badan_usaha_id, seq_no")
            elif t == "invoice_items":
                cur.execute("SELECT * FROM invoice_items ORDER BY invoice_id, urutan")
            else:
                cur.execute("SELECT * FROM %s ORDER BY 1" % t)
            out["tables"][t] = rows_as_dicts(cur)
            print("  %-16s : %d baris" % (t, len(out["tables"][t])))
        except Exception as e:
            conn.rollback()
            out["tables"][t] = {"error": str(e)}
            print("  %-16s : GAGAL (%s)" % (t, e))
    cur.close(); conn.close()
    with open("invoices_export.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("OK -> invoices_export.json")


if __name__ == "__main__":
    main(sys.argv[1:])
