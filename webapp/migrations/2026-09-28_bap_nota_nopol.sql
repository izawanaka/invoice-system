-- Migrasi 28 Sep 2026: plat kendaraan per BAP (Rekap Invoice rincian per BAP).
-- Keputusan owner 28 Sep 2026: plat dibaca dari dokumen BAP yang jadi dasar terbit
-- invoice (OCR saat unggah web/Telegram). Kolom teks, pisah koma bila >1 truk.
-- Idempoten; satu transaksi; tidak menyentuh tabel invoices/invoice_items/bap.
\set ON_ERROR_STOP on
SET search_path = public;
BEGIN;
ALTER TABLE app_bap_nota ADD COLUMN IF NOT EXISTS nopol text;
COMMENT ON COLUMN app_bap_nota.nopol IS 'Plat kendaraan pengangkut dari OCR dokumen BAP (28 Sep 2026); pisah koma bila >1; NULL = tidak terbaca/tidak tertulis.';
-- Isi awal dari ocr_json bila OCR sudah pernah mengembalikan nopol (backfill OCR ulang dilakukan skrip terpisah).
UPDATE app_bap_nota SET nopol = NULLIF(trim(ocr_json->>'nopol'), '')
 WHERE nopol IS NULL AND ocr_json ? 'nopol' AND NULLIF(trim(ocr_json->>'nopol'), '') IS NOT NULL;
SELECT 'NOPOL_MIGRASI_OK' AS hasil, count(*) AS n_nota, count(nopol) AS n_nopol FROM app_bap_nota;
COMMIT;
