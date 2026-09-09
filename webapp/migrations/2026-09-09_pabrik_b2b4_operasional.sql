-- 9 Sep 2026: PABRIK B2-B4 -- operasional: lot & tahap, terima truk, produksi sak,
-- ledger sak kosong, ledger stok jadi, kas kecil, upah harian, cuaca.
-- Kontrak: Business/Cocopeat/DESIGN-PABRIK.md (P1 append-only, P2 saldo = SUM ledger,
-- P3 kubik dihitung server, P4 produksi atomik, P5 saldo tidak negatif, P6 1 petak = 1 lot).
\set ON_ERROR_STOP on
BEGIN;

-- ---------- lot & tahap ----------
CREATE TABLE IF NOT EXISTS ops_lot (
  id              serial PRIMARY KEY,
  petak_id        integer NOT NULL REFERENCES ops_petak(id),
  nomor_lot       text NOT NULL UNIQUE,
  tanggal_buka    date NOT NULL,
  tanggal_tutup   date,
  status          text NOT NULL DEFAULT 'curah'
                  CHECK (status IN ('curah','giling','basah','jemur','siap_karung','habis')),
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);
-- P6: satu petak hanya boleh punya SATU lot aktif (belum habis, belum dibatalkan).
CREATE UNIQUE INDEX IF NOT EXISTS ops_lot_satu_aktif_per_petak
  ON ops_lot (petak_id) WHERE status <> 'habis' AND dibatalkan_pada IS NULL;

