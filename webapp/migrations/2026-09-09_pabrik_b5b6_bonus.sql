-- 9 Sep 2026: PABRIK B5-B6 -- pengiriman (surat jalan, tujuan kode), tautan BAP (owner),
-- BAP versi pabrik (P7), klaim -> potongan, rekap bonus bulanan (Konsep B, K5), triwulan.
\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS ops_pengiriman (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  no_surat_jalan  text NOT NULL,
  jumlah_sak      integer NOT NULL CHECK (jumlah_sak > 0),
  nopol           text,
  tujuan_kode     text NOT NULL,           -- K3: kode (T1, T2..), bukan nama PT
  bap_id          integer REFERENCES bap(id),   -- ditautkan owner (B5)
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_pengiriman_sj_uq ON ops_pengiriman (lower(no_surat_jalan)) WHERE dibatalkan_pada IS NULL;
ALTER TABLE ops_stok_jadi_mutasi DROP CONSTRAINT IF EXISTS ops_stok_jadi_mutasi_ref_pengiriman_fk;
ALTER TABLE ops_stok_jadi_mutasi ADD CONSTRAINT ops_stok_jadi_mutasi_ref_pengiriman_fk
  FOREIGN KEY (ref_pengiriman_id) REFERENCES ops_pengiriman(id);

CREATE TABLE IF NOT EXISTS ops_klaim (
  id                 serial PRIMARY KEY,
  tanggal_terima     date NOT NULL,
  pengiriman_id      integer NOT NULL REFERENCES ops_pengiriman(id),
  jumlah_sak_diklaim integer NOT NULL CHECK (jumlah_sak_diklaim > 0),
  jenis              text NOT NULL CHECK (jenis IN ('mutu','angkut')),
  potongan_sak       integer NOT NULL,      -- mutu 2x, angkut 1x (SOP §5)
  bukti              text,
  keterangan         text,
  created_by         integer NOT NULL REFERENCES app_users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh    integer REFERENCES app_users(id),
  dibatalkan_pada    timestamptz,
  alasan_batal       text
);
ALTER TABLE ops_stok_jadi_mutasi DROP CONSTRAINT IF EXISTS ops_stok_jadi_mutasi_ref_klaim_fk;
ALTER TABLE ops_stok_jadi_mutasi ADD CONSTRAINT ops_stok_jadi_mutasi_ref_klaim_fk
  FOREIGN KEY (ref_klaim_id) REFERENCES ops_klaim(id);

CREATE TABLE IF NOT EXISTS ops_potongan (
  id              serial PRIMARY KEY,
  bulan           char(7) NOT NULL CHECK (bulan ~ '^\d{4}-\d{2}$'),
  sebab           text NOT NULL CHECK (sebab IN ('klaim_mutu','klaim_angkut','susut','opname_sak','lot_rusak','carry_over','manual')),
  sak             integer NOT NULL CHECK (sak > 0),
  ref_tabel       text,
  ref_id          integer,
  keterangan      text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);
CREATE INDEX IF NOT EXISTS ops_potongan_bulan_idx ON ops_potongan (bulan);

CREATE TABLE IF NOT EXISTS ops_rekap_bonus_bulanan (
  id               serial PRIMARY KEY,
  bulan            char(7) NOT NULL,
  karyawan_id      integer NOT NULL REFERENCES ops_karyawan(id),
  sak_bap          integer NOT NULL DEFAULT 0,
  m3_kks_tanpa_konversi numeric(12,3) NOT NULL DEFAULT 0,
  sak_dikirim      integer NOT NULL DEFAULT 0,
  potongan         integer NOT NULL DEFAULT 0,
  sak_netto        integer NOT NULL DEFAULT 0,
  sisa_negatif     integer NOT NULL DEFAULT 0,
  bonus_jenjang    numeric(14,2) NOT NULL DEFAULT 0,
  sak_klaim        integer NOT NULL DEFAULT 0,
  pct_klaim        numeric(6,3) NOT NULL DEFAULT 0,
  pengali          numeric(4,2) NOT NULL DEFAULT 1,
  bonus_bulan      numeric(14,2) NOT NULL DEFAULT 0,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','menunggu_parameter','dibekukan')),
  rincian          jsonb,
  dihitung_pada    timestamptz NOT NULL DEFAULT now(),
  dibekukan_oleh   integer REFERENCES app_users(id),
  dibekukan_pada   timestamptz,
  UNIQUE (bulan, karyawan_id)
);

CREATE TABLE IF NOT EXISTS ops_pembayaran_bonus_triwulan (
  id              serial PRIMARY KEY,
  periode         text NOT NULL CHECK (periode ~ '^\d{4}-Q[1-4]$'),
  karyawan_id     integer NOT NULL REFERENCES ops_karyawan(id),
  total           numeric(14,2) NOT NULL,
  tanggal_bayar   date NOT NULL,
  bukti           text,
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text,
  UNIQUE (periode, karyawan_id)
);

-- P7: HANYA kolom aman. Tidak ada badan_usaha_id, site, PO, invoice, harga.
CREATE OR REPLACE VIEW v_ops_bap_pabrik AS
  SELECT p.id AS pengiriman_id, p.no_surat_jalan, p.tanggal AS tanggal_kirim, p.jumlah_sak, p.tujuan_kode,
         b.no_bap, b.tgl_bap, b.total_qty AS qty_bap, b.satuan AS satuan_bap,
         coalesce((SELECT sum(k.jumlah_sak_diklaim) FROM ops_klaim k WHERE k.pengiriman_id=p.id AND k.dibatalkan_pada IS NULL),0)::integer AS sak_klaim
  FROM ops_pengiriman p LEFT JOIN bap b ON b.id = p.bap_id
  WHERE p.dibatalkan_pada IS NULL;

-- Rasio teramati sak dikirim vs m3 BAP KKS: alat owner untuk mengunci sak_per_m3_kks.
CREATE OR REPLACE VIEW v_ops_rasio_kks AS
  SELECT b.id AS bap_id, b.no_bap, b.tgl_bap, b.total_qty AS m3_bap,
         sum(p.jumlah_sak)::integer AS sak_dikirim,
         round(sum(p.jumlah_sak) / nullif(b.total_qty,0), 3) AS sak_per_m3
  FROM ops_pengiriman p JOIN bap b ON b.id=p.bap_id
  WHERE p.dibatalkan_pada IS NULL AND lower(b.satuan) IN ('m3','m³')
  GROUP BY b.id, b.no_bap, b.tgl_bap, b.total_qty;

SELECT 'B5B6_MIGRASI_OK' AS hasil, (SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'ops_%') AS n_tabel;
COMMIT;
