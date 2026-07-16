#!/usr/bin/env python3
"""test_ocr_fixtures.py -- uji prompt OCR terhadap DOKUMEN ASLI.

KENAPA FILE INI ADA (14 Juli 2026):
74 test lain memanggil fungsi Python secara langsung dengan angka karangan. Semuanya
HIJAU, padahal OCR salah membaca dokumen sungguhan -- dua kali, dengan confidence "high":
  1. Mengambil berat KOTOR (19.104 kg) padahal harus berat BERSIH (18.852 kg).
  2. Mengisi customer dengan nama perusahaan SENDIRI, bukan pembeli.
Keduanya lolos semua test dan baru ketahuan setelah invoice salah terbit di produksi.

Test ini satu-satunya yang melihat dokumen ASLI. Jalankan SETIAP KALI prompt ocr_doc.py
diubah. Merah = prompt MUNDUR, jangan dideploy. (Memanggil API Anthropic; ada biayanya.)

Pakai:  python3 test_ocr_fixtures.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_doc

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
pass_, fail = 0, []


def cek(nama, ok, detail=""):
    global pass_
    if ok:
        pass_ += 1
        print(f"  PASS: {nama}")
    else:
        fail.append(nama)
        print(f"  FAIL: {nama}  {detail}")


def main():
    harapan = json.load(open(os.path.join(FIX, "expected.json")))
    for berkas, exp in harapan.items():
        if berkas.startswith("_"):
            continue
        path = os.path.join(FIX, berkas)
        if not os.path.exists(path):
            cek(f"{berkas}: file fixture ada", False, "-- file hilang")
            continue
        print(f"\n--- {berkas} ---")
        print(f"    ({exp['_kenapa_ada']})")
        bagian = ocr_doc.bagian_dari_berkas(berkas, open(path, "rb").read())
        hasil = ocr_doc.baca_dokumen(bagian)
        print(f"    OCR baca: {json.dumps({k: v for k, v in hasil.items() if k != 'reply'}, ensure_ascii=False)}")

        for kunci, nilai in exp.items():
            if kunci.startswith("_"):
                continue
            # PENTING: cek "_dilarang_memuat" DULU -- ia juga berakhiran "_memuat",
            # jadi kalau urutannya terbalik ia tertangkap cabang yang salah.
            if kunci.endswith("_dilarang_memuat"):
                f = kunci[:-len("_dilarang_memuat")]
                cek(f"{berkas}: {f} TIDAK memuat '{nilai}'",
                    nilai.lower() not in str(hasil.get(f, "")).lower(),
                    f"-- terbaca: {hasil.get(f)!r} (ini nama perusahaan SENDIRI!)")
            elif kunci.endswith("_memuat"):
                f = kunci[:-len("_memuat")]
                cek(f"{berkas}: {f} memuat '{nilai}'",
                    nilai.lower() in str(hasil.get(f, "")).lower(),
                    f"-- terbaca: {hasil.get(f)!r}")
            else:
                cek(f"{berkas}: {kunci} = {nilai}",
                    str(hasil.get(kunci, "")).strip() == str(nilai).strip(),
                    f"-- terbaca: {hasil.get(kunci)!r}")

    print("\n" + "=" * 60)
    print(f"HASIL FIXTURE: {pass_} PASS, {len(fail)} FAIL")
    if fail:
        print("GAGAL: " + ", ".join(fail))
        print("\n>> PROMPT OCR MUNDUR. JANGAN DEPLOY.")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
