#!/usr/bin/env python3
"""Test pemetaan PT->site (pt_site.py). Murni, tanpa DB/jaringan."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pt_site

pt_site.MAP_FILE = "/tmp/test_pt_site_map.json"
if os.path.exists(pt_site.MAP_FILE):
    os.remove(pt_site.MAP_FILE)

lulus, gagal = [], []
def cek(nama, kondisi, detail=""):
    (lulus if kondisi else gagal).append(nama)
    print(f"  {'PASS' if kondisi else 'FAIL'}: {nama}{'' if kondisi else '  -- ' + detail}")

print("[Normalisasi]")
cek("norm titik & kapital sama", pt_site.norm_pt("PT. Mahakam Persada Sakti") == pt_site.norm_pt("pt mahakam persada sakti"))

print("\n[Resolve site dari PT]")
s, st = pt_site.resolve_site("PT Mahakam Persada Sakti", "Senyiur")
cek("Mahakam -> MPS (autofill, koreksi tebakan)", (s, st) == ("MPS", "autofill"), f"{s}/{st}")
s, st = pt_site.resolve_site("PT. Permata Borneo Abadi", "")
cek("Permata -> Senyiur (autofill)", (s, st) == ("Senyiur", "autofill"), f"{s}/{st}")
s, st = pt_site.resolve_site("PT Itci Hutani Manunggal", "Jembayan")
cek("multi-site: tebakan valid dipertahankan", (s, st) == ("Jembayan", "kept"), f"{s}/{st}")
s, st = pt_site.resolve_site("PT Itci Hutani Manunggal", "Senyiur")
cek("multi-site: tebakan tak valid -> ask", (s, st) == ("", "ask"), f"{s}/{st}")
s, st = pt_site.resolve_site("PT Belum Pernah Ada", "Jembayan")
cek("PT asing -> ask (tak menebak)", (s, st) == ("", "ask"), f"{s}/{st}")

print("\n[Ingat permanen]")
pt_site.remember("PT Belum Pernah Ada", "Jembayan")
s, st = pt_site.resolve_site("PT Belum Pernah Ada", "")
cek("setelah remember -> autofill", (s, st) == ("Jembayan", "autofill"), f"{s}/{st}")
pt_site.remember("PT Belum Pernah Ada", "Jembayan")
cek("remember idempoten", pt_site.sites_for("PT Belum Pernah Ada") == ["Jembayan"], str(pt_site.sites_for("PT Belum Pernah Ada")))

if os.path.exists(pt_site.MAP_FILE):
    os.remove(pt_site.MAP_FILE)

print("\n" + "="*50)
print(f"HASIL test_pt_site: {len(lulus)} PASS, {len(gagal)} FAIL")
if gagal:
    print("GAGAL: " + ", ".join(gagal)); sys.exit(1)
print("SEMUA LOLOS.")
