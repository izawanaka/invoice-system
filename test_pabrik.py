"""
test_pabrik.py -- uji workspace PABRIK (DESIGN-PABRIK.md). Dijalankan DI DALAM
container API:  docker exec -i invoice-api-prod python /app/test_pabrik.py

Gaya sama dengan test_invoice_flow.py: check(nama, kondisi) -> ringkasan PASS/FAIL.
Akun uji dibuat langsung di DB (bukan lewat UI) dan SELURUH jejaknya dihapus di
akhir (baris ops_* & app_audit_log milik akun uji, lalu akunnya) -- ini satu-satunya
tempat penghapusan akun dibenarkan: akun uji, data uji.

B1: peran admin/kepala, penjaga global (403 ke semua endpoint invoice), parameter
effective-dated, master pemasok/petak/karyawan.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path[:0] = ["/app/webapp", "/app"]
import settings  # noqa: E402,F401
import db_helper  # noqa: E402
import security  # noqa: E402

BASE = os.environ.get("PABRIK_TEST_BASE", "http://localhost:8000")
PASS = FAIL = 0
GAGAL = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        GAGAL.append(name)
        print(f"  FAIL  {name}  {detail}")


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


# ------------------------------------------------------------ akun uji
UJI = {"admin": "uji_admin_pabrik", "kepala": "uji_kepala_pabrik", "staff": "uji_staf_pabrik"}


def buat_akun_uji(conn):
    cur = conn.cursor()
    ids = {}
    for role, uname in UJI.items():
        cur.execute("SELECT id FROM app_users WHERE username=%s", (uname,))
        row = cur.fetchone()
        if row:
            ids[role] = row[0]
            continue
        cur.execute(
            "INSERT INTO app_users (email, username, password_hash, nama, role, aktif, login_via_google, password_aktif) "
            "VALUES (%s,%s,%s,%s,%s,true,false,false) RETURNING id",
            (uname + "@uji.local", uname, security.hash_password("UjiPabrik-2026!"), "Akun Uji " + role, role),
        )
        ids[role] = cur.fetchone()[0]
    conn.commit()
    return ids


def hapus_akun_uji(conn, ids):
    cur = conn.cursor()
    uid = list(ids.values())
    cur.execute("DELETE FROM ops_pemasok WHERE created_by = ANY(%s)", (uid,))
    cur.execute("DELETE FROM ops_petak WHERE created_by = ANY(%s)", (uid,))
    cur.execute("DELETE FROM ops_karyawan WHERE created_by = ANY(%s) OR user_id = ANY(%s)", (uid, uid))
    cur.execute("DELETE FROM ops_parameter WHERE created_by = ANY(%s)", (uid,))
    cur.execute("DELETE FROM app_audit_log WHERE user_id = ANY(%s)", (uid,))
    cur.execute("DELETE FROM app_users WHERE id = ANY(%s)", (uid,))
    conn.commit()


def token(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT email, role FROM app_users WHERE id=%s", (user_id,))
    email, role = cur.fetchone()
    return security.create_access_token(user_id, email, role)


def main():
    conn = db_helper.get_conn()
    ids = buat_akun_uji(conn)
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_users WHERE role='owner' AND aktif ORDER BY id LIMIT 1")
    owner_id = cur.fetchone()[0]
    t_owner = token(conn, owner_id)
    t_admin = token(conn, ids["admin"])
    t_kepala = token(conn, ids["kepala"])
    t_staf = token(conn, ids["staff"])
    owner_param_id = None
    try:
        print("== A. Peran & penjaga global (K1, K2, K3)")
        cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='app_users_role_check'")
        check("A1 CHECK role memuat admin & kepala", "'admin'" in cur.fetchone()[0])
        s, b = req("GET", "/ops/ping", t_admin)
        check("A2 admin boleh /ops/ping", s == 200 and b and b.get("workspace") == "PABRIK", (s, b))
        s, b = req("GET", "/ops/ping", t_kepala)
        check("A3 kepala boleh /ops/ping", s == 200 and b and b.get("role") == "kepala", (s, b))
        s, b = req("GET", "/ops/ping", t_staf)
        check("A4 staf invoice ditolak /ops (403)", s == 403, (s, b))
        s, b = req("GET", "/ops/ping", t_owner)
        check("A5 owner boleh /ops/ping", s == 200, (s, b))

        jalur_invoice = ["/invoices", "/po", "/bap", "/badan-usaha", "/users", "/mitra/groups",
                         "/faktur-pajak", "/resi", "/dokumen/cek", "/pembayaran/x"]
        for tok, nama in ((t_admin, "admin"), (t_kepala, "kepala")):
            semua = []
            for j in jalur_invoice:
                s, _ = req("GET", j, tok)
                semua.append((j, s))
            check(f"A6 {nama}: SEMUA endpoint invoice 403", all(s == 403 for _, s in semua), semua)
            s, _ = req("POST", "/po", tok, {"x": 1})
            check(f"A7 {nama}: POST /po 403 (bukan 422)", s == 403, s)
            s, b = req("GET", "/auth/me", tok)
            check(f"A8 {nama}: /auth/me tetap bisa", s == 200 and b.get("role") == nama, (s, b))

        print("== B. Parameter effective-dated (P9, P1)")
        s, b = req("GET", "/ops/parameter", t_kepala)
        kode = {p["kode"]: p for p in (b or [])} if s == 200 else {}
        check("B1 kepala baca parameter efektif (14 kode)", s == 200 and len(kode) == 14, (s, len(kode)))
        check("B2 kg_per_sak = 34", kode.get("kg_per_sak", {}).get("nilai") == 34.0, kode.get("kg_per_sak"))
        check("B3 sak_per_m3_kks masih None", "sak_per_m3_kks" in kode and kode["sak_per_m3_kks"]["nilai"] is None)
        s, _ = req("POST", "/ops/parameter", t_kepala, {"kode": "kg_per_sak", "nilai": 35, "berlaku_mulai": "2026-10-01"})
        check("B4 kepala TIDAK boleh ubah parameter (403)", s == 403, s)
        s, _ = req("POST", "/ops/parameter", t_admin, {"kode": "kg_per_sak", "nilai": 35, "berlaku_mulai": "2026-10-01"})
        check("B5 admin TIDAK boleh ubah parameter (403)", s == 403, s)
        s, b = req("POST", "/ops/parameter", t_owner, {"kode": "kg_per_sak", "nilai": 35, "berlaku_mulai": "2026-10-01",
                                                        "catatan": "UJI B1 - akan dihapus"})
        check("B6 owner tetapkan kg_per_sak=35 mulai 1 Okt (201)", s == 201, (s, b))
        owner_param_id = b.get("id") if s == 201 else None
        cur.execute("SELECT ops_param('kg_per_sak', DATE '2026-09-15'), ops_param('kg_per_sak', DATE '2026-10-02')")
        v_sep, v_okt = cur.fetchone()
        check("B7 nilai efektif Sep=34, Okt=35 (baris lama ditutup, bukan ditimpa)",
              float(v_sep) == 34 and float(v_okt) == 35, (v_sep, v_okt))
        s, _ = req("POST", "/ops/parameter", t_owner, {"kode": "kg_per_sak", "nilai": 33, "berlaku_mulai": "2026-09-20"})
        check("B8 mundur ke sebelum baris aktif ditolak (409)", s == 409, s)
        s, _ = req("POST", "/ops/parameter", t_owner, {"kode": "kode_ngawur", "nilai": 1, "berlaku_mulai": "2026-10-01"})
        check("B9 kode tidak dikenal ditolak (422)", s == 422, s)
        cur.execute("SELECT ops_pengali(0.9), ops_pengali(1), ops_pengali(3), ops_pengali(3.01), ops_pengali(5), ops_pengali(5.5)")
        check("B10 pengali klaim KSP: <1->1.0, 1-3->0.8, >3-5->0.5, >5->0",
              [float(x) for x in cur.fetchone()] == [1.0, 0.8, 0.8, 0.5, 0.5, 0.0])
        s, b = req("GET", "/ops/tarif-bonus", t_kepala)
        check("B11 kepala baca 4 jenjang tarif", s == 200 and len(b) == 4, (s, b))

        print("== C. Master pemasok / petak / karyawan")
        s, b = req("POST", "/ops/pemasok", t_kepala, {"nama": "Uji Pemasok Sabut", "jenis": "sabut"})
        check("C1 kepala buat pemasok (201) -- setara admin, tanpa flag", s == 201, (s, b))
        pid = b.get("id") if s == 201 else None
        s, _ = req("POST", "/ops/pemasok", t_admin, {"nama": "uji pemasok sabut", "jenis": "sabut"})
        check("C2 duplikat nama (case-insensitive) ditolak (409)", s == 409, s)
        s, b = req("PATCH", f"/ops/pemasok/{pid}", t_admin, {"aktif": False})
        check("C3 admin nonaktifkan pemasok (200)", s == 200 and b.get("aktif") is False, (s, b))
        s, b = req("GET", "/ops/pemasok?hanya_aktif=true", t_kepala)
        check("C4 hanya_aktif menyaring", s == 200 and all(p["id"] != pid for p in b), s)
        s, _ = req("POST", "/ops/petak", t_kepala, {"nomor": "uji-1"})
        check("C5 kepala TIDAK boleh buat petak (owner-only, 403)", s == 403, s)
        s, b = req("POST", "/ops/petak", t_owner, {"nomor": "uji-1", "panjang_m": 10, "lebar_m": 5, "tinggi_maks_m": 2})
        check("C6 owner buat petak, nomor di-upper (UJI-1)", s == 201 and b.get("nomor") == "UJI-1", (s, b))
        s, b = req("POST", "/ops/karyawan", t_owner, {"nama": "Uji Kepala", "peran": "kepala", "gaji_pokok": 8000000,
                                                       "uang_makan": 1000000, "user_id": ids["kepala"],
                                                       "berlaku_mulai": "2026-09-01"})
        check("C7 owner catat kepala gaji 8jt+1jt (201)", s == 201, (s, b))
        s, _ = req("POST", "/ops/karyawan", t_owner, {"nama": "Uji Kepala", "peran": "kepala", "gaji_pokok": 8500000,
                                                       "berlaku_mulai": "2026-09-01"})
        check("C8 baris karyawan tanggal sama/mundur ditolak (409)", s == 409, s)
        s, b = req("POST", "/ops/karyawan", t_owner, {"nama": "Uji Kepala", "peran": "kepala", "gaji_pokok": 8500000,
                                                       "berlaku_mulai": "2026-11-01"})
        cur.execute("SELECT berlaku_sampai FROM ops_karyawan WHERE lower(nama)='uji kepala' AND gaji_pokok=8000000")
        r = cur.fetchone()
        check("C9 kenaikan gaji = baris baru, baris lama ditutup 31 Okt",
              s == 201 and r and str(r[0]) == "2026-10-31", (s, r))
        s, _ = req("POST", "/ops/karyawan", t_owner, {"nama": "Uji Salah", "peran": "kepala", "user_id": ids["admin"],
                                                       "berlaku_mulai": "2026-09-01"})
        check("C10 kepala ditautkan ke akun non-kepala ditolak (422)", s == 422, s)
        s, _ = req("GET", "/ops/karyawan", t_kepala)
        check("C11 kepala tidak boleh baca daftar gaji (403) -- rekap miliknya menyusul B6", s == 403, s)
        cur.execute("SELECT count(*) FROM app_audit_log WHERE user_id = ANY(%s) AND aksi LIKE 'ops_%%'",
                    (list(ids.values()),))
        check("C12 tulisan admin/kepala tercatat di app_audit_log (P10)", cur.fetchone()[0] >= 2)

        print("== D. Invoice tidak tersentuh (K1)")
        cur.execute("SELECT count(*) FROM invoices")
        n_inv = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM purchase_orders")
        n_po = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM bap")
        n_bap = cur.fetchone()[0]
        s, b = req("GET", "/invoices", t_owner)
        check("D1 owner masih bisa /invoices, jumlah = DB", s == 200 and len(b) == n_inv, (s, n_inv))
        check("D2 tabel invoice utuh (PO/BAP/INV > 0)", n_po > 0 and n_bap > 0 and n_inv > 0, (n_po, n_bap, n_inv))
    finally:
        # bersihkan: parameter uji owner (baris 35) + buka kembali baris 34, lalu jejak akun uji
        if owner_param_id:
            cur.execute("DELETE FROM app_audit_log WHERE entity='ops_parameter' AND entity_id=%s", (str(owner_param_id),))
            cur.execute("DELETE FROM ops_parameter WHERE id=%s", (owner_param_id,))
            cur.execute("UPDATE ops_parameter SET berlaku_sampai=NULL WHERE kode='kg_per_sak' AND nilai=34 "
                        "AND dibatalkan_pada IS NULL")
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity IN ('ops_petak','ops_karyawan') "
                    "AND created_at > now() - interval '10 minutes' AND detail::text LIKE '%%Uji%%'", (owner_id,))
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity='ops_petak' "
                    "AND created_at > now() - interval '10 minutes' AND detail::text LIKE '%%uji-1%%'", (owner_id,))
        cur.execute("DELETE FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%'")
        cur.execute("DELETE FROM ops_petak WHERE nomor LIKE 'UJI-%%'")
        conn.commit()
        hapus_akun_uji(conn, ids)
        cur.execute("SELECT count(*) FROM app_users WHERE username LIKE 'uji_%%pabrik'")
        sisa = cur.fetchone()[0]
        conn.close()
        print(f"\n== bersih-bersih: akun uji tersisa = {sisa}")
    print(f"\n=== HASIL: {PASS} PASS / {FAIL} FAIL ===")
    if GAGAL:
        print("GAGAL:", GAGAL)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
