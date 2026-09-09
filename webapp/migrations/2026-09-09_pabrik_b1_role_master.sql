-- 9 Sep 2026: PABRIK B1 -- peran admin/kepala + tabel master/parameter workspace Pabrik.
-- Kontrak: Business/Cocopeat/DESIGN-PABRIK.md (K1..K10, P1..P10).
-- Tabel invoice (purchase_orders, bap, invoices) TIDAK disentuh.
\set ON_ERROR_STOP on
BEGIN;

-- ---------- 1. Peran baru (K2). Satu-satunya perubahan pada skema lama. ----------
ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_role_check;
ALTER TABLE app_users ADD CONSTRAINT app_users_role_check
  CHECK (role IN ('owner','staff','viewer','admin','kepala'));
COMMENT ON CONSTRAINT app_users_role_check ON app_users IS
  'owner/staff/viewer = apps invoice; admin/kepala = workspace Pabrik saja (DESIGN-PABRIK K2, 9 Sep 2026)';

-- ---------- 2. Parameter effective-dated (P9) ----------
CREATE TABLE IF NOT EXISTS ops_parameter (
  id              serial PRIMARY KEY,
  kode            text NOT NULL,
  nilai           numeric,               -- NULL = belum diputuskan owner
  berlaku_mulai   date NOT NULL,
  berlaku_sampai  date,
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text,
  CONSTRAINT ops_parameter_rentang CHECK (berlaku_sampai IS NULL OR berlaku_sampai >= berlaku_mulai),
  CONSTRAINT ops_parameter_kode CHECK (kode ~ '^[a-z0-9_]{2,40}$')
);
CREATE INDEX IF NOT EXISTS ops_parameter_kode_idx ON ops_parameter (kode, berlaku_mulai DESC);
COMMENT ON TABLE ops_parameter IS 'Parameter pabrik effective-dated (DESIGN-PABRIK P9). nilai NULL = belum diputuskan.';

-- Nilai efektif satu parameter pada tanggal tertentu (baris aktif, belum dibatalkan).
CREATE OR REPLACE FUNCTION ops_param(p_kode text, p_tgl date DEFAULT CURRENT_DATE)
RETURNS numeric LANGUAGE sql STABLE AS $$
  SELECT nilai FROM ops_parameter
  WHERE kode = p_kode AND dibatalkan_pada IS NULL
    AND berlaku_mulai <= p_tgl AND (berlaku_sampai IS NULL OR berlaku_sampai >= p_tgl)
  ORDER BY berlaku_mulai DESC, id DESC LIMIT 1
$$;

-- ---------- 3. Karyawan (kepala; buruh tetap bila ada) ----------
CREATE TABLE IF NOT EXISTS ops_karyawan (
  id              serial PRIMARY KEY,
  nama            text NOT NULL,
  peran           text NOT NULL CHECK (peran IN ('kepala','buruh','langsir','supir')),
  gaji_pokok      numeric(14,2) NOT NULL DEFAULT 0,
  uang_makan      numeric(14,2) NOT NULL DEFAULT 0,
  user_id         integer REFERENCES app_users(id),
  berlaku_mulai   date NOT NULL,
  berlaku_sampai  date,
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text,
  CONSTRAINT ops_karyawan_rentang CHECK (berlaku_sampai IS NULL OR berlaku_sampai >= berlaku_mulai)
);

-- ---------- 4. Tarif bonus berjenjang KSP-CP-001 (marjinal) ----------
CREATE TABLE IF NOT EXISTS ops_tarif_bonus (
  id              serial PRIMARY KEY,
  jenjang         smallint NOT NULL,
  sak_dari        integer NOT NULL,
  sak_sampai      integer,               -- NULL = tanpa batas atas
  tarif_per_sak   numeric(12,2) NOT NULL,
  berlaku_mulai   date NOT NULL,
  berlaku_sampai  date,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text,
  CONSTRAINT ops_tarif_bonus_rentang CHECK (berlaku_sampai IS NULL OR berlaku_sampai >= berlaku_mulai),
  CONSTRAINT ops_tarif_bonus_sak CHECK (sak_sampai IS NULL OR sak_sampai >= sak_dari)
);

-- ---------- 5. Pengali kualitas (klaim %) ----------
-- Baris berlaku bila pct >= batas (inklusif=true) atau pct > batas (inklusif=false);
-- yang dipakai = baris dengan batas terbesar yang terpenuhi.
CREATE TABLE IF NOT EXISTS ops_pengali_klaim (
  id              serial PRIMARY KEY,
  batas_pct       numeric(6,3) NOT NULL,
  inklusif        boolean NOT NULL DEFAULT true,
  pengali         numeric(4,2) NOT NULL CHECK (pengali >= 0 AND pengali <= 1),
  berlaku_mulai   date NOT NULL,
  berlaku_sampai  date,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);

CREATE OR REPLACE FUNCTION ops_pengali(p_pct numeric, p_tgl date DEFAULT CURRENT_DATE)
RETURNS numeric LANGUAGE sql STABLE AS $$
  SELECT pengali FROM ops_pengali_klaim
  WHERE dibatalkan_pada IS NULL
    AND berlaku_mulai <= p_tgl AND (berlaku_sampai IS NULL OR berlaku_sampai >= p_tgl)
    AND ((inklusif AND p_pct >= batas_pct) OR (NOT inklusif AND p_pct > batas_pct))
  ORDER BY batas_pct DESC, inklusif ASC LIMIT 1
