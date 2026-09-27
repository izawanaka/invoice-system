"""
ops_bonus.py -- workspace PABRIK tahap B5-B6 (9 Sep 2026): pengiriman & tautan BAP (P7),
klaim -> potongan, mesin bonus Konsep B (K5), bekukan rekap (P8), pembayaran triwulan.

Konsep B (K5): sak_bap(M) = Σ konversi volume BAP bertanggal bulan M yang tertaut pengiriman
  DKP kg   -> kg / kg_per_sak (efektif tgl BAP)
  KKS m3   -> m3 * sak_per_m3_kks (efektif tgl BAP); NULL -> rekap 'menunggu_parameter'
potongan(M) = Σ ops_potongan bulan M (klaim mutu 2x, angkut 1x, susut, opname, lot rusak, carry-over)
sak_netto   = max(0, sak_bap - potongan); sisa negatif -> carry_over ke bulan berikutnya SAAT DIBEKUKAN
bonus       = marjinal per jenjang (ops_tarif_bonus) dgn cap, x pengali(pct klaim = sak klaim / sak dikirim)
P7: admin/kepala tidak pernah menerima nama PT, PO, badan usaha, harga, invoice -- view v_ops_bap_pabrik.
P8: rekap 'dibekukan' tidak pernah dihitung ulang.
"""
import calendar
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import settings  # noqa: F401
import security
from audit import log_audit
from deps import get_db
from routers.ops_operasional import _batal, _kunci, _num, _param  # _kunci: F1 (27 Sep 2026)

router = APIRouter(prefix="/ops", tags=["pabrik-bonus"])

KOLOM_TERLARANG = {"nama_pt", "po_no", "badan_usaha", "badan_usaha_id", "harga", "invoice_no", "site", "customer"}


