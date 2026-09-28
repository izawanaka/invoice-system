#!/usr/bin/env python3
"""Backfill app_bap_nota.nopol (28 Sep 2026): OCR ulang berkas asli nota yang
nopol-nya masih NULL, HANYA isi kolom nopol + tambah kunci "nopol" di ocr_json.
Tidak menyentuh qty/no_bap/site/dipakai_invoice. Dijalankan di dalam container
invoice-api (punya ocr_doc, kunci Anthropic, INVOICE_DATA).

  python3 backfill_nopol.py            -> dry-run (cetak saja, tidak UPDATE)
  python3 backfill_nopol.py --tulis    -> UPDATE
"""
import json
import os
import sys

sys.path[:0] = ["/app/webapp", "/app"]
import settings  # noqa: F401,E402
import bap_arsip  # noqa: E402
import db_helper  # noqa: E402
import ocr_doc  # noqa: E402

TULIS = "--tulis" in sys.argv
conn = db_helper.get_conn()
cur = conn.cursor()
cur.execute("SELECT id, no_bap, original_filename, original_path FROM app_bap_nota "
            "WHERE nopol IS NULL AND jenis = 'BAP' ORDER BY id")
rows = cur.fetchall()
print(f"nota tanpa nopol: {len(rows)} (mode {'TULIS' if TULIS else 'DRY-RUN'})")
n_isi = n_kosong = n_gagal = 0
for nid, no_bap, fname, rel in rows:
    path = bap_arsip.jalur(rel)
    try:
        with open(path, "rb") as f:
            data = f.read()
        ocr = ocr_doc.baca_dokumen(ocr_doc.bagian_dari_berkas(fname, data))
        if isinstance(ocr, list):
            ocr = next((e for e in ocr if isinstance(e, dict) and (e.get("nopol") or "").strip()), ocr[0] if ocr else {})
        nopol = str((ocr or {}).get("nopol") or "").strip()[:100]
    except Exception as e:  # noqa: BLE001
        n_gagal += 1
        print(f"  #{nid} {no_bap or '(tanpa nomor)'}: GAGAL {str(e)[:120]}")
        continue
    if nopol:
        n_isi += 1
        print(f"  #{nid} {no_bap or '(tanpa nomor)'}: nopol = {nopol}")
        if TULIS:
            cur.execute("UPDATE app_bap_nota SET nopol = %s, "
                        "ocr_json = coalesce(ocr_json, '{}'::jsonb) || %s::jsonb "
                        "WHERE id = %s AND nopol IS NULL",
                        (nopol, json.dumps({"nopol": nopol}), nid))
    else:
        n_kosong += 1
        print(f"  #{nid} {no_bap or '(tanpa nomor)'}: plat tidak terbaca (dibiarkan NULL)")
if TULIS:
    conn.commit()
cur.execute("SELECT count(*), count(nopol) FROM app_bap_nota WHERE jenis='BAP'")
tot, ada = cur.fetchone()
print(f"ringkas: terisi={n_isi} kosong={n_kosong} gagal={n_gagal}; di DB nopol terisi {ada}/{tot}")
print("BACKFILL_OK")
