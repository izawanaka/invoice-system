-- 9 Sep 2026: PABRIK B7 -- stock opname (owner), tutup hari (penanda disiplin), audit
-- otomatis A1-A10 (temuan tersimpan, laporan Telegram ke owner). DESIGN-PABRIK.md §6.
-- P1: opname/tutup hari append-only (batal = tandai). Temuan audit bukan ledger: status
-- terbuka -> ditutup (owner) / selesai_otomatis (kondisi hilang), baris tidak dihapus.
\set ON_ERROR_STOP on
BEGIN;

-- ---------- stock opname (owner) ----------
CREATE TABLE IF NOT EXISTS ops_stock_opname (
  id                 serial PRIMARY KEY,
  tanggal            date NOT NULL,
  jenis              text NOT NULL CHECK (jenis IN ('petak','sak_kosong','stok_jadi')),
  objek_id           integer,                       -- petak: lot_id; lainnya NULL
  nilai_terukur      numeric(12,3) NOT NULL CHECK (nilai_terukur >= 0),
  nilai_sistem       numeric(12,3) NOT NULL,        -- snapshot saat opname
  selisih            numeric(12,3) NOT NULL,        -- terukur - sistem
  ref_mutasi_id      integer,                       -- baris ledger 'opname' yang dibuat (sak/stok jadi)
  berita_acara_foto  text,
  disaksikan_oleh    text,
  catatan            text,
  created_by         integer NOT NULL REFERENCES app_users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh    integer REFERENCES app_users(id),
  dibatalkan_pada    timestamptz,
  alasan_batal       text
);
CREATE INDEX IF NOT EXISTS ops_stock_opname_tgl_idx ON ops_stock_opname (jenis, tanggal DESC);

-- ---------- tutup hari (penanda kedisiplinan, tidak menahan apa pun) ----------
CREATE TABLE IF NOT EXISTS ops_tutup_hari (
  id              serial PRIMARY KEY,
  tanggal         date NOT NULL,
  ringkasan       jsonb NOT NULL,                    -- snapshot saldo + jumlah input hari itu
  catatan         text,
  created_by      integer NOT NULL REFERENCES app_users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  dibatalkan_oleh integer REFERENCES app_users(id),
  dibatalkan_pada timestamptz,
  alasan_batal    text
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_tutup_hari_tgl_uq ON ops_tutup_hari (tanggal) WHERE dibatalkan_pada IS NULL;

-- ---------- temuan audit A1-A10 ----------
CREATE TABLE IF NOT EXISTS ops_audit_temuan (
  id                   serial PRIMARY KEY,
  sidik                text NOT NULL,                -- kunci idempoten, mis. 'A1:lot:12'
  kode                 text NOT NULL CHECK (kode ~ '^A(10|[1-9])$'),
  tingkat              text NOT NULL CHECK (tingkat IN ('info','peringatan','flag')),
  ref_tabel            text,
  ref_id               integer,
  pesan                text NOT NULL,                -- P7: tidak pernah memuat nama PT/PO/harga/invoice
  detail               jsonb,
  usulan_potongan_sak  integer CHECK (usulan_potongan_sak IS NULL OR usulan_potongan_sak > 0),
  status               text NOT NULL DEFAULT 'terbuka' CHECK (status IN ('terbuka','ditutup','selesai_otomatis')),
  tanggal_audit        date NOT NULL,                -- pertama kali ditemukan
  terakhir_dilihat     date NOT NULL,                -- run terakhir yang masih menemukannya
  penjelasan           text,                         -- admin/kepala (A1: minta penjelasan tertulis)
  penjelasan_oleh      integer REFERENCES app_users(id),
  penjelasan_pada      timestamptz,
  ditutup_oleh         integer REFERENCES app_users(id),
  ditutup_pada         timestamptz,
  catatan_tutup        text,
  created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_audit_temuan_terbuka_uq ON ops_audit_temuan (sidik) WHERE status = 'terbuka';
CREATE INDEX IF NOT EXISTS ops_audit_temuan_status_idx ON ops_audit_temuan (status, kode);

-- ---------- A5: kas keluar tanpa foto nota dikecualikan dari HPP ----------
-- Baris otomatis (kategori upah/sak dibuat sistem dari upah harian / beli sak) tetap dihitung;
-- kas keluar manual tanpa nota dipisah ke kolom biaya_tanpa_nota supaya tetap terlihat.
CREATE OR REPLACE VIEW v_ops_hpp_bulanan AS
WITH kas AS (
  SELECT to_char(tanggal, 'YYYY-MM') AS bulan,
         sum(CASE WHEN foto_nota IS NOT NULL OR kategori IN ('upah','sak') THEN nominal ELSE 0 END) AS biaya_kas,
         sum(CASE WHEN foto_nota IS NULL AND kategori NOT IN ('upah','sak') THEN nominal ELSE 0 END) AS biaya_tanpa_nota
  FROM ops_kas_kecil
  WHERE jenis = 'keluar' AND dibatalkan_pada IS NULL
  GROUP BY to_char(tanggal, 'YYYY-MM')
), prod AS (
  SELECT to_char(tanggal, 'YYYY-MM') AS bulan, sum(jumlah_sak) AS sak
  FROM ops_produksi_sak
  WHERE dibatalkan_pada IS NULL AND status_qc = 'lolos'
  GROUP BY to_char(tanggal, 'YYYY-MM')
)
SELECT kas.bulan,
       kas.biaya_kas::numeric(14,2) AS biaya_kas,
       COALESCE(prod.sak, 0)::integer AS sak_lolos_qc,
       kas.biaya_tanpa_nota::numeric(14,2) AS biaya_tanpa_nota
FROM kas LEFT JOIN prod USING (bulan);

COMMIT;