def _bulan_akhir(bulan: str) -> date:
    y, m = int(bulan[:4]), int(bulan[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


def _bulan_berikut(bulan: str) -> str:
    y, m = int(bulan[:4]), int(bulan[5:7])
    return f"{y + (m // 12)}-{(m % 12) + 1:02d}"


def hitung_jenjang(sak_netto: int, tarif_rows, cap: Optional[float]) -> float:
    """Bonus marjinal: tiap jenjang dibayar untuk sak di rentangnya saja (KSP-CP-001).
    tarif_rows: [(sak_dari, sak_sampai|None, tarif_per_sak)]."""
    total = 0.0
    for sak_dari, sak_sampai, tarif in tarif_rows:
        atas = sak_sampai if sak_sampai is not None else 10**9
        n = max(0, min(sak_netto, atas) - sak_dari + 1)
        total += n * float(tarif)
    if cap is not None:
        total = min(total, float(cap))
    return round(total, 2)


def _karyawan_untuk(cur, user) -> Optional[int]:
    """Kepala hanya boleh melihat rekap miliknya (ops_karyawan.user_id = akun)."""
    cur.execute("SELECT id FROM ops_karyawan WHERE user_id=%s AND peran='kepala' AND dibatalkan_pada IS NULL "
                "ORDER BY berlaku_mulai DESC LIMIT 1", (user.id,))
    r = cur.fetchone()
    return r[0] if r else None


# ============================================================ PENGIRIMAN
class PengirimanIn(BaseModel):
    tanggal: date
    no_surat_jalan: str = Field(min_length=2, max_length=40)
    jumlah_sak: int = Field(gt=0, le=20000)
    nopol: Optional[str] = Field(default=None, max_length=20)
    tujuan_kode: str = Field(min_length=1, max_length=10, pattern="^[A-Za-z0-9-]+$")
    catatan: Optional[str] = Field(default=None, max_length=300)


class PengirimanOut(BaseModel):
    id: int
    tanggal: date
    no_surat_jalan: str
    jumlah_sak: int
    nopol: Optional[str]
    tujuan_kode: str
    bap_tertaut: bool
    no_bap: Optional[str]
    catatan: Optional[str]
    dibatalkan: bool


def _pengiriman_rows(cur, where="", params=()):
    cur.execute("SELECT p.id, p.tanggal, p.no_surat_jalan, p.jumlah_sak, p.nopol, p.tujuan_kode, p.bap_id IS NOT NULL, b.no_bap, "
                "p.catatan, p.dibatalkan_pada IS NOT NULL FROM ops_pengiriman p LEFT JOIN bap b ON b.id=p.bap_id " + where +
                " ORDER BY p.tanggal DESC, p.id DESC", params)
    return [PengirimanOut(id=r[0], tanggal=r[1], no_surat_jalan=r[2], jumlah_sak=r[3], nopol=r[4], tujuan_kode=r[5],
                          bap_tertaut=r[6], no_bap=r[7], catatan=r[8], dibatalkan=r[9]) for r in cur.fetchall()]


@router.get("/pengiriman", response_model=List[PengirimanOut])
def list_pengiriman(bulan: Optional[str] = None, conn=Depends(get_db),
                    user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    if bulan:
        return _pengiriman_rows(conn.cursor(), "WHERE to_char(p.tanggal,'YYYY-MM')=%s", (bulan,))
    return _pengiriman_rows(conn.cursor())


@router.post("/pengiriman", response_model=PengirimanOut, status_code=status.HTTP_201_CREATED)
def pengiriman_baru(body: PengirimanIn, conn=Depends(get_db),
                    user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "stok")
    cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
    sj = cur.fetchone()[0]
    if sj - body.jumlah_sak < 0:
        raise HTTPException(status_code=409, detail=f"Stok jadi hanya {sj} sak (P5)")
    cur.execute("SELECT 1 FROM ops_pengiriman WHERE lower(no_surat_jalan)=lower(%s) AND dibatalkan_pada IS NULL",
                (body.no_surat_jalan,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Nomor surat jalan sudah ada")
    cur.execute("INSERT INTO ops_pengiriman (tanggal, no_surat_jalan, jumlah_sak, nopol, tujuan_kode, catatan, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal, body.no_surat_jalan.strip(), body.jumlah_sak, body.nopol, body.tujuan_kode.upper(),
                 body.catatan, user.id))
    pid = cur.fetchone()[0]
    cur.execute("INSERT INTO ops_stok_jadi_mutasi (tanggal, jenis, delta, ref_pengiriman_id, keterangan, created_by) "
                "VALUES (%s,'kirim',%s,%s,%s,%s)", (body.tanggal, -body.jumlah_sak, pid, f"SJ {body.no_surat_jalan}", user.id))
    log_audit(conn, user.id, "ops_pengiriman_baru", "ops_pengiriman", pid, {"sak": body.jumlah_sak, "tujuan": body.tujuan_kode})
    conn.commit()
    return _pengiriman_rows(cur, "WHERE p.id=%s", (pid,))[0]


class BatalIn(BaseModel):
    alasan: str = Field(min_length=3, max_length=300)


@router.post("/pengiriman/{row_id}/batal", response_model=PengirimanOut)
def pengiriman_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                     user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "stok")
    cur.execute("SELECT bap_id FROM ops_pengiriman WHERE id=%s", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    if r[0]:
        raise HTTPException(status_code=409, detail="Sudah tertaut BAP -- owner harus melepas tautan dulu")
    _batal(cur, conn, user, "ops_pengiriman", row_id, body.alasan, "ops_pengiriman_batal")
    cur.execute("UPDATE ops_stok_jadi_mutasi SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s "
                "WHERE ref_pengiriman_id=%s AND dibatalkan_pada IS NULL", (user.id, body.alasan, row_id))
    conn.commit()
    return _pengiriman_rows(cur, "WHERE p.id=%s", (row_id,))[0]


# ============================================================ TAUTAN BAP (owner)
class TautIn(BaseModel):
    bap_id: int


@router.get("/bap-pilihan")
def bap_pilihan(bulan: Optional[str] = None, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_owner)):
    """OWNER SAJA: daftar BAP DKP/KKS untuk ditautkan (menampilkan badan usaha)."""
    cur = conn.cursor()
    q = ("SELECT b.id, b.no_bap, b.tgl_bap, b.total_qty, b.satuan, bu.kode, b.site, "
         "(SELECT count(*) FROM ops_pengiriman p WHERE p.bap_id=b.id AND p.dibatalkan_pada IS NULL) "
         "FROM bap b JOIN badan_usaha bu ON bu.id=b.badan_usaha_id ")
    if bulan:
        cur.execute(q + "WHERE to_char(b.tgl_bap,'YYYY-MM')=%s ORDER BY b.tgl_bap DESC, b.id DESC", (bulan,))
    else:
        cur.execute(q + "ORDER BY b.tgl_bap DESC, b.id DESC LIMIT 100")
    return [{"bap_id": r[0], "no_bap": r[1], "tgl_bap": r[2], "qty": _num(r[3]), "satuan": r[4], "badan_usaha": r[5],
             "site": r[6], "n_pengiriman": r[7]} for r in cur.fetchall()]


@router.post("/pengiriman/{row_id}/tautkan-bap", response_model=PengirimanOut)
def tautkan_bap(row_id: int, body: TautIn, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT bap_id, dibatalkan_pada FROM ops_pengiriman WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r or r[1]:
        raise HTTPException(status_code=404, detail="Pengiriman tidak ditemukan / dibatalkan")
    cur.execute("SELECT no_bap, tgl_bap FROM bap WHERE id=%s", (body.bap_id,))
    b = cur.fetchone()
    if not b:
        raise HTTPException(status_code=422, detail="BAP tidak ditemukan")
    bulan = b[1].strftime("%Y-%m")
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (bulan,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Rekap bonus {bulan} sudah dibekukan (P8); BAP bulan itu tidak bisa ditautkan lagi")
    cur.execute("UPDATE ops_pengiriman SET bap_id=%s WHERE id=%s", (body.bap_id, row_id))
    log_audit(conn, user.id, "ops_pengiriman_taut_bap", "ops_pengiriman", row_id, {"bap_id": body.bap_id, "no_bap": b[0], "sebelumnya": r[0]})
    conn.commit()
    return _pengiriman_rows(cur, "WHERE p.id=%s", (row_id,))[0]


@router.post("/pengiriman/{row_id}/lepas-bap", response_model=PengirimanOut)
def lepas_bap(row_id: int, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT p.bap_id, b.tgl_bap FROM ops_pengiriman p LEFT JOIN bap b ON b.id=p.bap_id WHERE p.id=%s FOR UPDATE OF p", (row_id,))
    r = cur.fetchone()
    if not r or not r[0]:
        raise HTTPException(status_code=404, detail="Tidak tertaut BAP")
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (r[1].strftime("%Y-%m"),))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Rekap bulan BAP itu sudah dibekukan (P8)")
    cur.execute("SELECT 1 FROM ops_klaim WHERE pengiriman_id=%s AND dibatalkan_pada IS NULL", (row_id,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Ada klaim aktif pada pengiriman ini")
    cur.execute("UPDATE ops_pengiriman SET bap_id=NULL WHERE id=%s", (row_id,))
    log_audit(conn, user.id, "ops_pengiriman_lepas_bap", "ops_pengiriman", row_id, {"bap_id": r[0]})
    conn.commit()
    return _pengiriman_rows(cur, "WHERE p.id=%s", (row_id,))[0]


@router.get("/bap-pabrik")
def bap_pabrik(bulan: Optional[str] = None, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    """K4/P7: BAP versi pabrik -- hanya kolom aman dari v_ops_bap_pabrik."""
    cur = conn.cursor()
    q = ("SELECT pengiriman_id, no_surat_jalan, tanggal_kirim, jumlah_sak, tujuan_kode, no_bap, tgl_bap, qty_bap, satuan_bap, sak_klaim "
         "FROM v_ops_bap_pabrik ")
    if bulan:
        cur.execute(q + "WHERE to_char(tgl_bap,'YYYY-MM')=%s ORDER BY tgl_bap DESC, pengiriman_id DESC", (bulan,))
    else:
        cur.execute(q + "ORDER BY tanggal_kirim DESC, pengiriman_id DESC LIMIT 200")
    rows = [{"pengiriman_id": r[0], "no_surat_jalan": r[1], "tanggal_kirim": r[2], "jumlah_sak": r[3], "tujuan_kode": r[4],
             "no_bap": r[5], "tgl_bap": r[6], "qty_bap": _num(r[7]), "satuan_bap": r[8], "sak_klaim": r[9]} for r in cur.fetchall()]
    assert not rows or not (set(rows[0].keys()) & KOLOM_TERLARANG)  # penjaga P7 di kode
    return rows


@router.get("/rasio-kks")
def rasio_kks(conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT bap_id, no_bap, tgl_bap, m3_bap, sak_dikirim, sak_per_m3 FROM v_ops_rasio_kks ORDER BY tgl_bap DESC")
    rows = [{"bap_id": r[0], "no_bap": r[1], "tgl_bap": r[2], "m3_bap": _num(r[3]), "sak_dikirim": r[4], "sak_per_m3": _num(r[5])}
            for r in cur.fetchall()]
    rasio = sorted(x["sak_per_m3"] for x in rows if x["sak_per_m3"])
    median = rasio[len(rasio) // 2] if rasio else None
    return {"median_sak_per_m3": median, "parameter_saat_ini": _param(cur, "sak_per_m3_kks"), "data": rows}


# ============================================================ KLAIM & POTONGAN
class KlaimIn(BaseModel):
    tanggal_terima: date
    pengiriman_id: int
    jumlah_sak_diklaim: int = Field(gt=0)
    jenis: str = Field(pattern="^(mutu|angkut)$")
    bukti: Optional[str] = None
    keterangan: Optional[str] = Field(default=None, max_length=300)


@router.get("/klaim")
def list_klaim(bulan: Optional[str] = None, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    q = ("SELECT k.id, k.tanggal_terima, k.pengiriman_id, p.no_surat_jalan, k.jumlah_sak_diklaim, k.jenis, k.potongan_sak, "
         "k.keterangan, k.dibatalkan_pada IS NOT NULL FROM ops_klaim k JOIN ops_pengiriman p ON p.id=k.pengiriman_id ")
    if bulan:
        cur.execute(q + "WHERE to_char(k.tanggal_terima,'YYYY-MM')=%s ORDER BY k.tanggal_terima DESC", (bulan,))
    else:
        cur.execute(q + "ORDER BY k.tanggal_terima DESC LIMIT 200")
    return [{"id": r[0], "tanggal_terima": r[1], "pengiriman_id": r[2], "no_surat_jalan": r[3], "jumlah_sak_diklaim": r[4],
             "jenis": r[5], "potongan_sak": r[6], "keterangan": r[7], "dibatalkan": r[8]} for r in cur.fetchall()]


@router.post("/klaim", status_code=status.HTTP_201_CREATED)
def klaim_baru(body: KlaimIn, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_owner)):
    """Klaim pembeli dicatat OWNER (K3/K4). Otomatis membuat potongan: mutu 2x, angkut 1x (SOP §5)."""
    cur = conn.cursor()
    cur.execute("SELECT jumlah_sak, bap_id FROM ops_pengiriman WHERE id=%s AND dibatalkan_pada IS NULL", (body.pengiriman_id,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=422, detail="Pengiriman tidak ditemukan")
    if body.jumlah_sak_diklaim > p[0]:
        raise HTTPException(status_code=422, detail=f"Klaim {body.jumlah_sak_diklaim} > sak dikirim {p[0]}")
    bulan = body.tanggal_terima.strftime("%Y-%m")
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (bulan,))
    if cur.fetchone():
        # KSP: klaim setelah rekap dibekukan -> potong di bulan berjalan
        bulan = date.today().strftime("%Y-%m")
    faktor = 2 if body.jenis == "mutu" else 1
    pot = body.jumlah_sak_diklaim * faktor
    cur.execute("INSERT INTO ops_klaim (tanggal_terima, pengiriman_id, jumlah_sak_diklaim, jenis, potongan_sak, bukti, keterangan, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal_terima, body.pengiriman_id, body.jumlah_sak_diklaim, body.jenis, pot, body.bukti, body.keterangan, user.id))
    kid = cur.fetchone()[0]
    cur.execute("INSERT INTO ops_potongan (bulan, sebab, sak, ref_tabel, ref_id, keterangan, created_by) VALUES (%s,%s,%s,'ops_klaim',%s,%s,%s) RETURNING id",
                (bulan, "klaim_" + body.jenis, pot, kid, f"Klaim {body.jenis} {body.jumlah_sak_diklaim} sak x{faktor}. {body.keterangan or ''}".strip(), user.id))
    pot_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_klaim_baru", "ops_klaim", kid, {"potongan_id": pot_id, "sak": pot, "bulan": bulan})
    conn.commit()
    return {"id": kid, "potongan_id": pot_id, "potongan_sak": pot, "bulan_potongan": bulan}


@router.post("/klaim/{row_id}/batal")
def klaim_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT bulan, dibatalkan_pada FROM ops_potongan WHERE ref_tabel='ops_klaim' AND ref_id=%s", (row_id,))
    pots = cur.fetchall()
    for bln, dib in pots:
        cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (bln,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Potongan klaim ini sudah masuk rekap {bln} yang dibekukan (P8)")
    _batal(cur, conn, user, "ops_klaim", row_id, body.alasan, "ops_klaim_batal")
    cur.execute("UPDATE ops_potongan SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s WHERE ref_tabel='ops_klaim' AND ref_id=%s AND dibatalkan_pada IS NULL",
                (user.id, body.alasan, row_id))
    conn.commit()
    return {"ok": True}


class PotonganIn(BaseModel):
    bulan: str = Field(pattern="^\\d{4}-\\d{2}$")
    sebab: str = Field(pattern="^(susut|opname_sak|lot_rusak|manual)$")
    sak: int = Field(gt=0)
    keterangan: str = Field(min_length=3, max_length=300)


@router.get("/potongan")
def list_potongan(bulan: Optional[str] = None, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    q = "SELECT id, bulan, sebab, sak, ref_tabel, ref_id, keterangan, dibatalkan_pada IS NOT NULL FROM ops_potongan "
    if bulan:
        cur.execute(q + "WHERE bulan=%s ORDER BY id", (bulan,))
    else:
        cur.execute(q + "ORDER BY bulan DESC, id DESC LIMIT 200")
    return [{"id": r[0], "bulan": r[1], "sebab": r[2], "sak": r[3], "ref_tabel": r[4], "ref_id": r[5], "keterangan": r[6], "dibatalkan": r[7]}
            for r in cur.fetchall()]


@router.post("/potongan", status_code=status.HTTP_201_CREATED)
def potongan_baru(body: PotonganIn, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (body.bulan,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Rekap bulan itu sudah dibekukan (P8)")
    cur.execute("INSERT INTO ops_potongan (bulan, sebab, sak, keterangan, created_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (body.bulan, body.sebab, body.sak, body.keterangan, user.id))
    pid = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_potongan_baru", "ops_potongan", pid, body.model_dump())
    conn.commit()
    return {"id": pid}


@router.post("/potongan/{row_id}/batal")
def potongan_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                   user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT bulan, sebab FROM ops_potongan WHERE id=%s", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    if r[1] in ("klaim_mutu", "klaim_angkut", "carry_over"):
        raise HTTPException(status_code=409, detail="Potongan klaim/carry-over dibatalkan lewat sumbernya")
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (r[0],))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Rekap bulan itu sudah dibekukan (P8)")
    _batal(cur, conn, user, "ops_potongan", row_id, body.alasan, "ops_potongan_batal")
    conn.commit()
    return {"ok": True}


# ============================================================ MESIN BONUS (K5 Konsep B)
def hitung_rekap(cur, bulan: str, karyawan_id: int) -> dict:
    akhir = _bulan_akhir(bulan)
    kg_per_sak = _param(cur, "kg_per_sak", akhir)
    sak_m3 = _param(cur, "sak_per_m3_kks", akhir)
    cap = _param(cur, "bonus_cap_bulan", akhir)
    # BAP bertanggal bulan M yang tertaut ke >=1 pengiriman aktif (dihitung sekali per BAP)
    cur.execute("SELECT DISTINCT b.id, b.no_bap, b.total_qty, lower(b.satuan) FROM ops_pengiriman p JOIN bap b ON b.id=p.bap_id "
                "WHERE p.dibatalkan_pada IS NULL AND to_char(b.tgl_bap,'YYYY-MM')=%s", (bulan,))
    sak_bap, m3_tanpa, rincian_bap, menunggu = 0.0, 0.0, [], False
    for bid, no_bap, qty, satuan in cur.fetchall():
        qty = _num(qty)
        if satuan in ("kg",):
            sak = qty / kg_per_sak if kg_per_sak else 0
        elif satuan in ("m3", "m³"):
            if sak_m3 is None:
                menunggu = True
                m3_tanpa += qty
                sak = 0
            else:
                sak = qty * sak_m3
        else:
            sak = 0
        sak_bap += sak
        rincian_bap.append({"bap_id": bid, "no_bap": no_bap, "qty": qty, "satuan": satuan, "sak": round(sak, 1)})
    sak_bap_i = int(round(sak_bap))
    cur.execute("SELECT coalesce(sum(jumlah_sak),0) FROM ops_pengiriman WHERE dibatalkan_pada IS NULL AND to_char(tanggal,'YYYY-MM')=%s", (bulan,))
    sak_dikirim = int(cur.fetchone()[0])
    cur.execute("SELECT coalesce(sum(sak),0) FROM ops_potongan WHERE bulan=%s AND dibatalkan_pada IS NULL", (bulan,))
    potongan = int(cur.fetchone()[0])
    netto_raw = sak_bap_i - potongan
    sak_netto = max(0, netto_raw)
    sisa_neg = max(0, -netto_raw)
    cur.execute("SELECT sak_dari, sak_sampai, tarif_per_sak FROM ops_tarif_bonus WHERE dibatalkan_pada IS NULL AND berlaku_mulai<=%s "
                "AND (berlaku_sampai IS NULL OR berlaku_sampai>=%s) ORDER BY jenjang", (akhir, akhir))
    tarif = cur.fetchall()
    bonus_jenjang = hitung_jenjang(sak_netto, tarif, cap)
    cur.execute("SELECT coalesce(sum(jumlah_sak_diklaim),0) FROM ops_klaim WHERE dibatalkan_pada IS NULL AND to_char(tanggal_terima,'YYYY-MM')=%s", (bulan,))
    sak_klaim = int(cur.fetchone()[0])
    pct = round(sak_klaim * 100.0 / sak_dikirim, 3) if sak_dikirim else 0.0
    cur.execute("SELECT ops_pengali(%s, %s)", (pct, akhir))
    r = cur.fetchone()
    pengali = _num(r[0]) if r and r[0] is not None else 1.0
    bonus = round(bonus_jenjang * pengali, 2)
    return {"bulan": bulan, "karyawan_id": karyawan_id, "sak_bap": sak_bap_i, "m3_kks_tanpa_konversi": round(m3_tanpa, 3),
            "sak_dikirim": sak_dikirim, "potongan": potongan, "sak_netto": sak_netto, "sisa_negatif": sisa_neg,
            "bonus_jenjang": bonus_jenjang, "sak_klaim": sak_klaim, "pct_klaim": pct, "pengali": pengali, "bonus_bulan": bonus,
            "status": "menunggu_parameter" if menunggu else "draft",
            "rincian": {"bap": rincian_bap, "kg_per_sak": kg_per_sak, "sak_per_m3_kks": sak_m3, "cap": cap,
                        "tarif": [[a, b, _num(c)] for a, b, c in tarif]}}


def _simpan_rekap(cur, r):
    import json
    cur.execute("INSERT INTO ops_rekap_bonus_bulanan (bulan, karyawan_id, sak_bap, m3_kks_tanpa_konversi, sak_dikirim, potongan, sak_netto, "
                "sisa_negatif, bonus_jenjang, sak_klaim, pct_klaim, pengali, bonus_bulan, status, rincian, dihitung_pada) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (bulan, karyawan_id) DO UPDATE SET "
                "sak_bap=EXCLUDED.sak_bap, m3_kks_tanpa_konversi=EXCLUDED.m3_kks_tanpa_konversi, sak_dikirim=EXCLUDED.sak_dikirim, "
                "potongan=EXCLUDED.potongan, sak_netto=EXCLUDED.sak_netto, sisa_negatif=EXCLUDED.sisa_negatif, bonus_jenjang=EXCLUDED.bonus_jenjang, "
                "sak_klaim=EXCLUDED.sak_klaim, pct_klaim=EXCLUDED.pct_klaim, pengali=EXCLUDED.pengali, bonus_bulan=EXCLUDED.bonus_bulan, "
                "status=EXCLUDED.status, rincian=EXCLUDED.rincian, dihitung_pada=now() "
                "WHERE ops_rekap_bonus_bulanan.status <> 'dibekukan' RETURNING id, status",
                (r["bulan"], r["karyawan_id"], r["sak_bap"], r["m3_kks_tanpa_konversi"], r["sak_dikirim"], r["potongan"], r["sak_netto"],
                 r["sisa_negatif"], r["bonus_jenjang"], r["sak_klaim"], r["pct_klaim"], r["pengali"], r["bonus_bulan"], r["status"],
                 json.dumps(r["rincian"], default=str)))
    return cur.fetchone()


def _baca_rekap(cur, bulan, karyawan_id):
    cur.execute("SELECT id, bulan, karyawan_id, sak_bap, m3_kks_tanpa_konversi, sak_dikirim, potongan, sak_netto, sisa_negatif, bonus_jenjang, "
                "sak_klaim, pct_klaim, pengali, bonus_bulan, status, rincian, dibekukan_pada FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND karyawan_id=%s",
                (bulan, karyawan_id))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "bulan": r[1], "karyawan_id": r[2], "sak_bap": r[3], "m3_kks_tanpa_konversi": _num(r[4]), "sak_dikirim": r[5],
            "potongan": r[6], "sak_netto": r[7], "sisa_negatif": r[8], "bonus_jenjang": _num(r[9]), "sak_klaim": r[10], "pct_klaim": _num(r[11]),
            "pengali": _num(r[12]), "bonus_bulan": _num(r[13]), "status": r[14], "rincian": r[15], "dibekukan_pada": r[16]}


@router.get("/bonus/rekap")
def bonus_rekap(bulan: str, karyawan_id: Optional[int] = None, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    """Owner: karyawan_id bebas (default: semua kepala aktif). Kepala: hanya rekap miliknya.
    Rekap 'dibekukan' dibaca apa adanya (P8); selain itu dihitung ulang dan disimpan sebagai draft."""
    cur = conn.cursor()
    if user.is_owner:
        if karyawan_id:
            ids = [karyawan_id]
        else:
            cur.execute("SELECT id FROM ops_karyawan WHERE peran='kepala' AND dibatalkan_pada IS NULL AND berlaku_mulai<=%s "
                        "AND (berlaku_sampai IS NULL OR berlaku_sampai>=%s)", (_bulan_akhir(bulan), date(int(bulan[:4]), int(bulan[5:7]), 1)))
            ids = [x[0] for x in cur.fetchall()]
    else:
        kid = _karyawan_untuk(cur, user)
        if not kid:
            raise HTTPException(status_code=403, detail="Akun ini tidak tertaut ke karyawan kepala")
        if karyawan_id and karyawan_id != kid:
            raise HTTPException(status_code=403, detail="Hanya rekap milik sendiri")
        ids = [kid]
    out = []
    for kid in ids:
        ada = _baca_rekap(cur, bulan, kid)
        if ada and ada["status"] == "dibekukan":
            out.append(ada)
            continue
        r = hitung_rekap(cur, bulan, kid)
        _simpan_rekap(cur, r)
        conn.commit()
        out.append(_baca_rekap(cur, bulan, kid))
    return out


@router.post("/bonus/rekap/{bulan}/{karyawan_id}/bekukan")
def bonus_bekukan(bulan: str, karyawan_id: int, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_owner)):
    """P8: bekukan = hitung final lalu kunci. Sisa negatif -> potongan carry_over di bulan berikutnya."""
    cur = conn.cursor()
    ada = _baca_rekap(cur, bulan, karyawan_id)
    if ada and ada["status"] == "dibekukan":
        raise HTTPException(status_code=409, detail="Sudah dibekukan")
    r = hitung_rekap(cur, bulan, karyawan_id)
    if r["status"] == "menunggu_parameter":
        raise HTTPException(status_code=409, detail="Ada BAP KKS (m3) tanpa parameter sak_per_m3_kks -- isi parameter dulu")
    _simpan_rekap(cur, r)
    cur.execute("UPDATE ops_rekap_bonus_bulanan SET status='dibekukan', dibekukan_oleh=%s, dibekukan_pada=now() WHERE bulan=%s AND karyawan_id=%s",
                (user.id, bulan, karyawan_id))
    if r["sisa_negatif"] > 0:
        nb = _bulan_berikut(bulan)
        cur.execute("INSERT INTO ops_potongan (bulan, sebab, sak, ref_tabel, ref_id, keterangan, created_by) VALUES (%s,'carry_over',%s,'ops_rekap_bonus_bulanan',%s,%s,%s)",
                    (nb, r["sisa_negatif"], karyawan_id, f"Sisa potongan negatif dari {bulan}", user.id))
    log_audit(conn, user.id, "ops_bonus_bekukan", "ops_rekap_bonus_bulanan", f"{bulan}/{karyawan_id}",
              {"bonus_bulan": r["bonus_bulan"], "sak_netto": r["sak_netto"], "carry_over": r["sisa_negatif"]})
    conn.commit()
    return _baca_rekap(cur, bulan, karyawan_id)


@router.get("/bonus/triwulan")
def bonus_triwulan(periode: str, conn=Depends(get_db),
                   user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    """periode 2026-Q3 = Jul-Sep. Total = Σ bonus_bulan rekap DIBEKUKAN. Kepala hanya miliknya."""
    y, q = int(periode[:4]), int(periode[-1])
    bulan_list = [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    cur = conn.cursor()
    if user.is_owner:
        cur.execute("SELECT DISTINCT karyawan_id FROM ops_rekap_bonus_bulanan WHERE bulan = ANY(%s)", (bulan_list,))
        ids = [x[0] for x in cur.fetchall()]
    else:
        kid = _karyawan_untuk(cur, user)
        if not kid:
            raise HTTPException(status_code=403, detail="Akun ini tidak tertaut ke karyawan kepala")
        ids = [kid]
    out = []
    for kid in ids:
        cur.execute("SELECT bulan, bonus_bulan, status FROM ops_rekap_bonus_bulanan WHERE karyawan_id=%s AND bulan = ANY(%s) ORDER BY bulan", (kid, bulan_list))
        rows = cur.fetchall()
        total = sum(_num(b) for _, b, st in rows if st == "dibekukan")
        cur.execute("SELECT id, total, tanggal_bayar FROM ops_pembayaran_bonus_triwulan WHERE periode=%s AND karyawan_id=%s AND dibatalkan_pada IS NULL", (periode, kid))
        pb = cur.fetchone()
        out.append({"periode": periode, "karyawan_id": kid, "bulan": [{"bulan": b, "bonus": _num(x), "status": st} for b, x, st in rows],
                    "semua_dibekukan": len(rows) == 3 and all(st == "dibekukan" for _, _, st in rows),
                    "total_dibekukan": round(total, 2), "dibayar": {"id": pb[0], "total": _num(pb[1]), "tanggal": pb[2]} if pb else None})
    return out


class BayarIn(BaseModel):
    periode: str = Field(pattern="^\\d{4}-Q[1-4]$")
    karyawan_id: int
    tanggal_bayar: date
    bukti: Optional[str] = None
    catatan: Optional[str] = None


@router.post("/bonus/triwulan/bayar", status_code=status.HTTP_201_CREATED)
def bonus_bayar(body: BayarIn, conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    y, q = int(body.periode[:4]), int(body.periode[-1])
    bulan_list = [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    cur.execute("SELECT count(*), coalesce(sum(bonus_bulan),0) FROM ops_rekap_bonus_bulanan WHERE karyawan_id=%s AND bulan = ANY(%s) AND status='dibekukan'",
                (body.karyawan_id, bulan_list))
    n, total = cur.fetchone()
    if n != 3:
        raise HTTPException(status_code=409, detail=f"Baru {n} dari 3 bulan yang dibekukan")
    cur.execute("SELECT 1 FROM ops_pembayaran_bonus_triwulan WHERE periode=%s AND karyawan_id=%s AND dibatalkan_pada IS NULL", (body.periode, body.karyawan_id))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Sudah dibayar")
    cur.execute("INSERT INTO ops_pembayaran_bonus_triwulan (periode, karyawan_id, total, tanggal_bayar, bukti, catatan, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id", (body.periode, body.karyawan_id, total, body.tanggal_bayar, body.bukti, body.catatan, user.id))
    pid = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_bonus_bayar", "ops_pembayaran_bonus_triwulan", pid, {"periode": body.periode, "total": _num(total)})
    conn.commit()
    return {"id": pid, "total": _num(total)}
