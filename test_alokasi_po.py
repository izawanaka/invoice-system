#!/usr/bin/env python3
"""Uji aturan alokasi PO (ditetapkan owner 14 Juli 2026).

Fungsi murni -- tanpa database, tanpa jaringan, tanpa menyentuh file apa pun.
Jalankan: python3 test_alokasi_po.py   (harus 0 FAIL)
"""
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bap_to_invoice as dkp
import bap_to_invoice_kks as kks

PASS, FAIL = [], []


def cek(nama, kondisi, detail=""):
    if kondisi:
        PASS.append(nama); print(f"  PASS: {nama}")
    else:
        FAIL.append(nama); print(f"  FAIL: {nama}  -- {detail}")


PO_DKP = [
    {"po_no": "4500259053", "total_kg": 132500, "used_kg": 76171, "rp_kg": 3050},  # sisa 56.329
    {"po_no": "4500264733", "total_kg": 52500,  "used_kg": 0,     "rp_kg": 3100},  # sisa 52.500
]
PO_KKS = [
    {"po_no": "14-0001-12883", "total_m3": 730, "used_m3": 532.33, "rp_m3": 758700},  # sisa 197,67
]

print("[L] Muat di 1 PO -> 1 baris, deskripsi memuat nomor PO itu")
items, splits, ref = dkp.alokasi_po([10000], PO_DKP, "total_kg", "used_kg", "rp_kg")
cek("L: 1 baris item", len(items) == 1, str(items))
cek("L: deskripsi = 'Cocopeat - PO.4500259053'", items[0][1] == "Cocopeat - PO.4500259053", str(items))
cek("L: harga PO pertama dipakai", items[0][3] == 3050, str(items))
cek("L: split hanya PO pertama", splits == [("4500259053", 10000.0)], str(splits))
cek("L: No. PO di kepala invoice = 1 nomor", ref == "4500259053", ref)

print("\n[M] PO pertama habis -> otomatis lanjut ke PO kedua, 2 baris, 2 harga")
items, splits, ref = dkp.alokasi_po([70000], PO_DKP, "total_kg", "used_kg", "rp_kg")
cek("M: jadi 2 baris item", len(items) == 2, str(items))
cek("M: baris 1 = sisa PO lama (56.329) @3050",
    items[0][1] == "Cocopeat - PO.4500259053" and items[0][2] == 56329 and items[0][3] == 3050, str(items))
cek("M: baris 2 = kelebihan (13.671) @3100 di PO baru",
    items[1][1] == "Cocopeat - PO.4500264733" and items[1][2] == 13671 and items[1][3] == 3100, str(items))
cek("M: total qty utuh", items[0][2] + items[1][2] == 70000, str(items))
cek("M: saldo tiap PO didebit terpisah (I7)",
    splits == [("4500259053", 56329.0), ("4500264733", 13671.0)], str(splits))
cek("M: kepala invoice memuat 2 nomor PO", ref == "4500259053 / 4500264733", ref)

print("\n[N] QTY melebihi SELURUH PO aktif -> DITOLAK (tidak ada invoice)")
try:
    dkp.alokasi_po([200000], PO_DKP, "total_kg", "used_kg", "rp_kg")
    cek("N: harus menolak", False, "malah lolos")
except ValueError as e:
    cek("N: ditolak dengan ValueError", True)
    cek("N: pesan menyebut sisa seluruh PO", "melebihi sisa seluruh PO aktif" in str(e), str(e))
    cek("N: pesan menuntun daftarkan PO baru", "Daftarkan PO baru" in str(e), str(e))

print("\n[O] Tidak ada PO aktif sama sekali -> DITOLAK")
try:
    dkp.alokasi_po([100], [], "total_kg", "used_kg", "rp_kg")
    cek("O: harus menolak", False, "malah lolos")
except ValueError as e:
    cek("O: ditolak", "Tidak ada PO aktif" in str(e), str(e))

print("\n[P] Multi-BAP juga ikut aturan yang sama (dulu SELALU dibebankan ke PO pertama)")
items, splits, ref = dkp.alokasi_po([50000, 20000], PO_DKP, "total_kg", "used_kg", "rp_kg")
cek("P: total 70.000 tetap terpecah ke 2 PO", len(splits) == 2, str(splits))
cek("P: PO lama dihabiskan persis", splits[0] == ("4500259053", 56329.0), str(splits))
cek("P: sisanya ke PO baru", splits[1] == ("4500264733", 13671.0), str(splits))
cek("P: jumlah qty semua baris = 70.000", sum(i[2] for i in items) == 70000, str(items))

print("\n[Q] Multi-BAP melebihi PO -> DITOLAK (dulu: invoice terbit, PO jadi minus)")
try:
    dkp.alokasi_po([60000, 60000], PO_DKP, "total_kg", "used_kg", "rp_kg")
    cek("Q: harus menolak", False, "malah lolos")
except ValueError:
    cek("Q: ditolak", True)

print("\n[R] KKS / Senyiur (m3, desimal)")
items, splits, ref = kks.alokasi_po([100.5], PO_KKS, "total_m3", "used_m3", "rp_m3")
cek("R: deskripsi memuat nomor PO KKS", items[0][1] == "Cocopeat - PO.14-0001-12883", str(items))
cek("R: qty desimal utuh", items[0][2] == 100.5, str(items))
cek("R: harga m3 dipakai", items[0][3] == 758700, str(items))
try:
    kks.alokasi_po([250], PO_KKS, "total_m3", "used_m3", "rp_m3")
    cek("R: 250 m3 > sisa 197,67 harus ditolak", False, "malah lolos")
except ValueError:
    cek("R: 250 m3 > sisa 197,67 -> ditolak", True)

print("\n[S] Batas persis (pas habis) TIDAK boleh ditolak")
items, splits, ref = kks.alokasi_po([197.67], PO_KKS, "total_m3", "used_m3", "rp_m3")
cek("S: qty == sisa persis -> diterima", len(items) == 1 and items[0][2] == 197.67, str(items))

print("\n" + "=" * 60)
print(f"HASIL: {len(PASS)} PASS, {len(FAIL)} FAIL")
if FAIL:
    print("GAGAL: " + ", ".join(FAIL)); sys.exit(1)
print("SEMUA SKENARIO LOLOS.")
