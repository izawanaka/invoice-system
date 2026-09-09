"""patch_b5.py -- anchor-assert: router ops_bonus + uji F (B5-B6) + pembersihan. Idempoten."""
ROOT = "/home/izawa/invoice-system/"
TANDA = "PABRIK_B5_9SEP2026"

UJI_F = '''
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
'''

BERSIH_F = '''
        # PABRIK_B5_9SEP2026: bersihkan pengiriman/klaim/potongan/rekap uji
        cur.execute("DELETE FROM ops_pembayaran_bonus_triwulan WHERE karyawan_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')")
        cur.execute("DELETE FROM ops_rekap_bonus_bulanan WHERE karyawan_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')")
        cur.execute("DELETE FROM ops_potongan WHERE keterangan LIKE '%%UJI%%' OR (sebab='carry_over' AND ref_id IN (SELECT id FROM ops_karyawan WHERE lower(nama) LIKE 'uji %%')) OR ref_id IN (SELECT id FROM ops_klaim WHERE keterangan LIKE 'UJI%%') AND ref_tabel='ops_klaim'")
        cur.execute("DELETE FROM ops_klaim WHERE keterangan LIKE 'UJI%%' OR pengiriman_id IN (SELECT id FROM ops_pengiriman WHERE created_by = ANY(%s))", (list(ids.values()),))
        cur.execute("DELETE FROM ops_pengiriman WHERE created_by = ANY(%s)", (list(ids.values()),))
        cur.execute("DELETE FROM app_audit_log WHERE user_id=%s AND entity IN ('ops_klaim','ops_potongan','ops_pengiriman','ops_rekap_bonus_bulanan','ops_pembayaran_bonus_triwulan') AND created_at > now() - interval '10 minutes'", (owner_id,))
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
    ("mitra, ops, ops_operasional, paperless", "mitra, ops, ops_bonus, ops_operasional, paperless", 1),
    ("app.include_router(ops_operasional.router)  # PABRIK_B2_9SEP2026\n",
     "app.include_router(ops_operasional.router)  # PABRIK_B2_9SEP2026\napp.include_router(ops_bonus.router)  # PABRIK_B5_9SEP2026\n", 1),
])
patch("test_pabrik.py", [
    ('        print("== D. Invoice tidak tersentuh (K1)")\n', UJI_F + '\n        print("== D. Invoice tidak tersentuh (K1)")\n', 1),
    ('        cur.execute("DELETE FROM ops_upah_harian WHERE created_by = ANY(%s)", (list(ids.values()),))\n',
     '        cur.execute("DELETE FROM ops_upah_harian WHERE created_by = ANY(%s)", (list(ids.values()),))\n'
     '        cur.execute("DELETE FROM ops_stok_jadi_mutasi WHERE created_by = ANY(%s)", (list(ids.values()),))\n' + BERSIH_F, 1),
])
print("PATCH_B5_OK")
