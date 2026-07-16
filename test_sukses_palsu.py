#!/usr/bin/env python3
"""Uji: kegagalan HARUS dilaporkan gagal -- tidak boleh jadi 'sukses palsu'.

Latar belakang (14 Juli 2026): bot membalas "Invoice berhasil!" padahal PDF tidak
pernah jadi dan seluruh transaksi DB sudah di-rollback. Penyebabnya bap_to_invoice.py
hanya memeriksa stderr, sementara invoice_dkp.py melaporkan kegagalan lewat STDOUT +
exit code 1 dengan stderr KOSONG.

Test ini mensimulasikan script invoice yang GAGAL dengan pola persis seperti itu.
Tidak menyentuh database, tidak menulis PDF, tidak mengubah counter asli.
"""
import os

import json, os, subprocess, sys, tempfile, shutil

PASS, FAIL = [], []

def cek(nama, kondisi, detail=""):
    (PASS if kondisi else FAIL).append(nama)
    print(f"  {'PASS' if kondisi else 'FAIL'}: {nama}{'' if kondisi else '  -- ' + detail}")


def jalankan_dengan_script_gagal(modul):
    """Jalankan bap_to_invoice(_kks) dengan INVOICE_SCRIPT diganti script tiruan yang
    GAGAL persis seperti invoice_dkp.py: json error ke STDOUT, stderr KOSONG, exit 1."""
    tmp = tempfile.mkdtemp()
    try:
        palsu = os.path.join(tmp, "invoice_palsu.py")
        with open(palsu, "w") as f:
            f.write(
                "import json, sys\n"
                "INV_NO=''\nINV_DATE=''\nNO_BAP=''\nSITE=''\nNO_PO=''\nCUSTOMER=''\n"
                "CUST_ADDR=[]\nPO_SPLITS=[('',0)]\nITEMS=[]\n"
                "print(json.dumps({'status':'error','message':'PDF gagal ditulis (mount mati). Rollback total.'}))\n"
                "sys.exit(1)\n"
            )
        counter = os.path.join(tmp, "counter.txt")
        with open(counter, "w") as f:
            f.write("088")

        kode = (
            f"import sys; sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r});"
            f"import {modul} as m;"
            f"m.INVOICE_SCRIPT = {palsu!r};"
            f"m.INV_NO_FILE = {counter!r};"
            f"m.main()"
        )
        inp = os.path.join(tmp, "bap.json")
        payload = {"site": "Suring", "qty_kg": 1000, "no_bap": "TES/0/0", "inv_date": "7 Juli 2026"} \
            if modul == "bap_to_invoice" else \
            {"site": "Senyiur", "qty_m3": 10, "no_bap": "TES/0/0", "inv_date": "7 Juli 2026"}
        with open(inp, "w") as f:
            json.dump(payload, f)

        kode = kode.replace("m.main()", f"m.INPUT_FILE = {inp!r}; m.main()")
        r = subprocess.run([sys.executable, "-c", kode], capture_output=True, text=True)
        with open(counter) as f:
            counter_akhir = f.read().strip()
        return r, counter_akhir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


for modul, label in [("bap_to_invoice", "DKP"), ("bap_to_invoice_kks", "KKS")]:
    print(f"\n[T-{label}] Script invoice GAGAL (error di stdout, stderr kosong, exit 1)")
    r, counter_akhir = jalankan_dengan_script_gagal(modul)
    out = r.stdout.strip()
    hasil = {}
    for baris in out.split("\n"):
        if baris.strip().startswith("{"):
            try:
                hasil = json.loads(baris)
            except Exception:
                pass
    cek(f"T-{label}: exit code BUKAN 0", r.returncode != 0, f"rc={r.returncode}")
    cek(f"T-{label}: status = error (BUKAN success)", hasil.get("status") == "error", out[:200])
    cek(f"T-{label}: pesan asli script diteruskan",
        "mount" in hasil.get("message", "").lower() or "rollback" in hasil.get("message", "").lower(),
        str(hasil))
    cek(f"T-{label}: counter TIDAK maju (tetap 088)", counter_akhir == "088", f"counter={counter_akhir}")
    cek(f"T-{label}: TIDAK ada kata 'berhasil' di balasan", "success" not in out, out[:200])

print("\n" + "=" * 60)
print(f"HASIL: {len(PASS)} PASS, {len(FAIL)} FAIL")
if FAIL:
    print("GAGAL: " + ", ".join(FAIL)); sys.exit(1)
print("SEMUA SKENARIO LOLOS.")