CREATE TABLE IF NOT EXISTS ops_lot_tahap (
  id            serial PRIMARY KEY,
  lot_id        integer NOT NULL REFERENCES ops_lot(id),
  tahap         text NOT NULL CHECK (tahap IN ('curah','giling','basah','jemur','siap_karung','habis')),
  tanggal_mulai date NOT NULL,
  ec            numeric(6,3),
  kadar_air_pct numeric(5,2),
  catatan       text,
  created_by    integer NOT NULL REFERENCES app_users(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ops_lot_tahap_lot_idx ON ops_lot_tahap (lot_id, id);

-- ---------- terima truk (P3: kubik generated) ----------
CREATE TABLE IF NOT EXISTS ops_penerimaan (
  id              serial PRIMARY KEY,
  tahun           integer NOT NULL,
  no_urut         integer NOT NULL,
  tanggal         date NOT NULL,
  jam             time NOT NULL,
  nopol           text NOT NULL,
  pemasok_id      integer NOT NULL REFERENCES ops_pemasok(id),
  p_m             numeric(6,2) NOT NULL CHECK (p_m > 0),
  l_m             numeric(6,2) NOT NULL CHECK (l_m > 0),
  t_m             numeric(6,2) NOT NULL CHECK (t_m > 0),
  kubik_masuk     numeric(10,3) GENERATED ALWAYS AS (round(p_m * l_m * t_m, 3)) STORED,
  lot_id          integer NOT NULL REFERENCES ops_lot(id),
  foto_plat       text,
  foto_muatan     text,
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text,
  UNIQUE (tahun, no_urut)
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_penerimaan_nopol_uq
  ON ops_penerimaan (nopol, tanggal, jam) WHERE dibatalkan_pada IS NULL;

-- ---------- produksi sak (P4 atomik di aplikasi) ----------
CREATE TABLE IF NOT EXISTS ops_produksi_sak (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  lot_id          integer NOT NULL REFERENCES ops_lot(id),
  jumlah_sak      integer NOT NULL CHECK (jumlah_sak > 0),
  berat_sampel    jsonb,
  status_qc       text NOT NULL DEFAULT 'belum' CHECK (status_qc IN ('lolos','gagal','belum')),
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);

-- ---------- ledger sak kosong (P2) ----------
CREATE TABLE IF NOT EXISTS ops_sak_kosong_mutasi (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  jenis           text NOT NULL CHECK (jenis IN ('beli','rusak','retur','dipakai','opname','koreksi')),
  delta           integer NOT NULL,     -- beli +, rusak -, dipakai -, retur 0, opname/koreksi +/-
  jumlah          integer NOT NULL CHECK (jumlah >= 0),
  pemasok_id      integer REFERENCES ops_pemasok(id),
  harga_per_sak   numeric(12,2),
  foto_nota       text,
  ref_produksi_id integer REFERENCES ops_produksi_sak(id),
  keterangan      text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);

-- ---------- ledger stok jadi (P2) ----------
CREATE TABLE IF NOT EXISTS ops_stok_jadi_mutasi (
  id                serial PRIMARY KEY,
  tanggal           date NOT NULL,
  jenis             text NOT NULL CHECK (jenis IN ('produksi','kirim','klaim','opname','koreksi')),
  delta             integer NOT NULL,
  ref_produksi_id   integer REFERENCES ops_produksi_sak(id),
  ref_pengiriman_id integer,          -- FK dipasang di B5
  ref_klaim_id      integer,          -- FK dipasang di B6
  keterangan        text,
  created_by        integer NOT NULL REFERENCES app_users(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh   integer REFERENCES app_users(id),
  dibatalkan_pada   timestamptz,
  alasan_batal      text
);

-- ---------- kas kecil (P2, P5) ----------
CREATE TABLE IF NOT EXISTS ops_kas_kecil (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  jenis           text NOT NULL CHECK (jenis IN ('keluar','isi_ulang')),
  kategori        text NOT NULL CHECK (kategori IN ('bbm','upah','sak','perbaikan','konsumsi','lain','isi_ulang')),
  nominal         numeric(14,2) NOT NULL CHECK (nominal > 0),
  keterangan      text,
  foto_nota       text,
  ref_sak_mutasi_id integer REFERENCES ops_sak_kosong_mutasi(id),
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);
ALTER TABLE ops_sak_kosong_mutasi ADD COLUMN IF NOT EXISTS ref_kas_id integer REFERENCES ops_kas_kecil(id);

-- ---------- upah harian (K7) ----------
CREATE TABLE IF NOT EXISTS ops_upah_harian (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  nama            text NOT NULL,
  peran           text NOT NULL CHECK (peran IN ('buruh','langsir','supir')),
  satuan          text NOT NULL CHECK (satuan IN ('hari','rit')),
  jumlah          numeric(8,2) NOT NULL CHECK (jumlah > 0),
  tarif           numeric(12,2) NOT NULL CHECK (tarif > 0),
  total           numeric(14,2) NOT NULL,
  kas_id          integer NOT NULL REFERENCES ops_kas_kecil(id),
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);

-- ---------- cuaca (K10) ----------
CREATE TABLE IF NOT EXISTS ops_cuaca (
  id           serial PRIMARY KEY,
  tanggal      date NOT NULL,
  sumber       text NOT NULL CHECK (sumber IN ('api','manual')),
  hujan_mm     numeric(7,2),
  suhu_max_c   numeric(5,2),
  cuaca_teks   text,
  catatan      text,
  created_by   integer REFERENCES app_users(id),   -- NULL = job otomatis
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tanggal, sumber)
);

-- ---------- views (P2) ----------
CREATE OR REPLACE VIEW v_ops_saldo_sak_kosong AS
  SELECT coalesce(sum(delta),0)::integer AS saldo,
         coalesce(sum(CASE WHEN jenis='rusak' THEN jumlah ELSE 0 END),0)::integer
         - coalesce(sum(CASE WHEN jenis='retur' THEN jumlah ELSE 0 END),0)::integer AS rusak_belum_retur
  FROM ops_sak_kosong_mutasi WHERE dibatalkan_pada IS NULL;

CREATE OR REPLACE VIEW v_ops_saldo_stok_jadi AS
  SELECT coalesce(sum(delta),0)::integer AS saldo
  FROM ops_stok_jadi_mutasi WHERE dibatalkan_pada IS NULL;

CREATE OR REPLACE VIEW v_ops_saldo_kas AS
  SELECT coalesce(sum(CASE WHEN jenis='isi_ulang' THEN nominal ELSE -nominal END),0)::numeric(14,2) AS saldo
  FROM ops_kas_kecil WHERE dibatalkan_pada IS NULL;

CREATE OR REPLACE VIEW v_ops_lot_ringkas AS
  SELECT l.id AS lot_id, l.nomor_lot, l.petak_id, pt.nomor AS petak, l.status, l.tanggal_buka, l.tanggal_tutup,
         coalesce((SELECT sum(kubik_masuk) FROM ops_penerimaan p WHERE p.lot_id=l.id AND p.dibatalkan_pada IS NULL),0)::numeric(10,3) AS kubik_masuk,
         coalesce((SELECT sum(jumlah_sak) FROM ops_produksi_sak s WHERE s.lot_id=l.id AND s.dibatalkan_pada IS NULL),0)::integer AS sak_jadi,
         coalesce((SELECT sum(jumlah_sak) FROM ops_produksi_sak s WHERE s.lot_id=l.id AND s.dibatalkan_pada IS NULL AND s.status_qc='lolos'),0)::integer AS sak_lolos_qc,
         (CURRENT_DATE - l.tanggal_buka) AS umur_hari,
         CASE WHEN ops_param('batas_hari_karung') IS NOT NULL AND l.status <> 'habis'
                   AND (CURRENT_DATE - l.tanggal_buka) > ops_param('batas_hari_karung') THEN true ELSE false END AS lewat_batas_karung
  FROM ops_lot l JOIN ops_petak pt ON pt.id = l.petak_id
  WHERE l.dibatalkan_pada IS NULL;

CREATE OR REPLACE VIEW v_ops_hpp_bulanan AS
  WITH kas AS (SELECT to_char(tanggal,'YYYY-MM') AS bulan, sum(nominal) AS biaya_kas
               FROM ops_kas_kecil WHERE jenis='keluar' AND dibatalkan_pada IS NULL GROUP BY 1),
       prod AS (SELECT to_char(tanggal,'YYYY-MM') AS bulan, sum(jumlah_sak) AS sak
                FROM ops_produksi_sak WHERE dibatalkan_pada IS NULL AND status_qc='lolos' GROUP BY 1)
  SELECT kas.bulan, kas.biaya_kas::numeric(14,2) AS biaya_kas, coalesce(prod.sak,0)::integer AS sak_lolos_qc
  FROM kas LEFT JOIN prod USING (bulan);

SELECT 'B2B4_MIGRASI_OK' AS hasil,
       (SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'ops_%') AS n_tabel;
COMMIT;
