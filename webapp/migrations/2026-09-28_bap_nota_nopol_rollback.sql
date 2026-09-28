-- Rollback migrasi 28 Sep 2026 (JANGAN dijalankan otomatis; hanya atas perintah owner).
\set ON_ERROR_STOP on
SET search_path = public;
BEGIN;
ALTER TABLE app_bap_nota DROP COLUMN IF EXISTS nopol;
COMMIT;
