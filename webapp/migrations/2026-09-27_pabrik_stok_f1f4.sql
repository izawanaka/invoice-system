-- 2026-09-27_pabrik_stok_f1f4.sql -- polesan lapisan stok cocopeat (DESIGN-PABRIK Update 27 Sep 2026)
-- F1/F2: pagar saldo ledger di DB (kunci advisory + constraint trigger DEFERRED)
-- F4   : append-only 5 ledger di DB (tolak DELETE/TRUNCATE; UPDATE hanya pembatalan & isi tautan NULL)
-- Idempoten, satu transaksi. Rollback: 2026-09-27_pabrik_stok_f1f4_rollback.sql (JANGAN dijalankan otomatis).
BEGIN;
SET LOCAL search_path = public;

-- Kunci per ledger. Kelas & nomor SAMA dengan KUNCI_KELAS/KUNCI_LEDGER di routers/ops_operasional.py.
CREATE OR REPLACE FUNCTION ops_kunci_ledger(p_ledger text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF p_ledger = 'kas' THEN PERFORM pg_advisory_xact_lock(77301, 1);
    ELSIF p_ledger = 'sak' THEN PERFORM pg_advisory_xact_lock(77301, 2);
    ELSIF p_ledger = 'stok' THEN PERFORM pg_advisory_xact_lock(77301, 3);
    ELSE RAISE EXCEPTION 'ops_kunci_ledger: ledger tidak dikenal %', p_ledger;
    END IF;
END $$;

-- F2: saldo ledger tidak boleh negatif (P5), dicek saat COMMIT sesudah mengambil kunci ledger,
-- sehingga dua transaksi paralel tidak bisa sama-sama lolos.
CREATE OR REPLACE FUNCTION ops_cek_saldo_ledger() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_ledger text := TG_ARGV[0];
    v_saldo numeric;
BEGIN
    PERFORM ops_kunci_ledger(v_ledger);
    IF v_ledger = 'kas' THEN
        SELECT saldo INTO v_saldo FROM v_ops_saldo_kas;
    ELSIF v_ledger = 'sak' THEN
        SELECT saldo INTO v_saldo FROM v_ops_saldo_sak_kosong;
    ELSE
        SELECT saldo INTO v_saldo FROM v_ops_saldo_stok_jadi;
    END IF;
    IF v_saldo < 0 THEN
        RAISE EXCEPTION 'P5: saldo % menjadi % (tidak boleh negatif)', v_ledger, v_saldo
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;

-- F4: ledger append-only. Izin sesi ops.izinkan_hapus_uji='ya' HANYA berlaku di DB klon uji (bukan bisnis_izawa),
-- dipakai bersih-bersih test_pabrik.py. Keputusan owner 27 Sep 2026 (B1).
CREATE OR REPLACE FUNCTION ops_jaga_ledger() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    -- B1 (27 Sep 2026): izin uji TIDAK PERNAH berlaku di produksi (bisnis_izawa) -> append-only mutlak di sana.
    v_uji  boolean := current_database() <> 'bisnis_izawa' AND coalesce(current_setting('ops.izinkan_hapus_uji', true), '') = 'ya';
    v_boleh text[] := ARRAY['dibatalkan_oleh', 'dibatalkan_pada', 'alasan_batal'];
    v_ref  text;
    v_old  jsonb;
    v_new  jsonb;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF v_uji THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'P1: % append-only -- DELETE ditolak (id=%)', TG_TABLE_NAME, OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_uji THEN RETURN NEW; END IF;
    v_old := to_jsonb(OLD);
    v_new := to_jsonb(NEW);
    IF TG_NARGS > 0 THEN v_boleh := v_boleh || TG_ARGV; END IF;
    IF (v_new - v_boleh) IS DISTINCT FROM (v_old - v_boleh) THEN
        RAISE EXCEPTION 'P1: % append-only -- hanya pembatalan/tautan yang boleh diisi (id=%)', TG_TABLE_NAME, OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF (v_old ->> 'dibatalkan_pada') IS NOT NULL AND (
           v_new -> 'dibatalkan_pada' IS DISTINCT FROM v_old -> 'dibatalkan_pada'
        OR v_new -> 'dibatalkan_oleh' IS DISTINCT FROM v_old -> 'dibatalkan_oleh'
        OR v_new -> 'alasan_batal'    IS DISTINCT FROM v_old -> 'alasan_batal') THEN
        RAISE EXCEPTION 'P1: % id=% sudah dibatalkan -- tidak bisa diubah atau dibuka lagi', TG_TABLE_NAME, OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_NARGS > 0 THEN
        FOREACH v_ref IN ARRAY TG_ARGV LOOP
            IF (v_old ->> v_ref) IS NOT NULL AND v_new -> v_ref IS DISTINCT FROM v_old -> v_ref THEN
                RAISE EXCEPTION 'P1: % id=% tautan % sudah terisi -- tidak boleh diganti', TG_TABLE_NAME, OLD.id, v_ref
                    USING ERRCODE = 'check_violation';
            END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION ops_tolak_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_database() <> 'bisnis_izawa' AND coalesce(current_setting('ops.izinkan_hapus_uji', true), '') = 'ya' THEN RETURN NULL; END IF;
    RAISE EXCEPTION 'P1: % append-only -- TRUNCATE ditolak', TG_TABLE_NAME USING ERRCODE = 'check_violation';
END $$;

-- F2 triggers
DROP TRIGGER IF EXISTS trg_ops_saldo_kas  ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_saldo_sak  ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_saldo_stok ON ops_stok_jadi_mutasi;
CREATE CONSTRAINT TRIGGER trg_ops_saldo_kas  AFTER INSERT OR UPDATE ON ops_kas_kecil
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ops_cek_saldo_ledger('kas');
CREATE CONSTRAINT TRIGGER trg_ops_saldo_sak  AFTER INSERT OR UPDATE ON ops_sak_kosong_mutasi
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ops_cek_saldo_ledger('sak');
CREATE CONSTRAINT TRIGGER trg_ops_saldo_stok AFTER INSERT OR UPDATE ON ops_stok_jadi_mutasi
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ops_cek_saldo_ledger('stok');

-- F4 triggers (argumen = kolom tautan yang boleh diisi sekali dari NULL)
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_stok_jadi_mutasi;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_produksi_sak;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_jaga ON ops_stock_opname;
CREATE TRIGGER trg_ops_jaga BEFORE UPDATE OR DELETE ON ops_sak_kosong_mutasi FOR EACH ROW EXECUTE FUNCTION ops_jaga_ledger();
CREATE TRIGGER trg_ops_jaga BEFORE UPDATE OR DELETE ON ops_stok_jadi_mutasi  FOR EACH ROW EXECUTE FUNCTION ops_jaga_ledger();
CREATE TRIGGER trg_ops_jaga BEFORE UPDATE OR DELETE ON ops_produksi_sak      FOR EACH ROW EXECUTE FUNCTION ops_jaga_ledger();
CREATE TRIGGER trg_ops_jaga BEFORE UPDATE OR DELETE ON ops_kas_kecil         FOR EACH ROW EXECUTE FUNCTION ops_jaga_ledger('ref_sak_mutasi_id');
CREATE TRIGGER trg_ops_jaga BEFORE UPDATE OR DELETE ON ops_stock_opname      FOR EACH ROW EXECUTE FUNCTION ops_jaga_ledger('ref_mutasi_id');

DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_sak_kosong_mutasi;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_stok_jadi_mutasi;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_produksi_sak;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_kas_kecil;
DROP TRIGGER IF EXISTS trg_ops_tolak_truncate ON ops_stock_opname;
CREATE TRIGGER trg_ops_tolak_truncate BEFORE TRUNCATE ON ops_sak_kosong_mutasi FOR EACH STATEMENT EXECUTE FUNCTION ops_tolak_truncate();
CREATE TRIGGER trg_ops_tolak_truncate BEFORE TRUNCATE ON ops_stok_jadi_mutasi  FOR EACH STATEMENT EXECUTE FUNCTION ops_tolak_truncate();
CREATE TRIGGER trg_ops_tolak_truncate BEFORE TRUNCATE ON ops_produksi_sak      FOR EACH STATEMENT EXECUTE FUNCTION ops_tolak_truncate();
CREATE TRIGGER trg_ops_tolak_truncate BEFORE TRUNCATE ON ops_kas_kecil         FOR EACH STATEMENT EXECUTE FUNCTION ops_tolak_truncate();
CREATE TRIGGER trg_ops_tolak_truncate BEFORE TRUNCATE ON ops_stock_opname      FOR EACH STATEMENT EXECUTE FUNCTION ops_tolak_truncate();

-- Verifikasi di dalam transaksi: 3 + 5 + 5 trigger, dan saldo saat ini tidak negatif.
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM pg_trigger
     WHERE NOT tgisinternal AND tgname IN ('trg_ops_saldo_kas','trg_ops_saldo_sak','trg_ops_saldo_stok','trg_ops_jaga','trg_ops_tolak_truncate');
    IF n <> 13 THEN RAISE EXCEPTION 'verifikasi gagal: trigger % (harus 13)', n; END IF;
    IF (SELECT saldo FROM v_ops_saldo_kas) < 0 OR (SELECT saldo FROM v_ops_saldo_sak_kosong) < 0
       OR (SELECT saldo FROM v_ops_saldo_stok_jadi) < 0 THEN
        RAISE EXCEPTION 'verifikasi gagal: ada saldo negatif sebelum pagar dipasang';
    END IF;
END $$;
COMMIT;
