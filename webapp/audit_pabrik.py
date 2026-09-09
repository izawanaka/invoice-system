"""
audit_pabrik.py -- PABRIK B7 (9 Sep 2026): audit otomatis A1-A10 (DESIGN-PABRIK.md §6),
simpan temuan ke ops_audit_temuan (idempoten lewat 'sidik'), laporan Telegram ke owner.

Dijalankan cron harian di host VM102:
    docker exec invoice-api-prod python /app/webapp/audit_pabrik.py --kirim
Dipanggil juga oleh endpoint POST /ops/audit/jalankan (owner) lewat jalankan(conn, ...).

Prinsip:
  - Satu kondisi = satu temuan terbuka (sidik unik). Run berikutnya yang masih menemukan
    kondisi itu hanya memperbarui terakhir_dilihat/pesan; kondisi yang hilang -> selesai_otomatis.
  - K2: tidak ada cek yang membedakan siapa pengetik.
  - P7: pesan/detail tidak pernah memuat nama PT, PO, badan usaha, harga, invoice.
  - Audit hanya MENGUSULKAN potongan (A3/A4); yang memasukkan potongan tetap owner.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

sys.path[:0] = ["/app/webapp", "/app"]
import settings  # noqa: E402,F401

TG_CHAT_OWNER = "1251069696"   # sama dengan invoice_dkp.py / invoice_kks.py (chat owner)
TELEGRAM_MAKS = 3900           # batas pesan Telegram 4096 karakter
LOOKBACK_OPNAME_HARI = 180
UMUR_LOT_A2 = 14
BATAS_HARI_SJ_A9 = 30
TGL_BATAS_A10 = 5
TOLERANSI_SUSUT_DEFAULT = 2.0  # % -- dipakai bila parameter toleransi_susut_pct belum diisi owner

NAMA_CEK = {
    "A1": "Rendemen lot habis di luar kisaran",
    "A2": "Rendemen berjalan lot aktif > 14 hari di luar kisaran",
    "A3": "Selisih opname sak kosong (usulan potongan)",
    "A4": "Selisih opname stok jadi (usulan potongan)",
    "A5": "Kas keluar tanpa foto nota (dikecualikan dari HPP)",
    "A6": "Lot melewati batas hari karung (susut tidak diakui)",
    "A7": "Hari kerja tanpa input pabrik",
    "A8": "Sak dikirim vs sak dari BAP melebihi toleransi",
    "A9": "Surat jalan > 30 hari belum tertaut BAP",
    "A10": "Rekap bonus bulan lalu belum dibekukan",
}


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


def _param(cur, kode, tgl=None):
    cur.execute("SELECT ops_param(%s, %s)", (kode, tgl or date.today()))
    r = cur.fetchone()
    return _num(r[0]) if r and r[0] is not None else None


def _bulan_lalu(hari: date) -> str:
    awal = hari.replace(day=1) - timedelta(days=1)
    return awal.strftime("%Y-%m")


def _temuan(sidik, kode, tingkat, pesan, ref_tabel=None, ref_id=None, detail=None, usulan=None):
    return {"sidik": sidik, "kode": kode, "tingkat": tingkat, "pesan": pesan, "ref_tabel": ref_tabel,
            "ref_id": ref_id, "detail": detail or {}, "usulan_potongan_sak": usulan}


# ============================================================ cek A1-A10
def cek_a1(cur, hari):
    """Lot habis: rendemen final (sak jadi / kubik) di luar rendemen_min..rendemen_max."""
    out = []
    cur.execute("SELECT lot_id, nomor_lot, kubik_masuk, sak_jadi, tanggal_tutup FROM v_ops_lot_ringkas "
                "WHERE status='habis' AND kubik_masuk > 0 AND tanggal_tutup >= %s", (hari - timedelta(days=365),))
    for lot_id, nomor, kubik, sak, tutup in cur.fetchall():
        rmin, rmax = _param(cur, "rendemen_min", tutup), _param(cur, "rendemen_max", tutup)
        if rmin is None or rmax is None:
            continue
        rend = round(sak / _num(kubik), 2)
        if not (rmin <= rend <= rmax):
            out.append(_temuan(f"A1:lot:{lot_id}", "A1", "flag",
                               f"Lot {nomor} habis dengan rendemen {rend} sak/kubik (kisaran {rmin}-{rmax}). "
                               f"Minta penjelasan tertulis.", "ops_lot", lot_id,
                               {"nomor_lot": nomor, "kubik": _num(kubik), "sak_jadi": sak, "rendemen": rend,
                                "rendemen_min": rmin, "rendemen_max": rmax}))
    return out


def cek_a2(cur, hari):
    """Lot aktif > 14 hari yang sudah menghasilkan sak: rendemen berjalan di luar kisaran."""
    out = []
    rmin, rmax = _param(cur, "rendemen_min", hari), _param(cur, "rendemen_max", hari)
    if rmin is None or rmax is None:
        return out
    cur.execute("SELECT lot_id, nomor_lot, kubik_masuk, sak_jadi, umur_hari, status FROM v_ops_lot_ringkas "
                "WHERE status <> 'habis' AND kubik_masuk > 0 AND sak_jadi > 0 AND umur_hari > %s", (UMUR_LOT_A2,))
    for lot_id, nomor, kubik, sak, umur, st in cur.fetchall():
        rend = round(sak / _num(kubik), 2)
        if not (rmin <= rend <= rmax):
            out.append(_temuan(f"A2:lot:{lot_id}", "A2", "peringatan",
                               f"Lot {nomor} ({st}, umur {umur} hari) rendemen berjalan {rend} sak/kubik, "
                               f"di luar {rmin}-{rmax}. Peringatan dini.", "ops_lot", lot_id,
                               {"nomor_lot": nomor, "kubik": _num(kubik), "sak_jadi": sak, "rendemen": rend, "umur_hari": umur}))
    return out


def _cek_opname(cur, hari, jenis, kode, label):
    """A3/A4: opname dengan selisih negatif yang belum ada potongannya -> usulan potongan."""
    out = []
    cur.execute("SELECT o.id, o.tanggal, o.nilai_terukur, o.nilai_sistem, o.selisih FROM ops_stock_opname o "
                "WHERE o.jenis=%s AND o.dibatalkan_pada IS NULL AND o.selisih < 0 AND o.tanggal >= %s "
                "AND NOT EXISTS (SELECT 1 FROM ops_potongan p WHERE p.ref_tabel='ops_stock_opname' AND p.ref_id=o.id "
                "AND p.dibatalkan_pada IS NULL) ORDER BY o.id", (jenis, hari - timedelta(days=LOOKBACK_OPNAME_HARI)))
    for oid, tgl, terukur, sistem, selisih in cur.fetchall():
        kurang = int(round(-_num(selisih)))
        if kurang <= 0:
            continue
        out.append(_temuan(f"{kode}:opname:{oid}", kode, "peringatan",
                           f"Opname {label} {tgl}: fisik {int(_num(terukur))} vs sistem {int(_num(sistem))} "
                           f"(kurang {kurang} sak). Usulan potongan {kurang} sak.", "ops_stock_opname", oid,
                           {"tanggal": tgl.isoformat(), "fisik": _num(terukur), "sistem": _num(sistem), "selisih": _num(selisih),
                            "bulan_potongan": tgl.strftime("%Y-%m")}, usulan=kurang))
    return out


def cek_a3(cur, hari):
    return _cek_opname(cur, hari, "sak_kosong", "A3", "sak kosong")


def cek_a4(cur, hari):
    return _cek_opname(cur, hari, "stok_jadi", "A4", "stok jadi")


def cek_a5(cur, hari):
    """Kas keluar manual tanpa foto nota (baris otomatis upah/sak dikecualikan)."""
    out = []
    cur.execute("SELECT id, tanggal, kategori, nominal, keterangan FROM ops_kas_kecil WHERE jenis='keluar' "
                "AND dibatalkan_pada IS NULL AND foto_nota IS NULL AND kategori NOT IN ('upah','sak') "
                "AND tanggal >= %s ORDER BY id", (hari - timedelta(days=90),))
    for kid, tgl, kat, nominal, ket in cur.fetchall():
        out.append(_temuan(f"A5:kas:{kid}", "A5", "info",
                           f"Kas keluar {tgl} {kat} Rp{_num(nominal):,.0f} tanpa foto nota -- dikecualikan dari HPP.",
                           "ops_kas_kecil", kid, {"tanggal": tgl.isoformat(), "kategori": kat, "nominal": _num(nominal),
                                                  "keterangan": (ket or "")[:120]}))
    return out


def cek_a6(cur, hari):
    out = []
    cur.execute("SELECT lot_id, nomor_lot, umur_hari, status FROM v_ops_lot_ringkas WHERE lewat_batas_karung")
    batas = _param(cur, "batas_hari_karung", hari)
    for lot_id, nomor, umur, st in cur.fetchall():
        out.append(_temuan(f"A6:lot:{lot_id}", "A6", "flag",
                           f"Lot {nomor} ({st}) sudah {umur} hari, melewati batas {batas:g} hari karung. "
                           f"Susut lot ini tidak diakui.", "ops_lot", lot_id,
                           {"nomor_lot": nomor, "umur_hari": umur, "batas_hari_karung": batas}))
    return out


# (tabel, kolom tanggal, syarat aktif) -- ops_lot_tahap tidak punya kolom batal: ikut lot induknya
AKTIF = "dibatalkan_pada IS NULL"
TABEL_INPUT = (("ops_penerimaan", "tanggal", AKTIF), ("ops_produksi_sak", "tanggal", AKTIF),
               ("ops_sak_kosong_mutasi", "tanggal", AKTIF), ("ops_kas_kecil", "tanggal", AKTIF),
               ("ops_upah_harian", "tanggal", AKTIF), ("ops_pengiriman", "tanggal", AKTIF),
               ("ops_lot_tahap", "tanggal_mulai", "EXISTS (SELECT 1 FROM ops_lot l WHERE l.id=ops_lot_tahap.lot_id AND l.dibatalkan_pada IS NULL)"),
               ("ops_lot", "tanggal_buka", AKTIF))


def _ada_input(cur, tgl):
    for tabel, kolom, aktif in TABEL_INPUT:
        cur.execute(f"SELECT 1 FROM {tabel} WHERE {kolom}=%s AND {aktif} LIMIT 1", (tgl,))
        if cur.fetchone():
            return True
    cur.execute("SELECT 1 FROM ops_tutup_hari WHERE tanggal=%s AND dibatalkan_pada IS NULL", (tgl,))
    return bool(cur.fetchone())


def _tanggal_input_pertama(cur):
    paling_awal = None
    for tabel, kolom, aktif in TABEL_INPUT:
        cur.execute(f"SELECT min({kolom}) FROM {tabel} WHERE {aktif}")
        r = cur.fetchone()[0]
        if r and (paling_awal is None or r < paling_awal):
            paling_awal = r
    return paling_awal


def cek_a7(cur, hari):
    """Hari kerja (Senin-Sabtu) kemarin tanpa satu pun input pabrik & tanpa tutup hari.
    Dilewati bila pabrik belum pernah punya data (belum beroperasi)."""
    kemarin = hari - timedelta(days=1)
    if kemarin.weekday() == 6:  # Minggu
        return []
    awal = _tanggal_input_pertama(cur)
    if awal is None or kemarin <= awal:
        return []
    if _ada_input(cur, kemarin):
        return []
    return [_temuan(f"A7:hari:{kemarin.isoformat()}", "A7", "peringatan",
                    f"{kemarin.strftime('%A %d-%m-%Y')}: tidak ada input pabrik sama sekali dan hari tidak ditutup. Tanya lapangan.",
                    "ops_tutup_hari", None, {"tanggal": kemarin.isoformat()})]


def cek_a8(cur, hari):
    """Per BAP tertaut (bulan ini & bulan lalu): sak surat jalan vs sak hasil konversi BAP."""
    out = []
    bulan = [hari.strftime("%Y-%m"), _bulan_lalu(hari)]
    cur.execute("SELECT b.id, b.no_bap, b.tgl_bap, b.total_qty, lower(b.satuan), sum(p.jumlah_sak), count(*) "
                "FROM ops_pengiriman p JOIN bap b ON b.id=p.bap_id WHERE p.dibatalkan_pada IS NULL "
                "AND to_char(b.tgl_bap,'YYYY-MM') = ANY(%s) GROUP BY b.id, b.no_bap, b.tgl_bap, b.total_qty, b.satuan", (bulan,))
    for bid, no_bap, tgl, qty, satuan, sak_sj, n_sj in cur.fetchall():
        qty = _num(qty)
        if satuan == "kg":
            k = _param(cur, "kg_per_sak", tgl)
            sak_bap = qty / k if k else None
        elif satuan in ("m3", "m³"):
            k = _param(cur, "sak_per_m3_kks", tgl)
            sak_bap = qty * k if k else None
        else:
            sak_bap = None
        if not sak_bap:
            continue
        tol = _param(cur, "toleransi_susut_pct", tgl)
        tol_default = tol is None
        tol = TOLERANSI_SUSUT_DEFAULT if tol_default else tol
        selisih_pct = round((sak_sj - sak_bap) / sak_bap * 100, 2)
        if abs(selisih_pct) > tol:
            out.append(_temuan(f"A8:bap:{bid}", "A8", "peringatan",
                               f"BAP {no_bap} ({tgl}): dikirim {int(sak_sj)} sak ({n_sj} SJ) vs BAP setara {sak_bap:.1f} sak "
                               f"= selisih {selisih_pct:+.2f}% (toleransi {tol:g}%{', default' if tol_default else ''}). "
                               f"Tampil di rekap bonus.", "bap", bid,
                               {"no_bap": no_bap, "tgl_bap": tgl.isoformat(), "qty": qty, "satuan": satuan,
                                "sak_bap": round(sak_bap, 1), "sak_dikirim": int(sak_sj), "selisih_pct": selisih_pct,
                                "toleransi_pct": tol, "toleransi_default": tol_default}))
    return out


def cek_a9(cur, hari):
    out = []
    cur.execute("SELECT id, tanggal, no_surat_jalan, jumlah_sak, tujuan_kode FROM ops_pengiriman WHERE bap_id IS NULL "
                "AND dibatalkan_pada IS NULL AND tanggal < %s ORDER BY tanggal", (hari - timedelta(days=BATAS_HARI_SJ_A9),))
    for pid, tgl, sj, sak, tujuan in cur.fetchall():
        umur = (hari - tgl).days
        out.append(_temuan(f"A9:sj:{pid}", "A9", "peringatan",
                           f"Surat jalan {sj} ({tgl}, {sak} sak, tujuan {tujuan}) sudah {umur} hari belum ditautkan ke BAP.",
                           "ops_pengiriman", pid, {"no_surat_jalan": sj, "tanggal": tgl.isoformat(), "jumlah_sak": sak,
                                                   "tujuan_kode": tujuan, "umur_hari": umur}))
    return out


def cek_a10(cur, hari):
    """Setelah tgl 5: rekap bulan lalu tiap kepala aktif belum dibekukan. Hanya bila bulan lalu
    memang ada aktivitas (pengiriman atau BAP tertaut), supaya tidak berisik sebelum pabrik jalan."""
    if hari.day <= TGL_BATAS_A10:
        return []
    bln = _bulan_lalu(hari)
    cur.execute("SELECT 1 FROM ops_pengiriman WHERE dibatalkan_pada IS NULL AND to_char(tanggal,'YYYY-MM')=%s LIMIT 1", (bln,))
    if not cur.fetchone():
        return []
    akhir = date(int(bln[:4]), int(bln[5:]), 1)
    cur.execute("SELECT id, nama FROM ops_karyawan WHERE peran='kepala' AND dibatalkan_pada IS NULL AND berlaku_mulai <= %s "
                "AND (berlaku_sampai IS NULL OR berlaku_sampai >= %s) AND NOT EXISTS (SELECT 1 FROM ops_rekap_bonus_bulanan r "
                "WHERE r.karyawan_id=ops_karyawan.id AND r.bulan=%s AND r.status='dibekukan')", (akhir, akhir, bln))
    out = []
    for kid, nama in cur.fetchall():
        out.append(_temuan(f"A10:rekap:{bln}:{kid}", "A10", "peringatan",
                           f"Rekap bonus {bln} untuk {nama} belum dibekukan (sudah lewat tanggal {TGL_BATAS_A10}).",
                           "ops_rekap_bonus_bulanan", kid, {"bulan": bln, "karyawan_id": kid, "nama": nama}))
    return out


SEMUA_CEK = [cek_a1, cek_a2, cek_a3, cek_a4, cek_a5, cek_a6, cek_a7, cek_a8, cek_a9, cek_a10]


# ============================================================ simpan & laporan
def simpan_temuan(cur, temuan, hari):
    """Idempoten: sidik terbuka yang masih ditemukan -> diperbarui; baru -> disisipkan;
    terbuka tapi tidak ditemukan lagi -> selesai_otomatis. Mengembalikan (baru, selesai)."""
    cur.execute("SELECT id, sidik FROM ops_audit_temuan WHERE status='terbuka'")
    terbuka = {sidik: tid for tid, sidik in cur.fetchall()}
    # Temuan yang sudah DITUTUP owner tidak dibangkitkan lagi walau kondisinya masih ada
    # (keputusan owner final). 'selesai_otomatis' boleh muncul lagi bila kondisinya kembali.
    cur.execute("SELECT DISTINCT sidik FROM ops_audit_temuan WHERE status='ditutup'")
    ditutup = {r[0] for r in cur.fetchall()}
    ditemukan = set()
    baru = []
    for t in temuan:
        ditemukan.add(t["sidik"])
        if t["sidik"] in ditutup and t["sidik"] not in terbuka:
            continue
        if t["sidik"] in terbuka:
            cur.execute("UPDATE ops_audit_temuan SET terakhir_dilihat=%s, pesan=%s, detail=%s, usulan_potongan_sak=%s WHERE id=%s",
                        (hari, t["pesan"], json.dumps(t["detail"]), t["usulan_potongan_sak"], terbuka[t["sidik"]]))
        else:
            cur.execute("INSERT INTO ops_audit_temuan (sidik, kode, tingkat, ref_tabel, ref_id, pesan, detail, usulan_potongan_sak, "
                        "tanggal_audit, terakhir_dilihat) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (t["sidik"], t["kode"], t["tingkat"], t["ref_tabel"], t["ref_id"], t["pesan"], json.dumps(t["detail"]),
                         t["usulan_potongan_sak"], hari, hari))
            t["id"] = cur.fetchone()[0]
            baru.append(t)
    hilang = [tid for sidik, tid in terbuka.items() if sidik not in ditemukan]
    selesai = []
    if hilang:
        # A10 hanya dievaluasi setelah tgl 5 -- jangan tutup otomatis saat tidak dievaluasi
        cur.execute("SELECT id, kode, pesan FROM ops_audit_temuan WHERE id = ANY(%s)", (hilang,))
        for tid, kode, pesan in cur.fetchall():
            if kode == "A10" and hari.day <= TGL_BATAS_A10:
                continue
            cur.execute("UPDATE ops_audit_temuan SET status='selesai_otomatis', ditutup_pada=now(), catatan_tutup='Kondisi tidak ditemukan lagi oleh audit' WHERE id=%s", (tid,))
            selesai.append({"id": tid, "kode": kode, "pesan": pesan})
    return baru, selesai


def ringkasan(cur, hari):
    cur.execute("SELECT saldo, rusak_belum_retur FROM v_ops_saldo_sak_kosong")
    sk, rusak = cur.fetchone()
    cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
    sj = cur.fetchone()[0]
    cur.execute("SELECT saldo FROM v_ops_saldo_kas")
    kas = _num(cur.fetchone()[0])
    kemarin = hari - timedelta(days=1)
    cur.execute("SELECT u.username, t.created_at FROM ops_tutup_hari t JOIN app_users u ON u.id=t.created_by "
                "WHERE t.tanggal=%s AND t.dibatalkan_pada IS NULL", (kemarin,))
    r = cur.fetchone()
    cur.execute("SELECT cuaca_teks, hujan_mm FROM ops_cuaca WHERE tanggal=%s ORDER BY sumber='manual' DESC LIMIT 1", (hari,))
    c = cur.fetchone()
    cur.execute("SELECT count(*) FROM v_ops_lot_ringkas WHERE status <> 'habis'")
    lot_aktif = cur.fetchone()[0]
    return {"sak_kosong": sk, "sak_rusak_belum_retur": rusak, "stok_jadi": sj, "kas": kas, "lot_aktif": lot_aktif,
            "tutup_hari_kemarin": {"tanggal": kemarin.isoformat(), "ditutup": bool(r), "oleh": r[0] if r else None},
            "cuaca": {"teks": c[0], "hujan_mm": _num(c[1])} if c else None}


def format_laporan(hari, ring, baru, selesai, terbuka):
    hari_id = hari.strftime("%d-%m-%Y")
    b = [f"🏭 Audit Pabrik {hari_id}",
         f"Sak kosong {ring['sak_kosong']} (rusak tunggu retur {ring['sak_rusak_belum_retur']}) · Stok jadi {ring['stok_jadi']} sak · "
         f"Kas kecil Rp{ring['kas']:,.0f} · Lot aktif {ring['lot_aktif']}"]
    th = ring["tutup_hari_kemarin"]
    b.append(f"Tutup hari {th['tanggal']}: {'✅ ' + th['oleh'] if th['ditutup'] else '❌ belum'}")
    if ring["cuaca"]:
        b.append(f"Cuaca hari ini: {ring['cuaca']['teks']} ({ring['cuaca']['hujan_mm']:g} mm)")
    if baru:
        b.append(f"\n🔔 Temuan baru ({len(baru)}):")
        for t in baru:
            b.append(f"• [{t['kode']}] {t['pesan']}")
    else:
        b.append("\n✅ Tidak ada temuan baru.")
    if selesai:
        b.append(f"\n☑️ Selesai otomatis ({len(selesai)}): " + ", ".join(f"{s['kode']}#{s['id']}" for s in selesai))
    if terbuka:
        per_kode = {}
        for t in terbuka:
            per_kode[t["kode"]] = per_kode.get(t["kode"], 0) + 1
        b.append(f"\n📌 Masih terbuka {len(terbuka)}: " + ", ".join(f"{k} ×{v}" for k, v in sorted(per_kode.items(), key=lambda x: int(x[0][1:]))))
    teks = "\n".join(b)
    if len(teks) > TELEGRAM_MAKS:
        teks = teks[:TELEGRAM_MAKS - 20] + "\n… (dipotong)"
    return teks


def kirim_telegram(teks: str) -> bool:
    """Kirim ke chat owner. Gagal kirim TIDAK boleh menggagalkan audit -- dicatat, dikembalikan False."""
    try:
        import config  # token dari file, bukan kode (I6)
        url = "https://api.telegram.org/bot" + config.tg_token() + "/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TG_CHAT_OWNER, "text": teks}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print("audit_pabrik: gagal kirim Telegram:", e, file=sys.stderr)
        return False


def jalankan(conn, hari=None, kirim=False, dipicu_oleh=None):
    hari = hari or date.today()
    cur = conn.cursor()
    temuan = []
    for f in SEMUA_CEK:
        temuan.extend(f(cur, hari))
    baru, selesai = simpan_temuan(cur, temuan, hari)
    cur.execute("SELECT id, kode, tingkat, pesan, tanggal_audit FROM ops_audit_temuan WHERE status='terbuka' ORDER BY id")
    terbuka = [{"id": r[0], "kode": r[1], "tingkat": r[2], "pesan": r[3], "tanggal_audit": r[4].isoformat()} for r in cur.fetchall()]
    ring = ringkasan(cur, hari)
    laporan = format_laporan(hari, ring, baru, selesai, terbuka)
    terkirim = kirim_telegram(laporan) if kirim else None
    cur.execute("INSERT INTO app_audit_log (user_id, aksi, entity, entity_id, detail) VALUES (%s,'ops_audit_jalankan','ops_audit_temuan',%s,%s)",
                (dipicu_oleh, hari.isoformat(), json.dumps({"baru": len(baru), "selesai_otomatis": len(selesai), "terbuka": len(terbuka),
                                                            "telegram": terkirim})))
    conn.commit()
    return {"tanggal": hari.isoformat(), "baru": baru, "selesai_otomatis": selesai, "terbuka": terbuka, "ringkasan": ring,
            "laporan": laporan, "telegram_terkirim": terkirim}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kirim", action="store_true", help="kirim laporan ke Telegram owner")
    ap.add_argument("--tanggal", help="YYYY-MM-DD (default hari ini)")
    a = ap.parse_args()
    import db_helper
    conn = db_helper.get_conn()
    try:
        hasil = jalankan(conn, date.fromisoformat(a.tanggal) if a.tanggal else None, kirim=a.kirim)
    finally:
        conn.close()
    print(hasil["laporan"])
    print(f"\n[audit_pabrik] baru={len(hasil['baru'])} selesai={len(hasil['selesai_otomatis'])} terbuka={len(hasil['terbuka'])} "
          f"telegram={hasil['telegram_terkirim']}")


if __name__ == "__main__":
    main()
