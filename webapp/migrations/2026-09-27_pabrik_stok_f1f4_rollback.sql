-- ROLLBACK 2026-09-27_pabrik_stok_f1f4.sql -- JANGAN dijalankan otomatis; hanya atas keputusan owner.
-- Hanya mencabut pagar (trigger & fungsi). Tidak menyentuh data.
BEGIN;
SET LOCAL search_path = public;
DROP TRIGGER IF EXISTS trg_ops_saldo_kas  ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_saldo_sak  ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_saldo_stok ON ops_stok_jadi_mutasi;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_stok_jadi_mutasi;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_produksi_sak;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_stock_opname;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_stok_jadi_mutasi;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_produksi_sak;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_stock_opname;
DROP FUNCTION IF EXISTS ops_cek_saldo_ledger();
DROP FUNCTION IF EXISTS ops_jaga_ledger();
DROP FUNCTION IF EXISTS ops_tolak_truncate();
DROP FUNCTION IF EXISTS ops_kunci_ledger(text);
COMMIT;
