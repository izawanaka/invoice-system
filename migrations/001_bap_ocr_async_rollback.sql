-- 001_bap_ocr_async_rollback.sql -- pasangan rollback 001. JANGAN dijalankan
-- otomatis; hanya kalau L2/L3 dibatalkan DAN kode sudah dikembalikan ke versi
-- sebelum commit ini (kode baru menulis ke kolom-kolom di bawah).
BEGIN;
SET search_path TO public;
DROP INDEX IF EXISTS ix_bap_nota_status_ocr;
DROP INDEX IF EXISTS ux_bap_nota_sha_belum_dipakai;
ALTER TABLE app_bap_nota DROP COLUMN IF EXISTS berkas_sha256;
ALTER TABLE app_bap_nota DROP COLUMN IF EXISTS ocr_error;
ALTER TABLE app_bap_nota DROP COLUMN IF EXISTS status_ocr;
COMMIT;
