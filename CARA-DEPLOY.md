# Cara Deploy (sandbox -> produksi)

**Jangan pernah mengedit langsung di `/home/izawa/invoice-system`.** Semua perubahan
dikerjakan di sandbox, diuji di sandbox, lalu di-merge. Mengedit path saat deploy adalah
sumber bug yang berulang -- itulah sebabnya `config.py` ada.

## Kenapa begini
Kode SAMA PERSIS di kedua tempat. Yang membedakan hanya env var:

| | produksi | sandbox |
|---|---|---|
| kode | `/home/izawa/invoice-system` (branch `main`) | `/home/izawa/invoice-sandbox` (branch `sandbox`) |
| data | folder kode itu sendiri | `/home/izawa/invoice-sandbox-data` |
| database | `bisnis_izawa` | `bisnis_sandbox` |
| PDF | mount CIFS ke PC | disk lokal |
| Excel -> PC | ya | **tidak pernah** |

Env KOSONG = perilaku produksi. Jadi produksi jalan tanpa disetel apa-apa.

## Langkah

```bash
# 1. kerja & uji di sandbox
cd /home/izawa/invoice-sandbox
source /home/izawa/invoice-sandbox-data/env.sh

python3 test_alokasi_po.py      # aturan alokasi & rollover PO
python3 test_sukses_palsu.py    # bot TIDAK boleh bilang sukses saat gagal
python3 test_invoice_flow.py    # alur invoice utuh
python3 ocr_doc.py --selftest   # logika OCR
python3 test_ocr_fixtures.py    # OCR vs DOKUMEN ASLI  <-- WAJIB kalau PROMPT diubah

# 2. semua hijau -> commit
git add -A && git commit -m "..."

# 3. merge ke produksi
cd /home/izawa/invoice-system
git merge sandbox

# 4. verifikasi produksi menunjuk ke tempat yang benar
python3 -c "import config; print(config.ringkas())"   # harus: ENV=produksi, DB dari file kredensial
```

## Yang test TIDAK bisa tangkap

Test memanggil fungsi Python langsung. Ia **tidak** melewati jembatan n8n/Telegram.
Bug hari ini yang lolos semua test: YA/BATAL tak sampai ke addpo, filter PII merusak
nomor PO. Keduanya lahir di n8n, bukan di Python.

**Maka: fitur bot wajib dicoba dari Telegram oleh pemilik sebelum disebut "selesai".**
Hijau di test != fitur jalan.
