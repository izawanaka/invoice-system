-- 001_bap_ocr_async.sql -- 11 Okt 2026
-- L2: unggah BAP dua fase (balas cepat, OCR di latar) -> kolom status_ocr/ocr_error
-- L3: anti-kembar berkas identik -> kolom berkas_sha256 + pagar unik di DB
-- Idempoten, satu transaksi, aditif (tidak ada DROP, tidak mengubah baris lama).
BEGIN;
SET search_path TO public;

ALTER TABLE app_bap_nota
    ADD COLUMN IF NOT EXISTS status_ocr varchar(16) NOT NULL DEFAULT 'selesai';
ALTER TABLE app_bap_nota
    ADD COLUMN IF NOT EXISTS ocr_error text;
ALTER TABLE app_bap_nota
    ADD COLUMN IF NOT EXISTS berkas_sha256 char(64);

-- Pagar L3 di level DB, bukan hanya di aplikasi: dua baris BELUM dipakai invoice
-- tidak boleh punya sidik berkas yang sama. Baris yang sudah dipakai invoice
-- sengaja dikecualikan supaya arsip historis tidak terganggu.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bap_nota_sha_belum_dipakai
    ON app_bap_nota (berkas_sha256)
    WHERE berkas_sha256 IS NOT NULL AND dipakai_invoice IS NULL;

-- Cari cepat baris yang masih diproses / gagal.
CREATE INDEX IF NOT EXISTS ix_bap_nota_status_ocr
    ON app_bap_nota (status_ocr)
    WHERE status_ocr <> 'selesai';

COMMIT;
