#!/usr/bin/env python3
"""
po_ocr.py -- Ekstraksi detail PO (item, harga, tanggal) khusus utk fitur
"Tambah PO dari Foto/Scan" di web app (Fase 2, 30 Jul 2026).

KENAPA MODUL BARU (bukan menambah ke ocr_doc.py):
  ocr_doc.py dipakai SAMA PERSIS oleh bot Telegram (lihat docstring
  webapp/routers/bap.py: "ocr_doc.py sendiri TIDAK diubah"). Fungsi
  baca_dokumen() di sana memakai PROMPT modul-level yang tetap (klasifikasi
  BAP/PO/LAIN + field ringkas: po_no & total_qty saja utk PO). Prompt itu
  TIDAK BOLEH diubah krn bisa mengubah perilaku bot Telegram yang sudah
  berjalan. Fitur ini butuh field lebih rinci (rincian item per baris,
  tanggal, breakdown harga) sehingga perlu prompt sendiri -- baca_dokumen()
  tidak menerima prompt custom (PROMPT ditulis langsung di badan fungsi),
  jadi tidak bisa dipakai ulang apa adanya utk kebutuhan ini.

APA YANG DIPAKAI ULANG DARI ocr_doc.py:
  - bagian_dari_berkas(nama, data): fungsi MURNI & generik (rasterisasi
    gambar/PDF jadi 'bagian' vision Claude), tidak terikat ke prompt apa
    pun -- aman dipakai ulang langsung.
  - ANTHROPIC_KEY_FILE & MODEL: supaya satu sumber kunci API & satu model
    yang dipakai di seluruh sistem (konsisten dgn bot Telegram/BAP web).
  - pt_site.resolve_site(): saran site dari nama PT, sama seperti jalur PO
    Telegram (ocr_doc.terapkan_pt_site).

PRINSIP: endpoint yang memakai modul ini (POST /po/ocr di
webapp/routers/po.py) HANYA membaca & mengembalikan JSON pratinjau --
TIDAK menulis apa pun ke database. Field yang tidak yakin dibaca model
WAJIB null (bukan tebakan) -- lihat aturan ketat di PROMPT_PO_DETAIL.
Penyimpanan sesungguhnya baru terjadi lewat POST /po (endpoint yang sudah
ada & sudah diuji) setelah user meninjau/melengkapi hasil ekstraksi ini.
"""
import json
import urllib.request

import ocr_doc
import pt_site

ANTHROPIC_KEY_FILE = ocr_doc.ANTHROPIC_KEY_FILE
MODEL = ocr_doc.MODEL

