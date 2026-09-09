"""patch_b2.py -- anchor-assert: daftarkan router ops_operasional di main.py, tambah uji E (B2-B4)
+ pembersihan ke test_pabrik.py. Idempoten."""
ROOT = "/home/izawa/invoice-system/"
TANDA = "PABRIK_B2_9SEP2026"

UJI_E = '''
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
'''

BERSIH_E = '''
        # PABRIK_B2_9SEP2026: bersihkan data operasional uji (urut FK)
        uid_all = list(ids.values()) + [owner_id]
        cur.execute("DELETE FROM ops_upah_harian WHERE created_by = ANY(%s)", (list(ids.values()),))
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
'''


def patch(path, edits):
    p = ROOT + path
    s = open(p, encoding="utf-8").read()
    if TANDA in s:
        print(f"skip {path}")
        return
    for a, n, c in edits:
        assert s.count(a) == c, f"{path}: anchor {s.count(a)}x -> {a[:60]!r}"
        s = s.replace(a, n)
    open(p, "w", encoding="utf-8").write(s)
    print(f"ok   {path}")


patch("webapp/main.py", [
    ("from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, ops, paperless, pembayaran, po, resi, users\n",
     "from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, ops, ops_operasional, paperless, pembayaran, po, resi, users\n", 1),
    ("app.include_router(ops.router)  # workspace Pabrik\n",
     "app.include_router(ops.router)  # workspace Pabrik\napp.include_router(ops_operasional.router)  # PABRIK_B2_9SEP2026\n", 1),
])
patch("test_pabrik.py", [
    ('        print("== D. Invoice tidak tersentuh (K1)")\n', UJI_E + '\n        print("== D. Invoice tidak tersentuh (K1)")\n', 1),
    ("        # bersihkan: parameter uji owner (baris 35) + buka kembali baris 34, lalu jejak akun uji\n",
     BERSIH_E + "        # bersihkan: parameter uji owner (baris 35) + buka kembali baris 34, lalu jejak akun uji\n", 1),
    ("B1: peran admin/kepala, penjaga global (403 ke semua endpoint invoice), parameter\neffective-dated, master pemasok/petak/karyawan.\n",
     "B1: peran admin/kepala, penjaga global (403 ke semua endpoint invoice), parameter\neffective-dated, master pemasok/petak/karyawan.\nB2-B4 (uji E): lot/tahap, terima truk, produksi atomik, sak kosong, kas kecil, upah, cuaca.\n", 1),
])
print("PATCH_B2_OK")
