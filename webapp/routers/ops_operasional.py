"""
ops_operasional.py -- workspace PABRIK tahap B2-B4 (9 Sep 2026):
lot & tahap, terima truk, produksi sak, sak kosong, stok jadi, kas kecil, upah harian, cuaca.

Kontrak DESIGN-PABRIK.md:
  P1 append-only: koreksi = endpoint /batal yang menandai baris + (bila perlu) baris kompensasi.
  P2 saldo selalu SUM ledger (view v_ops_saldo_*), tidak pernah kolom yang diedit.
  P3 kubik dihitung DB (kolom generated p*l*t) -- klien hanya kirim p, l, t.
  P4 produksi = satu transaksi: sak kosong -N, stok jadi +N, baris produksi. Gagal satu = rollback.
  P5 saldo kas & sak kosong tidak boleh negatif -> 409.
  P6 satu petak satu lot aktif (unique index); lot habis tidak menerima truk.
  K2 admin & kepala setara penuh (require_pabrik_tulis); isi ulang kas = owner.
  K9 tahap tengah hanya status + tanggal, tanpa angka.
"""
import json
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import settings  # noqa: F401
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/ops", tags=["pabrik-operasional"])

TAHAP_URUT = ["curah", "giling", "basah", "jemur", "siap_karung", "habis"]


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


# F1 (27 Sep 2026): serialisasi tulis per ledger. Urutan kunci tetap kas < sak < stok (anti-deadlock);
# kunci transaksi lepas otomatis saat commit/rollback. Kelas & nomor SAMA dengan fungsi DB
# ops_kunci_ledger() -- trigger saldo (F2, migrasi 2026-09-27) memakai kunci yang sama sebagai pagar kedua.
KUNCI_KELAS = 77301
KUNCI_LEDGER = {"kas": 1, "sak": 2, "stok": 3}


def _kunci(cur, *ledger):
    for nama in sorted(set(ledger), key=KUNCI_LEDGER.__getitem__):
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (KUNCI_KELAS, KUNCI_LEDGER[nama]))


