"""
test_pabrik.py -- uji workspace PABRIK (DESIGN-PABRIK.md). Dijalankan DI DALAM
container API:  docker exec -i invoice-api-prod python /app/test_pabrik.py

Gaya sama dengan test_invoice_flow.py: check(nama, kondisi) -> ringkasan PASS/FAIL.
Akun uji dibuat langsung di DB (bukan lewat UI) dan SELURUH jejaknya dihapus di
akhir (baris ops_* & app_audit_log milik akun uji, lalu akunnya) -- ini satu-satunya
tempat penghapusan akun dibenarkan: akun uji, data uji.

B1: peran admin/kepala, penjaga global (403 ke semua endpoint invoice), parameter
effective-dated, master pemasok/petak/karyawan.
B2-B4 (uji E): lot/tahap, terima truk, produksi atomik, sak kosong, kas kecil, upah, cuaca.
B7 (uji G): stock opname (owner), tutup hari, audit A1-A10 (idempoten, penjelasan, tutup, terima potongan).
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
    g_mulai = None
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


        print("== E. Operasional B2-B4 (P3, P4, P5, P6, K7, K9)")  # PABRIK_B2_9SEP2026
        s, b = req("POST", "/ops/petak", t_owner, {"nomor": "uji-2", "panjang_m": 8, "lebar_m": 4, "tinggi_maks_m": 2})
        petak2 = b.get("id") if s == 201 else None
        check("E1 owner buat petak UJI-2", s == 201, (s, b))
        s, b = req("POST", "/ops/lot", t_kepala, {"petak_id": petak2, "tanggal_buka": "2026-09-01"})
        lot_id = b.get("lot_id") if s == 201 else None
        check("E2 kepala buka lot (curah, nomor 2026-NNN)", s == 201 and b.get("status") == "curah" and str(b.get("nomor_lot", "")).startswith("2026-"), (s, b))
        s, _ = req("POST", "/ops/lot", t_admin, {"petak_id": petak2, "tanggal_buka": "2026-09-02"})
        check("E3 lot kedua di petak sama ditolak (P6, 409)", s == 409, s)
        s, b = req("POST", "/ops/pemasok", t_kepala, {"nama": "UJI Sabut", "jenis": "sabut"})
        pm_sabut = b.get("id")
        s2, b2 = req("POST", "/ops/pemasok", t_kepala, {"nama": "UJI Sak", "jenis": "sak"})
        pm_sak = b2.get("id")
        check("E4 pemasok sabut & sak dibuat", s == 201 and s2 == 201, (s, s2))
        truk = {"tanggal": "2026-09-02", "jam": "08:30", "nopol": "DC 1234 AB", "pemasok_id": pm_sabut,
                "p_m": 4, "l_m": 2, "t_m": 1.5, "lot_id": lot_id}
        s, b = req("POST", "/ops/penerimaan", t_admin, truk)
        check("E5 terima truk: kubik dihitung server = 12.0 (P3), nopol dinormalkan", s == 201 and b.get("kubik_masuk") == 12.0 and b.get("nopol") == "DC1234AB", (s, b))
        s, _ = req("POST", "/ops/penerimaan", t_kepala, truk)
        check("E6 truk duplikat nopol+tanggal+jam ditolak (409)", s == 409, s)
        s, b = req("POST", "/ops/penerimaan", t_kepala, {**truk, "jam": "10:00", "p_m": 2, "l_m": 2, "t_m": 2})
        check("E7 truk kedua kubik 8.0", s == 201 and b.get("kubik_masuk") == 8.0, (s, b))
        s, b = req("GET", "/ops/lot?hanya_aktif=true", t_kepala)
        lot_row = next((x for x in (b or []) if x["lot_id"] == lot_id), {})
        check("E8 lot ringkas: kubik masuk 20.0, sisa WIP estimasi 20.0", lot_row.get("kubik_masuk") == 20.0 and lot_row.get("sisa_wip_estimasi_kubik") == 20.0, lot_row)
        s, _ = req("POST", f"/ops/lot/{lot_id}/tahap", t_kepala, {"tahap": "jemur", "tanggal_mulai": "2026-09-03"})
        check("E9 tahap lompat curah->jemur ditolak (422, K9 maju satu langkah)", s == 422, s)
        s, _ = req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-03", "lot_id": lot_id, "jumlah_sak": 5})
        check("E10 produksi di lot tahap curah ditolak (409)", s == 409, s)
        ok = True
        for th, tg in (("giling", "2026-09-03"), ("basah", "2026-09-04"), ("jemur", "2026-09-05"), ("siap_karung", "2026-09-08")):
            s, b = req("POST", f"/ops/lot/{lot_id}/tahap", t_admin, {"tahap": th, "tanggal_mulai": tg})
            ok = ok and s == 200 and b.get("status") == th
        s, _ = req("POST", "/ops/penerimaan", t_kepala, {**truk, "jam": "11:00"})
        check("E11 tahap giling->basah->jemur->siap_karung; truk ke lot non-curah ditolak 409", ok and s == 409, (ok, s))
        s, _ = req("POST", "/ops/kas", t_admin, {"tanggal": "2026-09-08", "jenis": "keluar", "kategori": "bbm", "nominal": 50000, "keterangan": "UJI bbm"})
        check("E12 kas keluar saat saldo 0 ditolak (P5, 409)", s == 409, s)
        s, _ = req("POST", "/ops/kas", t_kepala, {"tanggal": "2026-09-08", "jenis": "isi_ulang", "nominal": 5000000, "keterangan": "UJI"})
        check("E13 kepala isi ulang kas ditolak (403, owner saja)", s == 403, s)
        s, b = req("POST", "/ops/kas", t_owner, {"tanggal": "2026-09-08", "jenis": "isi_ulang", "nominal": 5000000, "keterangan": "UJI isi ulang"})
        kas_isi_id = b.get("id") if s == 201 else None
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("E14 owner isi ulang 5 jt -> saldo kas 5.000.000", s == 201 and sal.get("kas") == 5000000.0, (s, sal))
        s, b = req("POST", "/ops/sak", t_admin, {"tanggal": "2026-09-08", "jenis": "beli", "jumlah": 100, "pemasok_id": pm_sak, "harga_per_sak": 2000, "keterangan": "UJI"})
        s2, sal = req("GET", "/ops/saldo", t_admin)
        check("E15 beli 100 sak @2000: sak 100, kas 4.800.000 (otomatis kas keluar)", s == 201 and sal.get("sak_kosong") == 100 and sal.get("kas") == 4800000.0, (s, sal))
        s, b = req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-09", "lot_id": lot_id, "jumlah_sak": 20, "berat_sampel": [34, 33.5, 35, 34.2, 33.8]})
        prod_id = b.get("id") if s == 201 else None
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("E16 produksi 20 sak (P4): qc 'belum' (param kosong), sak 80, stok jadi 20", s == 201 and b.get("status_qc") == "belum" and sal.get("sak_kosong") == 80 and sal.get("stok_jadi") == 20, (s, b, sal))
        s, _ = req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-09", "lot_id": lot_id, "jumlah_sak": 500})
        check("E17 produksi melebihi sak kosong ditolak (P5, 409)", s == 409, s)
        s, _ = req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-09", "lot_id": lot_id, "jumlah_sak": 3, "berat_sampel": [1, 2]})
        check("E18 sampel bukan 5 angka ditolak (422)", s == 422, s)
        s, _ = req("POST", "/ops/sak", t_kepala, {"tanggal": "2026-09-09", "jenis": "rusak", "jumlah": 10, "keterangan": "UJI robek"})
        s2, _ = req("POST", "/ops/sak", t_kepala, {"tanggal": "2026-09-09", "jenis": "retur", "jumlah": 5, "keterangan": "UJI"})
        s3, _ = req("POST", "/ops/sak", t_kepala, {"tanggal": "2026-09-09", "jenis": "retur", "jumlah": 20})
        s4, sal = req("GET", "/ops/saldo", t_kepala)
        check("E19 rusak 10 -> sak 70; retur 5 -> menunggu retur 5; retur 20 ditolak 409", s == 201 and s2 == 201 and s3 == 409 and sal.get("sak_kosong") == 70 and sal.get("sak_rusak_belum_retur") == 5, (s, s2, s3, sal))
        s, _ = req("POST", "/ops/upah", t_admin, {"tanggal": "2026-09-09", "nama": "UJI Buruh", "peran": "buruh", "satuan": "hari", "jumlah": 2})
        check("E20 upah tanpa tarif & parameter kosong ditolak (422)", s == 422, s)
        s, b = req("POST", "/ops/upah", t_admin, {"tanggal": "2026-09-09", "nama": "UJI Buruh", "peran": "buruh", "satuan": "hari", "jumlah": 2, "tarif": 150000})
        upah_id = b.get("id") if s == 201 else None
        s2, sal = req("GET", "/ops/saldo", t_admin)
        check("E21 upah 2 hari x 150rb = 300rb -> kas 4.500.000 (K7)", s == 201 and b.get("total") == 300000.0 and sal.get("kas") == 4500000.0, (s, b, sal))
        s, b = req("POST", f"/ops/upah/{upah_id}/batal", t_kepala, {"alasan": "UJI salah input"})
        s2, sal = req("GET", "/ops/saldo", t_admin)
        check("E22 batal upah (P1: tandai, bukan hapus) -> kas kembali 4.800.000", s == 200 and b.get("dibatalkan") is True and sal.get("kas") == 4800000.0, (s, sal))
        s, b = req("POST", f"/ops/lot/{lot_id}/tahap", t_kepala, {"tahap": "habis", "tanggal_mulai": "2026-09-09"})
        check("E23 lot habis: status habis, rendemen final 20 sak / 20 kubik = 1.0", s == 200 and b.get("status") == "habis" and b.get("rendemen") == 1.0, (s, b))
        cur.execute("SELECT detail FROM app_audit_log WHERE entity='ops_lot' AND entity_id=%s AND aksi='ops_lot_tahap' ORDER BY id DESC LIMIT 1", (str(lot_id),))
        det = cur.fetchone()[0]
        det = json.loads(det) if isinstance(det, str) else det
        check("E24 audit lot habis mencatat rendemen di luar kisaran (1.0 < 2.25)", det.get("rendemen_di_luar_kisaran") is True, det)
        s, _ = req("POST", "/ops/penerimaan", t_kepala, {**truk, "jam": "12:00"})
        check("E25 truk ke lot habis ditolak (P6, 409)", s == 409, s)
        s, b = req("POST", "/ops/lot", t_kepala, {"petak_id": petak2, "tanggal_buka": "2026-09-10"})
        lot2 = b.get("lot_id") if s == 201 else None
        check("E26 setelah habis, petak boleh buka lot baru", s == 201, (s, b))
        s, b = req("POST", f"/ops/produksi/{prod_id}/batal", t_kepala, {"alasan": "UJI salah hitung"})
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("E27 batal produksi membalik 3 baris: sak 90, stok jadi 0", s == 200 and sal.get("sak_kosong") == 90 and sal.get("stok_jadi") == 0, (s, sal))
        s, b = req("POST", "/ops/sak", t_kepala, {"tanggal": "2026-09-09", "jenis": "opname", "jumlah": 0, "opname_saldo_fisik": 85, "keterangan": "UJI opname"})
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("E28 opname fisik 85 -> delta -5, saldo 85", s == 201 and b.get("delta") == -5 and sal.get("sak_kosong") == 85, (s, b, sal))
        s, _ = req("POST", "/ops/cuaca", t_admin, {"tanggal": "2026-09-09", "hujan_mm": 12.5, "cuaca_teks": "hujan sore", "catatan": "UJI"})
        s2, _ = req("POST", "/ops/cuaca", t_kepala, {"tanggal": "2026-09-09", "hujan_mm": 14, "cuaca_teks": "hujan sore", "catatan": "UJI"})
        s3, b = req("GET", "/ops/cuaca?hari=30", t_kepala)
        n_uji = sum(1 for c in (b or []) if c["tanggal"] == "2026-09-09" and c["sumber"] == "manual")
        check("E29 cuaca manual upsert per tanggal (1 baris, nilai terakhir 14 mm)", s == 201 and s2 == 201 and n_uji == 1 and any(c["hujan_mm"] == 14.0 for c in b if c["sumber"] == "manual"), (s, s2, n_uji))
        s, _ = req("GET", "/ops/hpp", t_kepala)
        s2, b = req("GET", "/ops/hpp", t_owner)
        check("E30 HPP: kepala 403, owner 200", s == 403 and s2 == 200, (s, s2))
        s, _ = req("GET", "/ops/saldo", t_staf)
        check("E31 staf invoice tidak bisa baca saldo pabrik (403)", s == 403, s)


        print("== F. Pengiriman, BAP versi pabrik (P7), klaim, bonus Konsep B (K5), bekukan (P8)")  # PABRIK_B5_9SEP2026
        from routers.ops_bonus import hitung_jenjang, KOLOM_TERLARANG
        cur.execute("SELECT sak_dari, sak_sampai, tarif_per_sak FROM ops_tarif_bonus WHERE dibatalkan_pada IS NULL ORDER BY jenjang")
        tarif = cur.fetchall()
        check("F1 hitung_jenjang KSP: 5300->2.2jt, 6500->6jt(cap), 4500->0, 4501->2000",
              hitung_jenjang(5300, tarif, 6000000) == 2200000 and hitung_jenjang(6500, tarif, 6000000) == 6000000
              and hitung_jenjang(4500, tarif, 6000000) == 0 and hitung_jenjang(4501, tarif, 6000000) == 2000)
        ok = True
        for th, tg in (("giling", "2026-09-10"), ("basah", "2026-09-10"), ("jemur", "2026-09-10"), ("siap_karung", "2026-09-10")):
            s, _ = req("POST", f"/ops/lot/{lot2}/tahap", t_admin, {"tahap": th, "tanggal_mulai": tg})
            ok = ok and s == 200
        s, b = req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-10", "lot_id": lot2, "jumlah_sak": 30})
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("F2 lot2 siap karung, produksi 30 -> stok jadi 30, sak 55", ok and s == 201 and sal.get("stok_jadi") == 30 and sal.get("sak_kosong") == 55, (ok, s, sal))
        cur.execute("SELECT id, total_qty, tgl_bap FROM bap WHERE lower(satuan)='kg' ORDER BY id DESC LIMIT 1")
        bap_kg = cur.fetchone()
        bulan_bap = bap_kg[2].strftime("%Y-%m")
        tgl_bap = bap_kg[2].isoformat()
        s, _ = req("POST", "/ops/pengiriman", t_admin, {"tanggal": tgl_bap, "no_surat_jalan": "UJI-SJ-1", "jumlah_sak": 40, "tujuan_kode": "t1"})
        check("F3 kirim 40 > stok 30 ditolak (P5, 409)", s == 409, s)
        s, b = req("POST", "/ops/pengiriman", t_admin, {"tanggal": tgl_bap, "no_surat_jalan": "UJI-SJ-1", "jumlah_sak": 25, "tujuan_kode": "t1", "catatan": "UJI"})
        sj1 = b.get("id") if s == 201 else None
        s2, sal = req("GET", "/ops/saldo", t_kepala)
        check("F4 kirim 25 sak SJ UJI-SJ-1 tujuan T1 -> stok jadi 5", s == 201 and b.get("tujuan_kode") == "T1" and sal.get("stok_jadi") == 5, (s, b, sal))
        s, b = req("GET", "/ops/bap-pabrik", t_kepala)
        keys = set(b[0].keys()) if s == 200 and b else set()
        check("F5 kepala baca BAP versi pabrik: 200, TANPA kolom terlarang (P7)", s == 200 and keys and not (keys & KOLOM_TERLARANG), (s, keys))
        s, _ = req("GET", "/ops/bap-pilihan", t_kepala)
        s2, _ = req("GET", "/ops/rasio-kks", t_kepala)
        check("F6 kepala dilarang /bap-pilihan & /rasio-kks (403)", s == 403 and s2 == 403, (s, s2))
        s, _ = req("POST", f"/ops/pengiriman/{sj1}/tautkan-bap", t_kepala, {"bap_id": bap_kg[0]})
        check("F7 kepala tautkan BAP ditolak (403, owner saja)", s == 403, s)
        s, b = req("POST", f"/ops/pengiriman/{sj1}/tautkan-bap", t_owner, {"bap_id": bap_kg[0]})
        s2, bp = req("GET", f"/ops/bap-pabrik?bulan={bulan_bap}", t_kepala)
        row = next((x for x in (bp or []) if x["pengiriman_id"] == sj1), {})
        check("F8 owner tautkan BAP -> kepala melihat no_bap & qty, tanpa badan usaha", s == 200 and b.get("bap_tertaut") is True and row.get("no_bap") and "badan_usaha" not in row, (s, row))
        s, _ = req("POST", f"/ops/pengiriman/{sj1}/batal", t_kepala, {"alasan": "UJI"})
        check("F9 pengiriman tertaut BAP tidak bisa dibatalkan (409)", s == 409, s)
        s, _ = req("POST", "/ops/klaim", t_kepala, {"tanggal_terima": tgl_bap, "pengiriman_id": sj1, "jumlah_sak_diklaim": 3, "jenis": "mutu"})
        check("F10 kepala catat klaim ditolak (403, owner)", s == 403, s)
        s, b = req("POST", "/ops/klaim", t_owner, {"tanggal_terima": tgl_bap, "pengiriman_id": sj1, "jumlah_sak_diklaim": 3, "jenis": "mutu", "keterangan": "UJI klaim"})
        klaim_id = b.get("id") if s == 201 else None
        check("F11 klaim mutu 3 sak -> potongan 6 (2x) di bulan BAP", s == 201 and b.get("potongan_sak") == 6 and b.get("bulan_potongan") == bulan_bap, (s, b))
        cur.execute("SELECT id FROM ops_karyawan WHERE lower(nama)='uji kepala' AND user_id=%s", (ids["kepala"],))
        kar_id = cur.fetchone()[0]
        s, b = req("GET", f"/ops/bonus/rekap?bulan={bulan_bap}&karyawan_id={kar_id}", t_owner)
        rk = b[0] if s == 200 and b else {}
        sak_bap_exp = int(round(float(bap_kg[1]) / 34))
        check("F12 rekap owner: sak_bap = qty/34, potongan 6, sak_dikirim 25, pct klaim 12 -> pengali 0, bonus 0",
              s == 200 and rk.get("sak_bap") == sak_bap_exp and rk.get("potongan") == 6 and rk.get("sak_dikirim") == 25
              and rk.get("pct_klaim") == 12.0 and rk.get("pengali") == 0.0 and rk.get("bonus_bulan") == 0.0 and rk.get("status") == "draft", (s, rk, sak_bap_exp))
        s, b = req("GET", f"/ops/bonus/rekap?bulan={bulan_bap}", t_kepala)
        check("F13 kepala baca rekap miliknya (200, 1 baris)", s == 200 and len(b) == 1 and b[0]["karyawan_id"] == kar_id, (s, b))
        s, _ = req("POST", "/ops/potongan", t_owner, {"bulan": bulan_bap, "sebab": "manual", "sak": sak_bap_exp + 50, "keterangan": "UJI carry over"})
        s2, b = req("GET", f"/ops/bonus/rekap?bulan={bulan_bap}&karyawan_id={kar_id}", t_owner)
        rk = b[0] if s2 == 200 and b else {}
        check("F14 potongan > sak_bap -> sak_netto 0, sisa_negatif 56", s == 201 and rk.get("sak_netto") == 0 and rk.get("sisa_negatif") == 56, (s, rk))
        s, _ = req("POST", f"/ops/bonus/rekap/{bulan_bap}/{kar_id}/bekukan", t_kepala)
        check("F15 kepala bekukan ditolak (403)", s == 403, s)
        s, b = req("POST", f"/ops/bonus/rekap/{bulan_bap}/{kar_id}/bekukan", t_owner)
        s2, _ = req("POST", f"/ops/bonus/rekap/{bulan_bap}/{kar_id}/bekukan", t_owner)
        nb = f"{int(bulan_bap[:4]) + (int(bulan_bap[5:]) // 12)}-{(int(bulan_bap[5:]) % 12) + 1:02d}"
        cur.execute("SELECT sak FROM ops_potongan WHERE bulan=%s AND sebab='carry_over' AND ref_id=%s AND dibatalkan_pada IS NULL", (nb, kar_id))
        co = cur.fetchone()
        check("F16 owner bekukan (P8): status dibekukan, kedua kali 409, carry_over 56 ke bulan berikut", s == 200 and b.get("status") == "dibekukan" and s2 == 409 and co and co[0] == 56, (s, s2, co))
        s, b = req("POST", "/ops/pengiriman", t_admin, {"tanggal": tgl_bap, "no_surat_jalan": "UJI-SJ-2", "jumlah_sak": 5, "tujuan_kode": "T2", "catatan": "UJI"})
        sj2 = b.get("id")
        s2, _ = req("POST", f"/ops/pengiriman/{sj2}/tautkan-bap", t_owner, {"bap_id": bap_kg[0]})
        s3, _ = req("POST", f"/ops/klaim/{klaim_id}/batal", t_owner, {"alasan": "UJI"})
        s4, _ = req("POST", "/ops/potongan", t_owner, {"bulan": bulan_bap, "sebab": "manual", "sak": 1, "keterangan": "UJI tolak"})
        check("F17 setelah dibekukan: taut BAP bulan itu 409, batal klaim 409, potongan baru 409", s == 201 and s2 == 409 and s3 == 409 and s4 == 409, (s, s2, s3, s4))
        q = (int(bulan_bap[5:]) - 1) // 3 + 1
        s, b = req("GET", f"/ops/bonus/triwulan?periode={bulan_bap[:4]}-Q{q}", t_kepala)
        s2, b2 = req("POST", "/ops/bonus/triwulan/bayar", t_owner, {"periode": f"{bulan_bap[:4]}-Q{q}", "karyawan_id": kar_id, "tanggal_bayar": "2026-10-15"})
        check("F18 triwulan: kepala lihat miliknya (1 bulan beku), bayar ditolak 409 (baru 1 dari 3)", s == 200 and len(b) == 1 and b[0]["total_dibekukan"] == 0.0 and s2 == 409, (s, b, s2))
        s, b = req("GET", f"/ops/bonus/rekap?bulan={bulan_bap}&karyawan_id={kar_id}", t_owner)
        check("F19 rekap beku dibaca apa adanya, tidak dihitung ulang (P8)", s == 200 and b[0]["status"] == "dibekukan" and b[0]["sisa_negatif"] == 56, (s, b))
        s, b = req("GET", "/ops/rasio-kks", t_owner)
        check("F20 rasio KKS owner 200, parameter_saat_ini None", s == 200 and b.get("parameter_saat_ini") is None, (s, b))


        print("== G. Stock opname, tutup hari, audit A1-A10 (B7)")  # PABRIK_B7_9SEP2026
        from datetime import date as _date, timedelta as _td
        cur.execute("SELECT now()")
        g_mulai = cur.fetchone()[0]
        _y, _m = int(bulan_bap[:4]), int(bulan_bap[5:])
        tgl_opname = (_date(_y, _m, 1) - _td(days=1)).isoformat()  # bulan sebelum bulan_bap (rekapnya sudah beku)
        s, _ = req("POST", "/ops/opname", t_kepala, {"tanggal": tgl_opname, "jenis": "sak_kosong", "nilai_terukur": 10})
        check("G1 kepala stock opname ditolak (403, owner saja)", s == 403, s)
        req("POST", "/ops/produksi", t_kepala, {"tanggal": "2026-09-10", "lot_id": lot2, "jumlah_sak": 5})  # stok jadi utk G3/G6
        s0, sal0 = req("GET", "/ops/saldo", t_owner)
        sk0, sj0 = sal0.get("sak_kosong"), sal0.get("stok_jadi")
        s, b = req("POST", "/ops/opname", t_owner, {"tanggal": tgl_opname, "jenis": "sak_kosong", "nilai_terukur": sk0 - 3, "disaksikan_oleh": "UJI saksi", "catatan": "UJI opname sak"})
        op_sak = b.get("id") if s == 201 else None
        s2, sal = req("GET", "/ops/saldo", t_owner)
        cur.execute("SELECT jenis, delta FROM ops_sak_kosong_mutasi WHERE id=%s", (b.get("ref_mutasi_id") or 0,))
        mut = cur.fetchone()
        check("G2 opname sak kosong fisik-3: selisih -3, ledger 'opname' delta -3, saldo turun 3 (P2)",
              s == 201 and b.get("selisih") == -3.0 and b.get("nilai_sistem") == float(sk0) and mut == ("opname", -3) and sal.get("sak_kosong") == sk0 - 3, (s, b, mut, sal))
        s, b = req("POST", "/ops/opname", t_owner, {"tanggal": tgl_opname, "jenis": "stok_jadi", "nilai_terukur": sj0, "catatan": "UJI opname stok"})
        check("G3 opname stok jadi cocok: selisih 0, tanpa ledger (ref_mutasi_id None)", s == 201 and b.get("selisih") == 0.0 and b.get("ref_mutasi_id") is None, (s, b))
        s, b = req("POST", "/ops/opname", t_owner, {"tanggal": tgl_opname, "jenis": "petak", "objek_id": lot2, "nilai_terukur": 1.5, "catatan": "UJI opname petak"})
        s2, _ = req("POST", "/ops/opname", t_owner, {"tanggal": tgl_opname, "jenis": "petak", "objek_id": lot_id, "nilai_terukur": 1})
        s3, _ = req("POST", "/ops/opname", t_owner, {"tanggal": "2099-01-01", "jenis": "stok_jadi", "nilai_terukur": 1})
        check("G4 opname petak lot aktif dicatat (K9, tanpa ledger); lot habis 409; tanggal depan 422",
              s == 201 and b.get("objek") and b.get("ref_mutasi_id") is None and s2 == 409 and s3 == 422, (s, b, s2, s3))
        hari_ini = _date.today().isoformat()
        s, b = req("POST", "/ops/tutup-hari", t_admin, {"tanggal": hari_ini, "catatan": "UJI tutup"})
        th_id = b.get("id") if s == 201 else None
        s2, _ = req("POST", "/ops/tutup-hari", t_kepala, {"tanggal": hari_ini})
        s3, _ = req("POST", "/ops/tutup-hari", t_kepala, {"tanggal": "2099-01-01"})
        s4, rg = req("GET", "/ops/tutup-hari/ringkasan", t_kepala)
        check("G5 admin tutup hari (201, ringkasan ada saldo); kepala tutup lagi 409; hari depan 422; ringkasan sudah_ditutup",
              s == 201 and "saldo_kas" in b.get("ringkasan", {}) and s2 == 409 and s3 == 422 and s4 == 200 and rg.get("sudah_ditutup") is True, (s, s2, s3, s4, rg))
        s, _ = req("POST", "/ops/kas", t_owner, {"tanggal": "2026-09-08", "jenis": "isi_ulang", "nominal": 100000, "keterangan": "UJI isi ulang 2"})
        s, b = req("POST", "/ops/kas", t_admin, {"tanggal": "2026-09-09", "jenis": "keluar", "kategori": "bbm", "nominal": 40000, "keterangan": "UJI bbm tanpa nota"})
        kas_tanpa_nota = b.get("id") if s == 201 else None
        tgl_lama = (_date.today() - _td(days=40)).isoformat()
        s2, b2 = req("POST", "/ops/pengiriman", t_admin, {"tanggal": tgl_lama, "no_surat_jalan": "UJI-SJ-LAMA", "jumlah_sak": 2, "tujuan_kode": "T3", "catatan": "UJI"})
        sj_lama = b2.get("id") if s2 == 201 else None
        check("G6 persiapan audit: kas keluar tanpa nota (201), SJ 40 hari lalu belum tertaut (201)", s == 201 and s2 == 201, (s, b, s2, b2))
        s, _ = req("POST", "/ops/audit/jalankan?kirim=false", t_admin)
        check("G7 admin jalankan audit ditolak (403)", s == 403, s)
        s, ha = req("POST", "/ops/audit/jalankan?kirim=false", t_owner)
        baru = {(t["kode"], t.get("ref_id")): t for t in ha.get("baru", [])} if s == 200 else {}
        check("G8 owner jalankan audit: A1 lot rendemen 1.0, A3 usulan 3 sak, A5 kas tanpa nota, A9 SJ lama",
              s == 200 and ("A1", lot_id) in baru and baru.get(("A3", op_sak), {}).get("usulan_potongan_sak") == 3
              and ("A5", kas_tanpa_nota) in baru and ("A9", sj_lama) in baru and ha.get("telegram_terkirim") is None,
              (s, sorted(baru.keys())))
        s, tb = req("GET", "/ops/audit?status=terbuka", t_kepala)
        teks = json.dumps(tb) if s == 200 else ""
        check("G9 kepala baca temuan terbuka (200), tanpa kolom terlarang (P7), laporan berjudul Audit Pabrik",
              s == 200 and len(tb) >= 4 and not any(k in teks for k in KOLOM_TERLARANG) and ha.get("laporan", "").startswith("🏭 Audit Pabrik"), (s, len(tb)))
        id_a1 = baru[("A1", lot_id)]["id"]
        id_a3 = baru[("A3", op_sak)]["id"]
        id_a5 = baru[("A5", kas_tanpa_nota)]["id"]
        s, b = req("POST", f"/ops/audit/{id_a1}/penjelasan", t_kepala, {"penjelasan": "UJI sabut basah, jemur terganggu hujan"})
        s2, _ = req("POST", f"/ops/audit/{id_a1}/tutup", t_kepala, {"catatan": "UJI"})
        s3, b3 = req("POST", f"/ops/audit/{id_a1}/tutup", t_owner, {"catatan": "UJI diterima"})
        s4, _ = req("POST", f"/ops/audit/{id_a1}/tutup", t_owner, {"catatan": "UJI lagi"})
        check("G10 kepala tulis penjelasan A1 (200); kepala tutup 403; owner tutup 200; tutup kedua 409",
              s == 200 and b.get("penjelasan", "").startswith("UJI") and s2 == 403 and s3 == 200 and b3.get("status") == "ditutup" and s4 == 409, (s, s2, s3, s4))
        s, b = req("POST", f"/ops/audit/{id_a3}/terima-potongan", t_owner, {})
        cur.execute("SELECT bulan, sebab, sak, ref_id FROM ops_potongan WHERE id=%s", (b.get("potongan_id") or 0,))
        pot = cur.fetchone()
        s2, _ = req("POST", f"/ops/opname/{op_sak}/batal", t_owner, {"alasan": "UJI"})
        check("G11 owner terima usulan A3 -> potongan opname_sak 3 sak bulan opname merujuk opname; opname tak bisa dibatalkan setelah jadi potongan (409)",
              s == 201 and pot == (tgl_opname[:7], "opname_sak", 3, op_sak) and s2 == 409, (s, b, pot, s2))
        s, _ = req("POST", f"/ops/kas/{kas_tanpa_nota}/batal", t_admin, {"alasan": "UJI salah"})
        s2, ha2 = req("POST", "/ops/audit/jalankan?kirim=false", t_owner)
        sel = {x["id"] for x in ha2.get("selesai_otomatis", [])} if s2 == 200 else set()
        cur.execute("SELECT status FROM ops_audit_temuan WHERE id=%s", (id_a5,))
        st5 = cur.fetchone()[0]
        n_baru_ulang = [t for t in ha2.get("baru", []) if t["kode"] in ("A1", "A3", "A5", "A9") and t.get("ref_id") in (lot_id, op_sak, kas_tanpa_nota, sj_lama)]
        check("G12 audit ulang idempoten: A5 selesai_otomatis setelah kas dibatalkan, temuan lama tidak digandakan",
              s == 200 and s2 == 200 and id_a5 in sel and st5 == "selesai_otomatis" and not n_baru_ulang, (s, s2, sel, st5, [(t["kode"], t.get("ref_id")) for t in n_baru_ulang]))
        s, b = req("GET", "/ops/hpp", t_owner)
        check("G13 HPP punya kolom biaya_tanpa_nota (A5)", s == 200 and isinstance(b, list) and (not b or "biaya_tanpa_nota" in b[0]), (s, b[:1] if isinstance(b, list) else b))
        s, b = req("POST", f"/ops/tutup-hari/{th_id}/batal", t_kepala, {"alasan": "UJI"})
        s2, rg = req("GET", "/ops/tutup-hari/ringkasan", t_admin)
        check("G14 batal tutup hari (P1 tandai) -> ringkasan sudah_ditutup false", s == 200 and b.get("dibatalkan") is True and rg.get("sudah_ditutup") is False, (s, rg))

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

        # PABRIK_B7_9SEP2026: bersihkan opname / tutup hari / temuan audit uji
        cur.execute("DELETE FROM ops_potongan WHERE ref_tabel='ops_stock_opname' AND ref_id IN (SELECT id FROM ops_stock_opname WHERE catatan LIKE 'UJI%%')")
        if g_mulai:
            cur.execute("DELETE FROM ops_audit_temuan WHERE created_at >= %s", (g_mulai,))
        cur.execute("DELETE FROM ops_stock_opname WHERE catatan LIKE 'UJI%%'")
        cur.execute("DELETE FROM ops_sak_kosong_mutasi WHERE jenis='opname' AND keterangan LIKE '%%UJI opname%%'")
        cur.execute("DELETE FROM ops_stok_jadi_mutasi WHERE jenis='opname' AND keterangan LIKE '%%UJI opname%%'")
        cur.execute("DELETE FROM ops_tutup_hari WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM app_audit_log WHERE entity IN ('ops_stock_opname','ops_tutup_hari','ops_audit_temuan') AND created_at > now() - interval '15 minutes'")
        # PABRIK_B2_9SEP2026: bersihkan data operasional uji (urut FK)
        uid_all = list(ids.values()) + [owner_id]
        cur.execute("DELETE FROM ops_upah_harian WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_stok_jadi_mutasi WHERE created_by = ANY(%s)", (list(ids.values()),))

        # PABRIK_B5_9SEP2026: bersihkan pengiriman/klaim/potongan/rekap uji
        cur.execute("DELETE FROM ops_pembayaran_bonus_triwulan WHERE karyawan_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')")
        cur.execute("DELETE FROM ops_rekap_bonus_bulanan WHERE karyawan_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')")
        cur.execute("DELETE FROM ops_potongan WHERE keterangan LIKE '%%UJI%%' OR (sebab='carry_over' AND ref_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')) OR ref_id IN (SELECT id FROM ops_klaim WHERE keterangan LIKE 'UJI%%') AND ref_tabel='ops_klaim'")
        cur.execute("DELETE FROM ops_klaim WHERE keterangan LIKE 'UJI%%' OR pengiriman_id IN (SELECT id FROM ops_pengiriman WHERE created_by = ANY(%s))", (list(ids.values()),))
        cur.execute("DELETE FROM ops_pengiriman WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity IN ('ops_klaim','ops_potongan','ops_pengiriman','ops_rekap_bonus_bulanan','ops_pembayaran_bonus_triwulan') AND created_at > now() - interval '10 minutes'", (owner_id,))
        cur.execute("DELETE FROM ops_stok_jadi_mutasi WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("UPDATE ops_kas_kecil SET ref_sak_mutasi_id=NULL WHERE created_by = ANY(%s) OR keterangan LIKE 'UJI%%'", (list(ids.values()),))
        cur.execute("DELETE FROM ops_sak_kosong_mutasi WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_kas_kecil WHERE created_by = ANY(%s) OR (created_by=%s AND keterangan LIKE 'UJI%%')", (list(ids.values()), owner_id))
        cur.execute("DELETE FROM ops_produksi_sak WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_penerimaan WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_lot_tahap WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_lot WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM ops_cuaca WHERE catatan = 'UJI'")
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity='ops_kas_kecil' AND created_at > now() - interval '10 minutes'", (owner_id,))
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity='ops_petak' AND created_at > now() - interval '10 minutes' AND detail::text LIKE '%%uji-2%%'", (owner_id,))
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