$$;

-- ---------- 6. Master: pemasok & petak ----------
CREATE TABLE IF NOT EXISTS ops_pemasok (
  id          serial PRIMARY KEY,
  nama        text NOT NULL,
  jenis       text NOT NULL CHECK (jenis IN ('sabut','sak','lainnya')),
  kontak      text,
  aktif       boolean NOT NULL DEFAULT true,
  created_by  integer NOT NULL REFERENCES app_users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_pemasok_nama_jenis_uq ON ops_pemasok (lower(nama), jenis);

CREATE TABLE IF NOT EXISTS ops_petak (
  id            serial PRIMARY KEY,
  nomor         text NOT NULL UNIQUE,
  panjang_m     numeric(6,2),
  lebar_m       numeric(6,2),
  tinggi_maks_m numeric(6,2),
  aktif         boolean NOT NULL DEFAULT true,
  created_by    integer NOT NULL REFERENCES app_users(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------- 7. Seed (created_by = owner id 1 / denny) ----------
INSERT INTO ops_parameter (kode, nilai, berlaku_mulai, catatan, created_by) VALUES
 ('kg_per_sak',          34,      DATE '2026-09-01', 'K6: 1 sak = 33-35 kg berat penuh, nominal 34', 1),
 ('sak_per_m3_kks',      NULL,    DATE '2026-09-01', 'BELUM diputuskan; dikunci owner setelah rasio teramati (v_ops_rasio_kks)', 1),
 ('rendemen_sak_per_kubik', 2.5,  DATE '2026-09-01', 'Rendemen standar 1 kubik = 2,5 sak', 1),
 ('rendemen_min',        2.25,    DATE '2026-09-01', 'SOP-CP-001 kisaran wajar bawah', 1),
 ('rendemen_max',        3.00,    DATE '2026-09-01', 'SOP-CP-001 kisaran wajar atas', 1),
 ('bonus_cap_bulan',     6000000, DATE '2026-09-01', 'KSP-CP-001 cap bonus per bulan', 1),
 ('berat_sak_min_kg',    NULL,    DATE '2026-09-01', 'SOP [..] belum diputuskan', 1),
 ('kadar_air_max_pct',   NULL,    DATE '2026-09-01', 'SOP [..] belum diputuskan', 1),
 ('ec_max',              NULL,    DATE '2026-09-01', 'SOP [..] belum diputuskan (mS/cm)', 1),
 ('toleransi_susut_pct', NULL,    DATE '2026-09-01', 'SOP [..] belum diputuskan', 1),
 ('batas_hari_karung',   NULL,    DATE '2026-09-01', 'SOP [..] belum diputuskan', 1),
 ('upah_buruh',          NULL,    DATE '2026-09-01', 'K7 upah harian buruh (per hari) - belum diisi', 1),
 ('upah_langsir',        NULL,    DATE '2026-09-01', 'K7 upah langsir - belum diisi', 1),
 ('upah_supir',          NULL,    DATE '2026-09-01', 'K7 upah supir jemput sabut - belum diisi', 1);

INSERT INTO ops_tarif_bonus (jenjang, sak_dari, sak_sampai, tarif_per_sak, berlaku_mulai, created_by) VALUES
 (0,    1, 4500,    0, DATE '2026-09-01', 1),
 (1, 4501, 5000, 2000, DATE '2026-09-01', 1),
 (2, 5001, 5500, 4000, DATE '2026-09-01', 1),
 (3, 5501, 6000, 6000, DATE '2026-09-01', 1);

INSERT INTO ops_pengali_klaim (batas_pct, inklusif, pengali, berlaku_mulai, created_by) VALUES
 (0, true,  1.00, DATE '2026-09-01', 1),
 (1, true,  0.80, DATE '2026-09-01', 1),
 (3, false, 0.50, DATE '2026-09-01', 1),
 (5, false, 0.00, DATE '2026-09-01', 1);

-- ---------- 8. Verifikasi di dalam transaksi ----------
DO $g$
BEGIN
  IF ops_param('kg_per_sak') <> 34 THEN RAISE EXCEPTION 'seed kg_per_sak salah'; END IF;
  IF ops_pengali(0.5) <> 1.00 THEN RAISE EXCEPTION 'pengali 0.5%% salah'; END IF;
  IF ops_pengali(2)   <> 0.80 THEN RAISE EXCEPTION 'pengali 2%% salah'; END IF;
  IF ops_pengali(3)   <> 0.80 THEN RAISE EXCEPTION 'pengali 3%% salah (harus 0.8)'; END IF;
  IF ops_pengali(4)   <> 0.50 THEN RAISE EXCEPTION 'pengali 4%% salah'; END IF;
  IF ops_pengali(5)   <> 0.50 THEN RAISE EXCEPTION 'pengali 5%% salah (harus 0.5)'; END IF;
  IF ops_pengali(6)   <> 0.00 THEN RAISE EXCEPTION 'pengali 6%% salah'; END IF;
  IF (SELECT count(*) FROM ops_parameter) <> 14 THEN RAISE EXCEPTION 'jumlah parameter salah'; END IF;
END $g$;

SELECT 'B1_MIGRASI_OK' AS hasil, count(*) AS n_param FROM ops_parameter;
COMMIT;
