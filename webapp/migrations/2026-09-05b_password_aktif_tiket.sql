-- 5 Sep 2026: password awal = TIKET SEKALI PAKAI (keputusan owner).
-- "pass awal itu hanya sebagai tanda mereka bisa masuk, dan begitu bisa masuk,
--  sudah otomatis mati (flag off)". Selanjutnya non-owner hanya lewat Google.
--
-- CATATAN PENTING: kolom ini SENGAJA terpisah dari login_via_google. Memakai
-- satu flag untuk gate DAN tiket adalah bug yang sudah terjadi (commit 7b27800):
-- tiket masuk pertama jadi tidak pernah bisa dipakai. Jangan digabung lagi.
\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE app_users ADD COLUMN IF NOT EXISTS password_aktif boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN app_users.password_aktif IS
  'Tiket sekali pakai (5 Sep 2026). true = password awal masih boleh dipakai untuk SATU kali masuk. Otomatis false setelah login password berhasil ATAU setelah login Google berhasil. Owner tidak terpengaruh (selalu boleh pakai password).';

-- Isi nilai awal:
--   owner            -> true (tidak dipakai; owner kebal gate, tapi konsisten)
--   sudah Google ok  -> false (tidak perlu tiket lagi)
--   belum Google     -> true (dapat tiket masuk pertama)
UPDATE app_users SET password_aktif = CASE
    WHEN role = 'owner' THEN true
    WHEN google_terbukti_pada IS NOT NULL THEN false
    ELSE true
END;

SELECT id, username, role, login_via_google AS izin_google,
       google_terbukti_pada IS NOT NULL AS google_terbukti, password_aktif
FROM app_users ORDER BY id;
COMMIT;
