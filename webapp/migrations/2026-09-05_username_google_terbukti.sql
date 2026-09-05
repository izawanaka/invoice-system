-- Migrasi 5 Sep 2026: login pakai USERNAME + bukti Google (google_terbukti_pada)
-- Keputusan owner: OTP dimatikan; input login = username saja (di belakang tetap email);
-- password non-owner mati otomatis setelah Google terbukti 1x; Leo diizinkan Google.
\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE app_users ADD COLUMN IF NOT EXISTS username varchar(30);
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS google_terbukti_pada timestamptz;

-- Username awal untuk 4 akun yang ada (supaya tidak ada yang terkunci saat deploy).
UPDATE app_users SET username = CASE id
    WHEN 1 THEN 'denny'
    WHEN 2 THEN 'maya'
    WHEN 3 THEN 'alam'
    WHEN 4 THEN 'leo'
END WHERE id IN (1,2,3,4) AND username IS NULL;

-- Leo: izinkan masuk lewat Google (keputusan owner 5 Sep 2026).
UPDATE app_users SET login_via_google = true WHERE id = 4;

-- Verifikasi SEBELUM mengunci constraint.
DO $$
DECLARE n_null int; n_total int;
BEGIN
  SELECT count(*) INTO n_total FROM app_users;
  SELECT count(*) INTO n_null FROM app_users WHERE username IS NULL OR username = '';
  IF n_null <> 0 THEN
    RAISE EXCEPTION 'MIGRASI DIBATALKAN: % dari % akun belum punya username', n_null, n_total;
  END IF;
  IF (SELECT count(DISTINCT lower(username)) FROM app_users) <> n_total THEN
    RAISE EXCEPTION 'MIGRASI DIBATALKAN: username tidak unik';
  END IF;
END $$;

ALTER TABLE app_users ALTER COLUMN username SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS app_users_username_lower_key ON app_users (lower(username));
ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_username_format;
ALTER TABLE app_users ADD CONSTRAINT app_users_username_format
    CHECK (username ~ '^[a-z0-9._]{3,30}$');

COMMENT ON COLUMN app_users.username IS 'Identitas login yang DIKETIK user (5 Sep 2026). Email tetap identitas internal & identitas Google.';
COMMENT ON COLUMN app_users.google_terbukti_pada IS 'Diisi saat login Google pertama SUKSES. Non-owner: bila terisi, jalur password DITOLAK. Reset password oleh owner mengosongkannya kembali (jalur pemulihan).';

SELECT id, username, email, role, login_via_google, google_terbukti_pada FROM app_users ORDER BY id;
COMMIT;