def _uang(v) -> Decimal:
    """T6: uang dihitung Decimal 2 desimal (ROUND_HALF_UP), bukan float."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _param(cur, kode, tgl=None):
    cur.execute("SELECT ops_param(%s, %s)", (kode, tgl or date.today()))
    r = cur.fetchone()
    return _num(r[0]) if r and r[0] is not None else None


def _saldo(cur):
    cur.execute("SELECT saldo, rusak_belum_retur FROM v_ops_saldo_sak_kosong")
    sk, rusak = cur.fetchone()
    cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
    sj = cur.fetchone()[0]
    cur.execute("SELECT saldo FROM v_ops_saldo_kas")
    kas = cur.fetchone()[0]
    return {"sak_kosong": sk, "sak_rusak_belum_retur": rusak, "stok_jadi": sj, "kas": _num(kas)}


def _batal(cur, conn, user, tabel, row_id, alasan, aksi):
    """P1: tandai baris dibatalkan; baris tidak pernah dihapus."""
    cur.execute(f"SELECT dibatalkan_pada FROM {tabel} WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Baris tidak ditemukan")
    if r[0] is not None:
        raise HTTPException(status_code=409, detail="Sudah dibatalkan sebelumnya")
    cur.execute(f"UPDATE {tabel} SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s WHERE id=%s",
                (user.id, alasan, row_id))
    log_audit(conn, user.id, aksi, tabel, row_id, {"alasan": alasan})


class BatalIn(BaseModel):
    alasan: str = Field(min_length=3, max_length=300)


# ============================================================ saldo & ringkasan
@router.get("/saldo")
def saldo(conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    return _saldo(conn.cursor())


# ============================================================ LOT
class LotOut(BaseModel):
    lot_id: int
    nomor_lot: str
    petak_id: int
    petak: str
    status: str
    tanggal_buka: date
    tanggal_tutup: Optional[date]
    kubik_masuk: float
    sak_jadi: int
    sak_lolos_qc: int
    rendemen: Optional[float]
    sisa_wip_estimasi_kubik: Optional[float]
    umur_hari: int
    lewat_batas_karung: bool


class LotCreate(BaseModel):
    petak_id: int
    tanggal_buka: date


class TahapIn(BaseModel):
    tahap: str = Field(pattern="^(giling|basah|jemur|siap_karung|habis)$")
    tanggal_mulai: date
    ec: Optional[float] = Field(default=None, ge=0)
    kadar_air_pct: Optional[float] = Field(default=None, ge=0, le=100)
    catatan: Optional[str] = Field(default=None, max_length=300)


def _lot_rows(cur, where="", params=()):
    rend = _param(cur, "rendemen_sak_per_kubik") or 2.5
    cur.execute("SELECT lot_id, nomor_lot, petak_id, petak, status, tanggal_buka, tanggal_tutup, kubik_masuk, "
                "sak_jadi, sak_lolos_qc, umur_hari, lewat_batas_karung FROM v_ops_lot_ringkas " + where +
                " ORDER BY status='habis', tanggal_buka DESC, lot_id DESC", params)
    out = []
    for r in cur.fetchall():
        kubik = _num(r[7])
        rendemen = round(r[8] / kubik, 2) if kubik and kubik > 0 else None
        sisa = round(kubik - r[8] / rend, 3) if kubik and r[4] != "habis" else None
        out.append(LotOut(lot_id=r[0], nomor_lot=r[1], petak_id=r[2], petak=r[3], status=r[4], tanggal_buka=r[5],
                          tanggal_tutup=r[6], kubik_masuk=kubik, sak_jadi=r[8], sak_lolos_qc=r[9], rendemen=rendemen,
                          sisa_wip_estimasi_kubik=sisa, umur_hari=r[10], lewat_batas_karung=r[11]))
    return out


@router.get("/lot", response_model=List[LotOut])
def list_lot(hanya_aktif: bool = False, conn=Depends(get_db),
             user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    return _lot_rows(conn.cursor(), "WHERE status <> 'habis'" if hanya_aktif else "")


@router.post("/lot", response_model=LotOut, status_code=status.HTTP_201_CREATED)
def lot_buka(body: LotCreate, conn=Depends(get_db),
             user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    cur.execute("SELECT nomor, aktif FROM ops_petak WHERE id=%s", (body.petak_id,))
    pt = cur.fetchone()
    if not pt or not pt[1]:
        raise HTTPException(status_code=422, detail="Petak tidak ada / nonaktif")
    cur.execute("SELECT nomor_lot FROM ops_lot WHERE petak_id=%s AND status<>'habis' AND dibatalkan_pada IS NULL",
                (body.petak_id,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Petak {pt[0]} masih punya lot aktif (P6: 1 petak = 1 lot)")
    tahun = body.tanggal_buka.year
    cur.execute("SELECT count(*) FROM ops_lot WHERE nomor_lot LIKE %s", (f"{tahun}-%",))
    nomor = f"{tahun}-{cur.fetchone()[0] + 1:03d}"
    cur.execute("INSERT INTO ops_lot (petak_id, nomor_lot, tanggal_buka, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
                (body.petak_id, nomor, body.tanggal_buka, user.id))
    lot_id = cur.fetchone()[0]
    cur.execute("INSERT INTO ops_lot_tahap (lot_id, tahap, tanggal_mulai, created_by) VALUES (%s,'curah',%s,%s)",
                (lot_id, body.tanggal_buka, user.id))
    log_audit(conn, user.id, "ops_lot_buka", "ops_lot", lot_id, {"petak": pt[0], "nomor_lot": nomor})
    conn.commit()
    return _lot_rows(cur, "WHERE lot_id=%s", (lot_id,))[0]


@router.get("/lot/{lot_id}/tahap")
def lot_tahap(lot_id: int, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT id, tahap, tanggal_mulai, ec, kadar_air_pct, catatan, created_by FROM ops_lot_tahap "
                "WHERE lot_id=%s ORDER BY id", (lot_id,))
    return [{"id": r[0], "tahap": r[1], "tanggal_mulai": r[2], "ec": _num(r[3]), "kadar_air_pct": _num(r[4]),
             "catatan": r[5], "created_by": r[6]} for r in cur.fetchall()]


@router.post("/lot/{lot_id}/tahap", response_model=LotOut)
def lot_ubah_tahap(lot_id: int, body: TahapIn, conn=Depends(get_db),
                   user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """Tahap hanya boleh maju SATU langkah (K9: tanpa angka di tengah). siap_karung wajib
    EC & kadar air bila parameternya sudah diisi owner; habis = tutup lot + rendemen final."""
    cur = conn.cursor()
    cur.execute("SELECT status, tanggal_buka FROM ops_lot WHERE id=%s AND dibatalkan_pada IS NULL FOR UPDATE", (lot_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Lot tidak ditemukan")
    skrg = r[0]
    if skrg == "habis":
        raise HTTPException(status_code=409, detail="Lot sudah habis")
    if TAHAP_URUT.index(body.tahap) != TAHAP_URUT.index(skrg) + 1:
        raise HTTPException(status_code=422, detail=f"Dari '{skrg}' hanya boleh ke '{TAHAP_URUT[TAHAP_URUT.index(skrg)+1]}'")
    if body.tanggal_mulai < r[1]:
        raise HTTPException(status_code=422, detail="Tanggal tahap mendahului tanggal buka lot")
    peringatan = []
    if body.tahap == "siap_karung":
        ec_max, ka_max = _param(cur, "ec_max"), _param(cur, "kadar_air_max_pct")
        if ec_max is not None and body.ec is None:
            raise HTTPException(status_code=422, detail="EC wajib diisi untuk siap karung")
        if ka_max is not None and body.kadar_air_pct is None:
            raise HTTPException(status_code=422, detail="Kadar air wajib diisi untuk siap karung")
        if ec_max is not None and body.ec > ec_max:
            peringatan.append(f"EC {body.ec} > batas {ec_max}")
        if ka_max is not None and body.kadar_air_pct > ka_max:
            peringatan.append(f"Kadar air {body.kadar_air_pct}% > batas {ka_max}%")
    cur.execute("INSERT INTO ops_lot_tahap (lot_id, tahap, tanggal_mulai, ec, kadar_air_pct, catatan, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (lot_id, body.tahap, body.tanggal_mulai, body.ec, body.kadar_air_pct, body.catatan, user.id))
    if body.tahap == "habis":
        cur.execute("UPDATE ops_lot SET status='habis', tanggal_tutup=%s WHERE id=%s", (body.tanggal_mulai, lot_id))
    else:
        cur.execute("UPDATE ops_lot SET status=%s WHERE id=%s", (body.tahap, lot_id))
    row = _lot_rows(cur, "WHERE lot_id=%s", (lot_id,))[0]
    detail = {"dari": skrg, "ke": body.tahap, "peringatan": peringatan}
    if body.tahap == "habis":
        rmin, rmax = _param(cur, "rendemen_min"), _param(cur, "rendemen_max")
        detail["rendemen_final"] = row.rendemen
        if row.rendemen is not None and rmin is not None and rmax is not None and not (rmin <= row.rendemen <= rmax):
            detail["rendemen_di_luar_kisaran"] = True
    log_audit(conn, user.id, "ops_lot_tahap", "ops_lot", lot_id, detail)
    conn.commit()
    return row


# ============================================================ TERIMA TRUK
class PenerimaanIn(BaseModel):
    tanggal: date
    jam: time
    nopol: str = Field(min_length=3, max_length=20)
    pemasok_id: int
    p_m: float = Field(gt=0, le=30)
    l_m: float = Field(gt=0, le=30)
    t_m: float = Field(gt=0, le=10)
    lot_id: int
    foto_plat: Optional[str] = None
    foto_muatan: Optional[str] = None
    catatan: Optional[str] = Field(default=None, max_length=300)


class PenerimaanOut(BaseModel):
    id: int
    no_urut: int
    tahun: int
    tanggal: date
    jam: str
    nopol: str
    pemasok_id: int
    pemasok: str
    p_m: float
    l_m: float
    t_m: float
    kubik_masuk: float
    lot_id: int
    nomor_lot: str
    foto_plat: Optional[str]
    foto_muatan: Optional[str]
    catatan: Optional[str]
    dibatalkan: bool


def _penerimaan_rows(cur, where, params):
    cur.execute("SELECT p.id, p.no_urut, p.tahun, p.tanggal, p.jam, p.nopol, p.pemasok_id, pm.nama, p.p_m, p.l_m, p.t_m, "
                "p.kubik_masuk, p.lot_id, l.nomor_lot, p.foto_plat, p.foto_muatan, p.catatan, p.dibatalkan_pada IS NOT NULL "
                "FROM ops_penerimaan p JOIN ops_pemasok pm ON pm.id=p.pemasok_id JOIN ops_lot l ON l.id=p.lot_id "
                + where + " ORDER BY p.tanggal DESC, p.jam DESC, p.id DESC", params)
    return [PenerimaanOut(id=r[0], no_urut=r[1], tahun=r[2], tanggal=r[3], jam=str(r[4])[:5], nopol=r[5], pemasok_id=r[6],
                          pemasok=r[7], p_m=_num(r[8]), l_m=_num(r[9]), t_m=_num(r[10]), kubik_masuk=_num(r[11]),
                          lot_id=r[12], nomor_lot=r[13], foto_plat=r[14], foto_muatan=r[15], catatan=r[16], dibatalkan=r[17])
            for r in cur.fetchall()]


@router.get("/penerimaan", response_model=List[PenerimaanOut])
def list_penerimaan(bulan: Optional[str] = None, lot_id: Optional[int] = None, conn=Depends(get_db),
                    user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    where, params = "WHERE 1=1", []
    if bulan:
        where += " AND to_char(p.tanggal,'YYYY-MM')=%s"
        params.append(bulan)
    if lot_id:
        where += " AND p.lot_id=%s"
        params.append(lot_id)
    return _penerimaan_rows(conn.cursor(), where, tuple(params))


@router.post("/penerimaan", response_model=PenerimaanOut, status_code=status.HTTP_201_CREATED)
def penerimaan_baru(body: PenerimaanIn, conn=Depends(get_db),
                    user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    cur.execute("SELECT status FROM ops_lot WHERE id=%s AND dibatalkan_pada IS NULL", (body.lot_id,))
    lot = cur.fetchone()
    if not lot:
        raise HTTPException(status_code=422, detail="Lot tidak ditemukan")
    if lot[0] != "curah":
        raise HTTPException(status_code=409, detail=f"Lot sudah tahap '{lot[0]}' -- truk hanya boleh masuk ke lot tahap curah (P6)")
    cur.execute("SELECT aktif FROM ops_pemasok WHERE id=%s AND jenis='sabut'", (body.pemasok_id,))
    pm = cur.fetchone()
    if not pm or not pm[0]:
        raise HTTPException(status_code=422, detail="Pemasok sabut tidak ada / nonaktif")
    tahun = body.tanggal.year
    cur.execute("SELECT coalesce(max(no_urut),0)+1 FROM ops_penerimaan WHERE tahun=%s", (tahun,))
    no_urut = cur.fetchone()[0]
    nopol = body.nopol.strip().upper().replace(" ", "")
    cur.execute("SELECT 1 FROM ops_penerimaan WHERE nopol=%s AND tanggal=%s AND jam=%s AND dibatalkan_pada IS NULL",
                (nopol, body.tanggal, body.jam))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Truk dengan nopol, tanggal, dan jam yang sama sudah tercatat")
    cur.execute("INSERT INTO ops_penerimaan (tahun, no_urut, tanggal, jam, nopol, pemasok_id, p_m, l_m, t_m, lot_id, "
                "foto_plat, foto_muatan, catatan, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, kubik_masuk",
                (tahun, no_urut, body.tanggal, body.jam, nopol, body.pemasok_id, body.p_m, body.l_m, body.t_m,
                 body.lot_id, body.foto_plat, body.foto_muatan, body.catatan, user.id))
    new_id, kubik = cur.fetchone()
    log_audit(conn, user.id, "ops_penerimaan_baru", "ops_penerimaan", new_id,
              {"no_urut": no_urut, "nopol": nopol, "kubik": _num(kubik), "lot_id": body.lot_id})
    conn.commit()
    return _penerimaan_rows(cur, "WHERE p.id=%s", (new_id,))[0]


@router.post("/penerimaan/{row_id}/batal", response_model=PenerimaanOut)
def penerimaan_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                     user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _batal(cur, conn, user, "ops_penerimaan", row_id, body.alasan, "ops_penerimaan_batal")
    conn.commit()
    return _penerimaan_rows(cur, "WHERE p.id=%s", (row_id,))[0]


# ============================================================ SAK KOSONG
class SakIn(BaseModel):
    tanggal: date
    jenis: str = Field(pattern="^(beli|rusak|retur)$")  # F3 (27 Sep 2026): opname hanya lewat /ops/opname (owner)
    jumlah: int = Field(ge=0)
    pemasok_id: Optional[int] = None
    harga_per_sak: Optional[float] = Field(default=None, ge=0)
    foto_nota: Optional[str] = None
    keterangan: Optional[str] = Field(default=None, max_length=300)
    opname_saldo_fisik: Optional[int] = Field(default=None, ge=0)


class SakOut(BaseModel):
    id: int
    tanggal: date
    jenis: str
    delta: int
    jumlah: int
    pemasok_id: Optional[int]
    harga_per_sak: Optional[float]
    foto_nota: Optional[str]
    ref_produksi_id: Optional[int]
    ref_kas_id: Optional[int]
    keterangan: Optional[str]
    dibatalkan: bool


def _sak_rows(cur, where="", params=()):
    cur.execute("SELECT id, tanggal, jenis, delta, jumlah, pemasok_id, harga_per_sak, foto_nota, ref_produksi_id, ref_kas_id, "
                "keterangan, dibatalkan_pada IS NOT NULL FROM ops_sak_kosong_mutasi " + where + " ORDER BY tanggal DESC, id DESC", params)
    return [SakOut(id=r[0], tanggal=r[1], jenis=r[2], delta=r[3], jumlah=r[4], pemasok_id=r[5], harga_per_sak=_num(r[6]),
                   foto_nota=r[7], ref_produksi_id=r[8], ref_kas_id=r[9], keterangan=r[10], dibatalkan=r[11]) for r in cur.fetchall()]


@router.get("/sak", response_model=List[SakOut])
def list_sak(bulan: Optional[str] = None, conn=Depends(get_db),
             user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    if bulan:
        return _sak_rows(conn.cursor(), "WHERE to_char(tanggal,'YYYY-MM')=%s", (bulan,))
    return _sak_rows(conn.cursor())


@router.post("/sak", response_model=SakOut, status_code=status.HTTP_201_CREATED)
def sak_mutasi(body: SakIn, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """beli: +N dan otomatis kas keluar kategori 'sak' (P5: kas cukup). rusak: -N (masuk daftar
    menunggu retur). retur: 0 (menutup rusak). opname: delta = fisik - saldo sistem."""
    cur = conn.cursor()
    _kunci(cur, "kas", "sak")
    cur.execute("SELECT saldo, rusak_belum_retur FROM v_ops_saldo_sak_kosong")
    sk, rusak = cur.fetchone()
    kas_id = None
    if body.jenis == "beli":
        if body.jumlah <= 0 or body.harga_per_sak is None or body.pemasok_id is None:
            raise HTTPException(status_code=422, detail="beli butuh jumlah>0, harga_per_sak, pemasok_id")
        cur.execute("SELECT aktif FROM ops_pemasok WHERE id=%s AND jenis='sak'", (body.pemasok_id,))
        pm = cur.fetchone()
        if not pm or not pm[0]:
            raise HTTPException(status_code=422, detail="Pemasok sak tidak ada / nonaktif")
        nominal = _uang(Decimal(body.jumlah) * _uang(body.harga_per_sak))
        cur.execute("SELECT saldo FROM v_ops_saldo_kas")
        if Decimal(cur.fetchone()[0]) - nominal < 0:
            raise HTTPException(status_code=409, detail=f"Kas kecil tidak cukup untuk beli sak Rp{nominal:,.0f} (P5)")
        delta = body.jumlah
        cur.execute("INSERT INTO ops_kas_kecil (tanggal, jenis, kategori, nominal, keterangan, foto_nota, created_by) "
                    "VALUES (%s,'keluar','sak',%s,%s,%s,%s) RETURNING id",
                    (body.tanggal, nominal, f"Beli {body.jumlah} sak bekas @Rp{body.harga_per_sak:,.0f}. {body.keterangan or ''}".strip(),
                     body.foto_nota, user.id))
        kas_id = cur.fetchone()[0]
    elif body.jenis == "rusak":
        if body.jumlah <= 0:
            raise HTTPException(status_code=422, detail="jumlah harus > 0")
        if sk - body.jumlah < 0:
            raise HTTPException(status_code=409, detail=f"Saldo sak kosong {sk}, tidak cukup untuk dicatat rusak {body.jumlah} (P5)")
        delta = -body.jumlah
    elif body.jenis == "retur":
        if body.jumlah <= 0 or body.jumlah > rusak:
            raise HTTPException(status_code=409, detail=f"Sak rusak menunggu retur hanya {rusak}")
        delta = 0
    else:  # F3 (27 Sep 2026): opname sak kosong hanya lewat POST /ops/opname (owner, saksi & berita acara)
        raise HTTPException(status_code=422, detail="Opname sak kosong hanya lewat menu Stock Opname (owner)")
    cur.execute("INSERT INTO ops_sak_kosong_mutasi (tanggal, jenis, delta, jumlah, pemasok_id, harga_per_sak, foto_nota, "
                "keterangan, ref_kas_id, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal, body.jenis, delta, abs(delta) if body.jenis == "opname" else body.jumlah, body.pemasok_id,
                 _uang(body.harga_per_sak) if body.harga_per_sak is not None else None, body.foto_nota, body.keterangan, kas_id, user.id))
    new_id = cur.fetchone()[0]
    if kas_id:
        cur.execute("UPDATE ops_kas_kecil SET ref_sak_mutasi_id=%s WHERE id=%s", (new_id, kas_id))
    log_audit(conn, user.id, "ops_sak_" + body.jenis, "ops_sak_kosong_mutasi", new_id, {"delta": delta, "kas_id": kas_id})
    conn.commit()
    return _sak_rows(cur, "WHERE id=%s", (new_id,))[0]


@router.post("/sak/{row_id}/batal", response_model=SakOut)
def sak_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "kas", "sak")
    cur.execute("SELECT jenis, delta, ref_kas_id, ref_produksi_id FROM ops_sak_kosong_mutasi WHERE id=%s", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    if r[0] in ("opname", "dipakai"):
        # F3 (27 Sep 2026): opname dibatalkan lewat /ops/opname/{id}/batal (owner); 'dipakai' lewat produksinya
        raise HTTPException(status_code=409, detail="Mutasi opname/produksi tidak bisa dibatalkan dari menu Sak -- batalkan dari dokumen asalnya")
    if r[3]:
        raise HTTPException(status_code=409, detail="Mutasi ini milik produksi -- batalkan produksinya")
    cur.execute("SELECT saldo FROM v_ops_saldo_sak_kosong")
    if cur.fetchone()[0] - r[1] < 0:
        raise HTTPException(status_code=409, detail="Pembatalan membuat saldo sak negatif (P5)")
    _batal(cur, conn, user, "ops_sak_kosong_mutasi", row_id, body.alasan, "ops_sak_batal")
    if r[2]:
        _batal(cur, conn, user, "ops_kas_kecil", r[2], f"Ikut batal sak #{row_id}: {body.alasan}", "ops_kas_batal")
    conn.commit()
    return _sak_rows(cur, "WHERE id=%s", (row_id,))[0]


# ============================================================ PRODUKSI (P4)
class ProduksiIn(BaseModel):
    tanggal: date
    lot_id: int
    jumlah_sak: int = Field(gt=0, le=5000)
    berat_sampel: Optional[List[float]] = None
    catatan: Optional[str] = Field(default=None, max_length=300)


class ProduksiOut(BaseModel):
    id: int
    tanggal: date
    lot_id: int
    nomor_lot: str
    jumlah_sak: int
    berat_sampel: Optional[List[float]]
    status_qc: str
    catatan: Optional[str]
    dibatalkan: bool


def _produksi_rows(cur, where="", params=()):
    cur.execute("SELECT s.id, s.tanggal, s.lot_id, l.nomor_lot, s.jumlah_sak, s.berat_sampel, s.status_qc, s.catatan, "
                "s.dibatalkan_pada IS NOT NULL FROM ops_produksi_sak s JOIN ops_lot l ON l.id=s.lot_id " + where +
                " ORDER BY s.tanggal DESC, s.id DESC", params)
    return [ProduksiOut(id=r[0], tanggal=r[1], lot_id=r[2], nomor_lot=r[3], jumlah_sak=r[4], berat_sampel=r[5],
                        status_qc=r[6], catatan=r[7], dibatalkan=r[8]) for r in cur.fetchall()]


@router.get("/produksi", response_model=List[ProduksiOut])
def list_produksi(bulan: Optional[str] = None, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    if bulan:
        return _produksi_rows(conn.cursor(), "WHERE to_char(s.tanggal,'YYYY-MM')=%s", (bulan,))
    return _produksi_rows(conn.cursor())


@router.post("/produksi", response_model=ProduksiOut, status_code=status.HTTP_201_CREATED)
def produksi_baru(body: ProduksiIn, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """P4: satu transaksi -- produksi + sak kosong -N + stok jadi +N. QC: 5 sampel, lolos bila
    >=4 dari 5 >= berat_sak_min_kg; parameter belum diisi -> 'belum'."""
    cur = conn.cursor()
    _kunci(cur, "sak", "stok")
    cur.execute("SELECT status FROM ops_lot WHERE id=%s AND dibatalkan_pada IS NULL FOR UPDATE", (body.lot_id,))
    lot = cur.fetchone()
    if not lot:
        raise HTTPException(status_code=422, detail="Lot tidak ditemukan")
    if lot[0] != "siap_karung":
        raise HTTPException(status_code=409, detail=f"Lot tahap '{lot[0]}' -- pengarungan hanya di tahap siap_karung")
    if body.berat_sampel is not None and len(body.berat_sampel) != 5:
        raise HTTPException(status_code=422, detail="berat_sampel harus tepat 5 angka (SOP QC harian)")
    cur.execute("SELECT saldo FROM v_ops_saldo_sak_kosong")
    sk = cur.fetchone()[0]
    if sk - body.jumlah_sak < 0:
        raise HTTPException(status_code=409, detail=f"Sak kosong hanya {sk}, tidak cukup untuk {body.jumlah_sak} sak (P5)")
    bmin = _param(cur, "berat_sak_min_kg", body.tanggal)
    if bmin is None or body.berat_sampel is None:
        qc = "belum"
    else:
        qc = "lolos" if sum(1 for b in body.berat_sampel if b >= bmin) >= 4 else "gagal"
    try:
        cur.execute("INSERT INTO ops_produksi_sak (tanggal, lot_id, jumlah_sak, berat_sampel, status_qc, catatan, created_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (body.tanggal, body.lot_id, body.jumlah_sak, json.dumps(body.berat_sampel) if body.berat_sampel else None,
                     qc, body.catatan, user.id))
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO ops_sak_kosong_mutasi (tanggal, jenis, delta, jumlah, ref_produksi_id, keterangan, created_by) "
                    "VALUES (%s,'dipakai',%s,%s,%s,%s,%s)",
                    (body.tanggal, -body.jumlah_sak, body.jumlah_sak, pid, f"Produksi #{pid}", user.id))
        cur.execute("INSERT INTO ops_stok_jadi_mutasi (tanggal, jenis, delta, ref_produksi_id, keterangan, created_by) "
                    "VALUES (%s,'produksi',%s,%s,%s,%s)", (body.tanggal, body.jumlah_sak, pid, f"Produksi #{pid}", user.id))
        log_audit(conn, user.id, "ops_produksi_baru", "ops_produksi_sak", pid,
                  {"lot_id": body.lot_id, "jumlah_sak": body.jumlah_sak, "qc": qc})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _produksi_rows(cur, "WHERE s.id=%s", (pid,))[0]


@router.post("/produksi/{row_id}/batal", response_model=ProduksiOut)
def produksi_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                   user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """Membatalkan produksi = membatalkan ketiga baris (produksi, sak dipakai, stok jadi). Ditolak
    bila stok jadi sudah terpakai (dikirim) sehingga saldo akan negatif (P5)."""
    cur = conn.cursor()
    _kunci(cur, "sak", "stok")
    cur.execute("SELECT jumlah_sak, dibatalkan_pada FROM ops_produksi_sak WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Produksi tidak ditemukan")
    if r[1]:
        raise HTTPException(status_code=409, detail="Sudah dibatalkan")
    cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
    if cur.fetchone()[0] - r[0] < 0:
        raise HTTPException(status_code=409, detail="Stok jadi sudah terpakai; pembatalan membuat saldo negatif (P5)")
    _batal(cur, conn, user, "ops_produksi_sak", row_id, body.alasan, "ops_produksi_batal")
    for tabel in ("ops_sak_kosong_mutasi", "ops_stok_jadi_mutasi"):
        cur.execute(f"UPDATE {tabel} SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s "
                    f"WHERE ref_produksi_id=%s AND dibatalkan_pada IS NULL", (user.id, body.alasan, row_id))
    conn.commit()
    return _produksi_rows(cur, "WHERE s.id=%s", (row_id,))[0]


# ============================================================ KAS KECIL & UPAH
class KasIn(BaseModel):
    tanggal: date
    jenis: str = Field(pattern="^(keluar|isi_ulang)$")
    kategori: str = Field(default="lain", pattern="^(bbm|perbaikan|konsumsi|lain)$")
    nominal: float = Field(gt=0)
    keterangan: Optional[str] = Field(default=None, max_length=300)
    foto_nota: Optional[str] = None


class KasOut(BaseModel):
    id: int
    tanggal: date
    jenis: str
    kategori: str
    nominal: float
    keterangan: Optional[str]
    foto_nota: Optional[str]
    ref_sak_mutasi_id: Optional[int]
    created_by: int
    dibatalkan: bool


def _kas_rows(cur, where="", params=()):
    cur.execute("SELECT id, tanggal, jenis, kategori, nominal, keterangan, foto_nota, ref_sak_mutasi_id, created_by, "
                "dibatalkan_pada IS NOT NULL FROM ops_kas_kecil " + where + " ORDER BY tanggal DESC, id DESC", params)
    return [KasOut(id=r[0], tanggal=r[1], jenis=r[2], kategori=r[3], nominal=_num(r[4]), keterangan=r[5], foto_nota=r[6],
                   ref_sak_mutasi_id=r[7], created_by=r[8], dibatalkan=r[9]) for r in cur.fetchall()]


@router.get("/kas", response_model=List[KasOut])
def list_kas(bulan: Optional[str] = None, conn=Depends(get_db),
             user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    if bulan:
        return _kas_rows(conn.cursor(), "WHERE to_char(tanggal,'YYYY-MM')=%s", (bulan,))
    return _kas_rows(conn.cursor())


@router.post("/kas", response_model=KasOut, status_code=status.HTTP_201_CREATED)
def kas_baru(body: KasIn, conn=Depends(get_db),
             user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "kas")
    if body.jenis == "isi_ulang":
        if not user.is_owner:
            raise HTTPException(status_code=403, detail="Isi ulang kas kecil hanya Owner")
        kategori = "isi_ulang"
    else:
        kategori = body.kategori
        cur.execute("SELECT saldo FROM v_ops_saldo_kas")
        if Decimal(cur.fetchone()[0]) - _uang(body.nominal) < 0:
            raise HTTPException(status_code=409, detail="Saldo kas kecil tidak cukup (P5)")
    cur.execute("INSERT INTO ops_kas_kecil (tanggal, jenis, kategori, nominal, keterangan, foto_nota, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal, body.jenis, kategori, _uang(body.nominal), body.keterangan, body.foto_nota, user.id))
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_kas_" + body.jenis, "ops_kas_kecil", new_id, {"nominal": body.nominal, "kategori": kategori})
    conn.commit()
    return _kas_rows(cur, "WHERE id=%s", (new_id,))[0]


@router.post("/kas/{row_id}/batal", response_model=KasOut)
def kas_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "kas")
    cur.execute("SELECT jenis, nominal, kategori, ref_sak_mutasi_id FROM ops_kas_kecil WHERE id=%s", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    if r[2] in ("sak", "upah") or r[3]:
        raise HTTPException(status_code=409, detail="Baris ini terikat beli sak / upah -- batalkan dari sana")
    if r[0] == "isi_ulang":
        if not user.is_owner:
            raise HTTPException(status_code=403, detail="Hanya Owner")
        cur.execute("SELECT saldo FROM v_ops_saldo_kas")
        if Decimal(cur.fetchone()[0]) - Decimal(r[1]) < 0:
            raise HTTPException(status_code=409, detail="Pembatalan isi ulang membuat saldo negatif (P5)")
    _batal(cur, conn, user, "ops_kas_kecil", row_id, body.alasan, "ops_kas_batal")
    conn.commit()
    return _kas_rows(cur, "WHERE id=%s", (row_id,))[0]


class UpahIn(BaseModel):
    tanggal: date
    nama: str = Field(min_length=2, max_length=120)
    peran: str = Field(pattern="^(buruh|langsir|supir)$")
    satuan: str = Field(pattern="^(hari|rit)$")
    jumlah: float = Field(gt=0, le=100)
    tarif: Optional[float] = Field(default=None, gt=0)
    catatan: Optional[str] = Field(default=None, max_length=300)


class UpahOut(BaseModel):
    id: int
    tanggal: date
    nama: str
    peran: str
    satuan: str
    jumlah: float
    tarif: float
    total: float
    kas_id: int
    catatan: Optional[str]
    dibatalkan: bool


def _upah_rows(cur, where="", params=()):
    cur.execute("SELECT id, tanggal, nama, peran, satuan, jumlah, tarif, total, kas_id, catatan, dibatalkan_pada IS NOT NULL "
                "FROM ops_upah_harian " + where + " ORDER BY tanggal DESC, id DESC", params)
    return [UpahOut(id=r[0], tanggal=r[1], nama=r[2], peran=r[3], satuan=r[4], jumlah=_num(r[5]), tarif=_num(r[6]),
                    total=_num(r[7]), kas_id=r[8], catatan=r[9], dibatalkan=r[10]) for r in cur.fetchall()]


@router.get("/upah", response_model=List[UpahOut])
def list_upah(bulan: Optional[str] = None, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    if bulan:
        return _upah_rows(conn.cursor(), "WHERE to_char(tanggal,'YYYY-MM')=%s", (bulan,))
    return _upah_rows(conn.cursor())


@router.post("/upah", response_model=UpahOut, status_code=status.HTTP_201_CREATED)
def upah_baru(body: UpahIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """K7: upah harian dibayar dari kas kecil (kategori upah). Tarif = parameter upah_<peran>
    bila tidak diisi; disimpan sebagai snapshot."""
    cur = conn.cursor()
    tarif = body.tarif if body.tarif is not None else _param(cur, "upah_" + body.peran, body.tanggal)
    if tarif is None:
        raise HTTPException(status_code=422, detail=f"Tarif upah {body.peran} belum diisi owner dan tidak dikirim")
    _kunci(cur, "kas")
    total = _uang(Decimal(str(body.jumlah)) * Decimal(str(tarif)))
    cur.execute("SELECT saldo FROM v_ops_saldo_kas")
    if Decimal(cur.fetchone()[0]) - total < 0:
        raise HTTPException(status_code=409, detail=f"Saldo kas kecil tidak cukup untuk upah Rp{total:,.0f} (P5)")
    cur.execute("INSERT INTO ops_kas_kecil (tanggal, jenis, kategori, nominal, keterangan, created_by) "
                "VALUES (%s,'keluar','upah',%s,%s,%s) RETURNING id",
                (body.tanggal, total, f"Upah {body.peran} {body.nama.strip()} {body.jumlah:g} {body.satuan}", user.id))
    kas_id = cur.fetchone()[0]
    cur.execute("INSERT INTO ops_upah_harian (tanggal, nama, peran, satuan, jumlah, tarif, total, kas_id, catatan, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal, body.nama.strip(), body.peran, body.satuan, body.jumlah, tarif, total, kas_id, body.catatan, user.id))
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_upah_baru", "ops_upah_harian", new_id, {"total": float(total), "kas_id": kas_id})
    conn.commit()
    return _upah_rows(cur, "WHERE id=%s", (new_id,))[0]


@router.post("/upah/{row_id}/batal", response_model=UpahOut)
def upah_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    _kunci(cur, "kas")
    cur.execute("SELECT kas_id FROM ops_upah_harian WHERE id=%s", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    _batal(cur, conn, user, "ops_upah_harian", row_id, body.alasan, "ops_upah_batal")
    _batal(cur, conn, user, "ops_kas_kecil", r[0], f"Ikut batal upah #{row_id}: {body.alasan}", "ops_kas_batal")
    conn.commit()
    return _upah_rows(cur, "WHERE id=%s", (row_id,))[0]


# ============================================================ HPP & CUACA
@router.get("/hpp")
def hpp_bulanan(conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    # PABRIK_B7_9SEP2026 (A5): kas keluar tanpa foto nota dikecualikan dari HPP, dilaporkan terpisah
    cur.execute("SELECT bulan, biaya_kas, sak_lolos_qc, biaya_tanpa_nota FROM v_ops_hpp_bulanan ORDER BY bulan DESC")
    return [{"bulan": r[0], "biaya_kas": _num(r[1]), "sak_lolos_qc": r[2], "biaya_tanpa_nota": _num(r[3]),
             "hpp_per_sak": round(_num(r[1]) / r[2], 2) if r[2] else None} for r in cur.fetchall()]


class CuacaIn(BaseModel):
    tanggal: date
    hujan_mm: Optional[float] = Field(default=None, ge=0)
    cuaca_teks: Optional[str] = Field(default=None, max_length=60)
    catatan: Optional[str] = Field(default=None, max_length=300)


@router.get("/cuaca")
def list_cuaca(hari: int = 14, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT tanggal, sumber, hujan_mm, suhu_max_c, cuaca_teks, catatan FROM ops_cuaca "
                "WHERE tanggal >= CURRENT_DATE - %s ORDER BY tanggal DESC, sumber", (hari,))
    return [{"tanggal": r[0], "sumber": r[1], "hujan_mm": _num(r[2]), "suhu_max_c": _num(r[3]), "cuaca_teks": r[4],
             "catatan": r[5]} for r in cur.fetchall()]


@router.post("/cuaca", status_code=status.HTTP_201_CREATED)
def cuaca_manual(body: CuacaIn, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    cur.execute("INSERT INTO ops_cuaca (tanggal, sumber, hujan_mm, cuaca_teks, catatan, created_by) "
                "VALUES (%s,'manual',%s,%s,%s,%s) ON CONFLICT (tanggal, sumber) DO UPDATE SET hujan_mm=EXCLUDED.hujan_mm, "
                "cuaca_teks=EXCLUDED.cuaca_teks, catatan=EXCLUDED.catatan, created_by=EXCLUDED.created_by RETURNING id",
                (body.tanggal, body.hujan_mm, body.cuaca_teks, body.catatan, user.id))
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_cuaca_manual", "ops_cuaca", new_id, body.model_dump(mode="json"))
    conn.commit()
    return {"id": new_id, "ok": True}