PROMPT_PO_DETAIL = (
    "Dokumen ini adalah PO (Purchase Order) dari customer utk usaha cocopeat kami "
    "(PT Deliandra Karya Pratama / CV Kreasi Karya Sukses -- kami PENJUAL, JANGAN "
    "PERNAH isi nama kami sendiri sebagai customer). Format PO berbeda-beda antar "
    "customer, jadi pahami isinya, jangan mengandalkan tata letak.\n\n"
    "Bacalah SELENGKAP DAN SETELITI mungkin, lalu jawab HANYA JSON tanpa teks lain:\n"
    "{\"po_no\":\"nomor PO atau null\","
    "\"customer\":\"nama perusahaan PEMBELI/penerbit PO atau null\","
    "\"tanggal_iso\":\"YYYY-MM-DD atau null kalau tanggal tidak jelas/tidak yakin\","
    "\"site_tebakan\":\"nama site tujuan pengiriman kalau tersurat jelas, kalau tidak yakin null\","
    "\"items\":[{\"nama_item\":\"nama barang/jasa\",\"kuantitas\":angka_atau_null,"
    "\"harga_satuan\":angka_atau_null,\"subtotal\":angka_atau_null}],"
    "\"total_qty\":angka_total_kuantitas_seluruh_item_atau_null,"
    "\"satuan\":\"satuan (kg, m3, dsb) atau null\","
    "\"harga_satuan\":angka_harga_per_satuan_kalau_PO_hanya_1_jenis_item_atau_null,"
    "\"total_nilai\":angka_total_nilai_PO_atau_null,"
    "\"catatan_keraguan\":\"tulis di sini SEMUA field yang buram/ambigu/tidak yakin, "
    "atau null kalau semua terbaca jelas\"}\n\n"
    "ATURAN KETAT:\n"
    "- JANGAN MENEBAK. Kalau tulisan buram, terpotong, atau ambigu, isi null utk "
    "field itu dan sebutkan di catatan_keraguan -- lebih baik kosong drpd salah.\n"
    "- Angka JANGAN pakai pemisah ribuan (mis. tulis 3200000 bukan 3.200.000).\n"
    "- 'items' minimal 1 entri kalau PO memuat rincian barang/jasa. Kalau PO cuma "
    "1 jenis item, cukup 1 entri -- isi juga total_qty/satuan/harga_satuan di "
    "level atas supaya form bisa langsung dipakai.\n"
    "- 'site' adalah lokasi/tujuan pengiriman, BUKAN alamat kantor customer. Kalau "
    "tidak tersurat jelas di dokumen, biarkan null -- JANGAN menebak dari alamat.\n"
    "- Kalau dokumen ternyata BUKAN PO (mis. BAP atau surat lain), tetap jawab "
    "format JSON di atas dgn semua field null dan catatan_keraguan = "
    "'Dokumen ini sepertinya bukan PO'."
)


def baca_po_detail(bagian):
    """Kirim gambar/PDF (bentuk 'bagian' dari ocr_doc.bagian_dari_berkas) ke Claude
    dgn prompt KHUSUS ekstraksi PO rinci. SENGAJA TIDAK memakai ocr_doc.baca_dokumen()
    krn fungsi itu memakai PROMPT klasifikasi ringkas milik bot Telegram yang tidak
    boleh diubah/dipakai dgn prompt lain (lihat docstring modul)."""
    with open(ANTHROPIC_KEY_FILE) as f:
        key = f.read().strip()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1500,
        "messages": [{"role": "user",
                      "content": bagian + [{"type": "text", "text": PROMPT_PO_DETAIL}]}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body)
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    resp = json.loads(urllib.request.urlopen(req).read())
    teks = resp["content"][0]["text"].replace("```json", "").replace("```", "").strip()
    return json.loads(teks)


def ekstrak_po(filename, data):
    """Titik masuk dipakai router webapp/routers/po.py (endpoint POST /po/ocr).
    Kembalikan dict siap dipetakan ke schemas.POOcrOut. TIDAK menyentuh DB/file
    state apa pun -- murni pratinjau ekstraksi."""
    bagian = ocr_doc.bagian_dari_berkas(filename, data)
    ocr = baca_po_detail(bagian)

    site_tebakan = ocr.get("site_tebakan") or ""
    site_saran, site_status = pt_site.resolve_site(ocr.get("customer") or "", site_tebakan)

    items = ocr.get("items") or []
    if not isinstance(items, list):
        items = []
    items_bersih = []
    for it in items:
        if not isinstance(it, dict):
            continue
        items_bersih.append({
            "nama_item": it.get("nama_item") or None,
            "kuantitas": it.get("kuantitas"),
            "harga_satuan": it.get("harga_satuan"),
            "subtotal": it.get("subtotal"),
        })

    return {
        "po_no": ocr.get("po_no") or None,
        "customer": ocr.get("customer") or None,
        "tanggal": ocr.get("tanggal_iso") or None,
        "items": items_bersih,
        "total_qty": ocr.get("total_qty"),
        "satuan": (ocr.get("satuan") or "").strip().lower() or None,
        "harga_satuan": ocr.get("harga_satuan"),
        "total_nilai": ocr.get("total_nilai"),
        "site_saran": site_saran or None,
        "site_status": site_status,
        "catatan_keraguan": ocr.get("catatan_keraguan") or None,
    }
