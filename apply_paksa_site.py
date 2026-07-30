#!/usr/bin/env python3
"""Menyisipkan paksa_site() ke ocr_doc.py + mengaitkannya di jalur BAP.
Idempotent: kalau paksa_site sudah ada, tidak mengubah apa pun."""
import sys
PATH = sys.argv[1] if len(sys.argv) > 1 else "ocr_doc.py"
src = open(PATH, encoding="utf-8").read()
if "def paksa_site" in src:
    print("SKIP: paksa_site sudah ada -- tidak ada perubahan.")
    sys.exit(0)
anchor1 = "def bangun_teks_addpo(ocr):"
fungsi = '''def paksa_site(caption):
    """Caption boleh MEMAKSA site, mengalahkan tebakan AI -- sama seperti
    paksa_jenis() memaksa jenis dokumen. Jaring pengaman kalau site salah dibaca
    dari foto (mis. 'Jembayan' malah tertebak 'Suring'). Kembalikan nama site
    kanonik dari SITES, atau None kalau caption tidak menyebut site mana pun."""
    c = (caption or "").strip().lower()
    if not c:
        return None
    for s in SITES:
        if s.lower() in c:
            return s
    return None
'''
if anchor1 not in src:
    sys.exit("GAGAL: anchor1 tidak ketemu -- tidak menulis.")
src = src.replace(anchor1, fungsi + "\n" + anchor1, 1)
anchor2 = '    elif jenis == "BAP":\n        simpan_state_bap(ocr)'
ganti2 = '''    elif jenis == "BAP":
        site_paksa = paksa_site(caption)   # caption mengalahkan tebakan AI
        if site_paksa:
            ocr["site"] = site_paksa
        simpan_state_bap(ocr)'''
if anchor2 not in src:
    sys.exit("GAGAL: anchor2 (jalur BAP) tidak ketemu -- tidak menulis.")
src = src.replace(anchor2, ganti2, 1)
anchor3 = '    cek("G: caption kosong -> tidak memaksa", paksa_jenis("") is None)\n'
tes = '''    print("\\n[Skenario M] Caption memaksa site (BAP), mengalahkan tebakan AI")
    cek("M: 'BAP Jembayan' -> Jembayan", paksa_site("BAP Jembayan") == "Jembayan")
    cek("M: 'bap suring juni' -> Suring", paksa_site("bap suring juni") == "Suring")
    cek("M: 'laporan mps' -> MPS", paksa_site("laporan mps") == "MPS")
    cek("M: tanpa site -> None", paksa_site("BAP juni") is None)
    cek("M: kosong -> None", paksa_site("") is None)
'''
if anchor3 not in src:
    sys.exit("GAGAL: anchor3 (selftest G) tidak ketemu -- tidak menulis.")
src = src.replace(anchor3, anchor3 + tes, 1)
open(PATH, "w", encoding="utf-8").write(src)
print("OK: paksa_site tersisip, jalur BAP diperbarui, selftest M ditambahkan.")
