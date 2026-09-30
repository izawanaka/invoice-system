#!/usr/bin/env python3
"""
faktur_ocr.py -- Ekstraksi detail Faktur Pajak (nomor faktur, tanggal, DPP, PPN,
total) khusus utk fitur "Faktur Pajak" di web app (Fase 3, 30 Jul 2026).

KENAPA MODUL BARU (bukan menambah ke ocr_doc.py):
  Pola sama persis dengan webapp/po_ocr.py. ocr_doc.py dipakai SAMA PERSIS oleh
  bot Telegram -- baca_dokumen() memakai PROMPT modul-level yang tetap (tidak
  boleh diubah). Fitur ini butuh prompt sendiri (field faktur pajak: nomor
  format "010.XXX-XX.XXXXXXXX", DPP/PPN/total) sehingga tidak bisa memakai
  baca_dokumen() apa adanya.

APA YANG DIPAKAI ULANG DARI ocr_doc.py:
  - bagian_dari_berkas(nama, data): fungsi MURNI & generik (rasterisasi
    gambar/PDF jadi 'bagian' vision Claude), tidak terikat ke prompt apa
    pun -- aman dipakai ulang langsung.
  - ANTHROPIC_KEY_FILE & MODEL: satu sumber kunci API & satu model yang
    dipakai di seluruh sistem (konsisten dgn bot Telegram/BAP/PO web).

PRINSIP: endpoint yang memakai modul ini (POST /faktur-pajak/ocr di
webapp/routers/faktur_pajak.py) HANYA membaca & mengembalikan JSON pratinjau
-- TIDAK menulis apa pun ke database. Field yang tidak yakin dibaca model
WAJIB null (bukan tebakan) -- lihat aturan ketat di PROMPT_FAKTUR_DETAIL.
Penyimpanan sesungguhnya baru terjadi lewat POST /faktur-pajak setelah user
meninjau/melengkapi & MEMILIH SENDIRI invoice sistem mana yang ditautkan
(tidak pernah auto-assign).
"""
import json
import urllib.request

import ocr_doc

ANTHROPIC_KEY_FILE = ocr_doc.ANTHROPIC_KEY_FILE
MODEL = ocr_doc.MODEL

PROMPT_FAKTUR_DETAIL = (
    "Dokumen ini adalah Faktur Pajak (dokumen pajak resmi Indonesia, biasanya "
    "diterbitkan lewat e-Faktur/Coretax DJP) utk usaha cocopeat kami "
    "(PT Deliandra Karya Pratama / CV Kreasi Karya Sukses -- kami PENJUAL/PKP "
    "penerbit faktur, JANGAN PERNAH isi nama kami sendiri sebagai pembeli/lawan "
    "transaksi). Format faktur bisa berbeda-beda (hasil cetak Coretax, scan, "
    "foto HP), jadi pahami isinya, jangan mengandalkan tata letak.\n\n"
    "Bacalah SELENGKAP DAN SETELITI mungkin, lalu jawab HANYA JSON tanpa teks lain:\n"
    "{\"nomor_faktur\":\"nomor faktur pajak atau null\","
    "\"tanggal_faktur_iso\":\"YYYY-MM-DD atau null kalau tanggal tidak jelas/tidak yakin\","
    "\"nama_pembeli\":\"nama perusahaan PEMBELI/lawan transaksi yang tertera atau null\","
    "\"referensi_invoice\":\"nomor invoice/PO/referensi transaksi yang tertera di faktur (kalau ada) atau null\","
    "\"dpp\":angka_dasar_pengenaan_pajak_atau_null,"
    "\"ppn\":angka_PPN_atau_null,"
    "\"total\":angka_total_termasuk_pajak_atau_null,"
    "\"catatan_keraguan\":\"tulis di sini SEMUA field yang buram/ambigu/tidak yakin, "
    "atau null kalau semua terbaca jelas\"}\n\n"
    "ATURAN KETAT:\n"
    "- JANGAN MENEBAK. Kalau tulisan buram, terpotong, atau ambigu, isi null utk "
    "field itu dan sebutkan di catatan_keraguan -- lebih baik kosong drpd salah.\n"
    "- Nomor faktur pajak Indonesia biasanya berformat seperti "
    "'010.XXX-XX.XXXXXXXX' (3 digit kode transaksi, titik, 3 digit status, "
    "strip, 2 digit tahun, titik, 8 digit nomor urut) -- baca digit per digit "
    "dgn teliti, JANGAN mengoreksi/menormalkan formatnya sendiri, salin PERSIS "
    "apa yang tertulis. Kalau formatnya tidak cocok pola ini sama sekali dan "
    "kamu ragu itu benar nomor faktur, tetap isi apa yang terbaca tapi sebutkan "
    "keraguannya di catatan_keraguan.\n"
    "- Angka JANGAN pakai pemisah ribuan (mis. tulis 3200000 bukan 3.200.000).\n"
    "- 'total' = DPP + PPN (nilai total termasuk pajak yang tertera di dokumen), "
    "BUKAN cuma DPP.\n"
    "- Kalau dokumen ternyata BUKAN Faktur Pajak (mis. Invoice biasa, BAP, atau "
    "surat lain), tetap jawab format JSON di atas dgn semua field null dan "
    "catatan_keraguan = 'Dokumen ini sepertinya bukan Faktur Pajak'."
)


def baca_faktur_detail(bagian):
    """Kirim gambar/PDF (bentuk 'bagian' dari ocr_doc.bagian_dari_berkas) ke Claude
    dgn prompt KHUSUS ekstraksi Faktur Pajak. SENGAJA TIDAK memakai
    ocr_doc.baca_dokumen() krn fungsi itu memakai PROMPT klasifikasi ringkas milik
    bot Telegram yang tidak boleh diubah/dipakai dgn prompt lain."""
    # 30 Sep 2026: Faktur Pajak di LUAR lingkup Aturan #21 (tabel faktur_pajak 0 baris) -- router menangkap error ini
    raise RuntimeError("OCR Faktur Pajak belum tersedia di mesin OCR lokal (Aturan Bisnis #21); isi manual dulu")


def ekstrak_faktur(filename, data):
    """Titik masuk dipakai router webapp/routers/faktur_pajak.py
    (endpoint POST /faktur-pajak/ocr). Kembalikan dict siap dipetakan ke
    schemas.FakturPajakOcrOut. TIDAK menyentuh DB/file state apa pun -- murni
    pratinjau ekstraksi."""
    bagian = ocr_doc.bagian_dari_berkas(filename, data)
    ocr = baca_faktur_detail(bagian)

    return {
        "nomor_faktur": ocr.get("nomor_faktur") or None,
        "tanggal_faktur": ocr.get("tanggal_faktur_iso") or None,
        "nama_pembeli": ocr.get("nama_pembeli") or None,
        "referensi_invoice": ocr.get("referensi_invoice") or None,
        "dpp": ocr.get("dpp"),
        "ppn": ocr.get("ppn"),
        "total": ocr.get("total"),
        "catatan_keraguan": ocr.get("catatan_keraguan") or None,
    }
