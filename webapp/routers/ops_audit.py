"""
ops_audit.py -- workspace PABRIK tahap B7 (9 Sep 2026): stock opname, tutup hari, audit A1-A10.

Kontrak DESIGN-PABRIK.md:
  §1  stock opname = owner. Tutup hari = admin/kepala/owner (penanda kedisiplinan, tidak menahan apa pun).
  P1  opname & tutup hari append-only: /batal menandai + membalik ledger 'opname' bila ada.
  P2  nilai_sistem saat opname = SUM ledger (view), selisih = fisik - sistem; ledger 'opname'
      dibuat SATU transaksi bersama baris opname. Opname petak (K9) hanya mencatat, tanpa ledger.
  P7  temuan audit tidak pernah memuat nama PT/PO/badan usaha/harga/invoice (dijaga di audit_pabrik).
  §6  audit hanya MENGUSULKAN potongan; owner yang menerima lewat /audit/{id}/terima-potongan.
  K2  admin & kepala setara: keduanya boleh menulis penjelasan temuan; menutup = owner.
"""
import json
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

import settings  # noqa: F401
import security
import audit_pabrik
from audit import log_audit
from deps import get_db
from routers.ops_operasional import _kunci  # F1 (27 Sep 2026)

router = APIRouter(prefix="/ops", tags=["pabrik-audit"])


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


def _param(cur, kode, tgl=None):
    cur.execute("SELECT ops_param(%s, %s)", (kode, tgl or date.today()))
    r = cur.fetchone()
    return _num(r[0]) if r and r[0] is not None else None


class BatalIn(BaseModel):
    alasan: str = Field(min_length=3, max_length=300)


# ============================================================ STOCK OPNAME (owner)
class OpnameIn(BaseModel):
    tanggal: date
    jenis: str = Field(pattern="^(petak|sak_kosong|stok_jadi)$")
    objek_id: Optional[int] = None            # petak: lot_id aktif
    nilai_terukur: float = Field(ge=0)
    berita_acara_foto: Optional[str] = Field(default=None, max_length=300)
    disaksikan_oleh: Optional[str] = Field(default=None, max_length=120)
    catatan: Optional[str] = Field(default=None, max_length=300)


class OpnameOut(BaseModel):
    id: int
    tanggal: date
    jenis: str
    objek_id: Optional[int]
    objek: Optional[str]
    nilai_terukur: float
    nilai_sistem: float
    selisih: float
    ref_mutasi_id: Optional[int]
    berita_acara_foto: Optional[str]
    disaksikan_oleh: Optional[str]
    catatan: Optional[str]
    created_by: int
    dibatalkan: bool


def _opname_rows(cur, where="", params=()):
    cur.execute("SELECT o.id, o.tanggal, o.jenis, o.objek_id, l.nomor_lot, o.nilai_terukur, o.nilai_sistem, o.selisih, "
                "o.ref_mutasi_id, o.berita_acara_foto, o.disaksikan_oleh, o.catatan, o.created_by, o.dibatalkan_pada IS NOT NULL "
                "FROM ops_stock_opname o LEFT JOIN ops_lot l ON l.id=o.objek_id AND o.jenis='petak' " + where +
                " ORDER BY o.tanggal DESC, o.id DESC", params)
    return [OpnameOut(id=r[0], tanggal=r[1], jenis=r[2], objek_id=r[3], objek=r[4], nilai_terukur=_num(r[5]),
                      nilai_sistem=_num(r[6]), selisih=_num(r[7]), ref_mutasi_id=r[8], berita_acara_foto=r[9],
                      disaksikan_oleh=r[10], catatan=r[11], created_by=r[12], dibatalkan=r[13]) for r in cur.fetchall()]


@router.get("/opname", response_model=List[OpnameOut])
def list_opname(jenis: Optional[str] = None, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    if jenis:
        return _opname_rows(cur, "WHERE o.jenis=%s", (jenis,))[:200]
    return _opname_rows(cur)[:200]


@router.post("/opname", response_model=OpnameOut, status_code=status.HTTP_201_CREATED)
def opname_baru(body: OpnameIn, conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    """sak_kosong / stok_jadi: selisih != 0 -> baris ledger 'opname' (P2) dalam transaksi yang sama.
    petak: nilai_sistem = sisa WIP estimasi lot aktif; hanya dicatat (K9), tanpa ledger."""
    cur = conn.cursor()
    _kunci(cur, "sak", "stok")
    if body.tanggal > date.today():
        raise HTTPException(status_code=422, detail="Tanggal opname tidak boleh di masa depan")
    ref_mutasi = None
    if body.jenis == "petak":
        if body.objek_id is None:
            raise HTTPException(status_code=422, detail="Opname petak butuh objek_id = lot_id")
        cur.execute("SELECT status, kubik_masuk, sak_jadi, nomor_lot FROM v_ops_lot_ringkas WHERE lot_id=%s", (body.objek_id,))
        lot = cur.fetchone()
        if not lot:
            raise HTTPException(status_code=404, detail="Lot tidak ditemukan")
        if lot[0] == "habis":
            raise HTTPException(status_code=409, detail=f"Lot {lot[3]} sudah habis, tidak ada WIP untuk diopname")
        rend = _param(cur, "rendemen_sak_per_kubik", body.tanggal) or 2.5
        sistem = round(_num(lot[1]) - lot[2] / rend, 3)
    elif body.jenis == "sak_kosong":
        if body.nilai_terukur != int(body.nilai_terukur):
            raise HTTPException(status_code=422, detail="Sak dihitung bulat")
        cur.execute("SELECT saldo FROM v_ops_saldo_sak_kosong")
        sistem = int(cur.fetchone()[0])
    else:
        if body.nilai_terukur != int(body.nilai_terukur):
            raise HTTPException(status_code=422, detail="Sak dihitung bulat")
        cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
        sistem = int(cur.fetchone()[0])
    selisih = round(body.nilai_terukur - sistem, 3)
    cur.execute("INSERT INTO ops_stock_opname (tanggal, jenis, objek_id, nilai_terukur, nilai_sistem, selisih, berita_acara_foto, "
                "disaksikan_oleh, catatan, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.tanggal, body.jenis, body.objek_id if body.jenis == "petak" else None, body.nilai_terukur, sistem, selisih,
                 body.berita_acara_foto, body.disaksikan_oleh, body.catatan, user.id))
    oid = cur.fetchone()[0]
    if body.jenis != "petak" and selisih != 0:
        delta = int(selisih)
        ket = f"Stock opname #{oid}: fisik {int(body.nilai_terukur)} vs sistem {sistem}. {body.catatan or ''}".strip()
        if body.jenis == "sak_kosong":
            cur.execute("INSERT INTO ops_sak_kosong_mutasi (tanggal, jenis, delta, jumlah, keterangan, created_by) "
                        "VALUES (%s,'opname',%s,%s,%s,%s) RETURNING id", (body.tanggal, delta, abs(delta), ket, user.id))
        else:
            cur.execute("INSERT INTO ops_stok_jadi_mutasi (tanggal, jenis, delta, keterangan, created_by) "
                        "VALUES (%s,'opname',%s,%s,%s) RETURNING id", (body.tanggal, delta, ket, user.id))
        ref_mutasi = cur.fetchone()[0]
        cur.execute("UPDATE ops_stock_opname SET ref_mutasi_id=%s WHERE id=%s", (ref_mutasi, oid))
    log_audit(conn, user.id, "ops_opname", "ops_stock_opname", oid,
              {"jenis": body.jenis, "fisik": body.nilai_terukur, "sistem": sistem, "selisih": selisih, "ref_mutasi_id": ref_mutasi})
    conn.commit()
    return _opname_rows(cur, "WHERE o.id=%s", (oid,))[0]


@router.post("/opname/{row_id}/batal", response_model=OpnameOut)
def opname_batal(row_id: int, body: BatalIn, conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    """P1: tandai opname dibatalkan + batalkan baris ledger 'opname'-nya (saldo kembali ke sebelum opname)."""
    cur = conn.cursor()
    _kunci(cur, "sak", "stok")
    cur.execute("SELECT jenis, ref_mutasi_id, dibatalkan_pada FROM ops_stock_opname WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Opname tidak ditemukan")
    if r[2] is not None:
        raise HTTPException(status_code=409, detail="Sudah dibatalkan sebelumnya")
    cur.execute("SELECT 1 FROM ops_potongan WHERE ref_tabel='ops_stock_opname' AND ref_id=%s AND dibatalkan_pada IS NULL", (row_id,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Opname ini sudah jadi potongan bonus; batalkan potongannya dulu")
    cur.execute("UPDATE ops_stock_opname SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s WHERE id=%s",
                (user.id, body.alasan, row_id))
    if r[1]:
        tabel = "ops_sak_kosong_mutasi" if r[0] == "sak_kosong" else "ops_stok_jadi_mutasi"
        cur.execute(f"UPDATE {tabel} SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s WHERE id=%s AND dibatalkan_pada IS NULL",
                    (user.id, body.alasan, r[1]))
    log_audit(conn, user.id, "ops_opname_batal", "ops_stock_opname", row_id, {"alasan": body.alasan, "ref_mutasi_id": r[1]})
    conn.commit()
    return _opname_rows(cur, "WHERE o.id=%s", (row_id,))[0]


# ============================================================ TUTUP HARI
class TutupHariIn(BaseModel):
    tanggal: date
    catatan: Optional[str] = Field(default=None, max_length=300)


class TutupHariOut(BaseModel):
    id: int
    tanggal: date
    ringkasan: dict
    catatan: Optional[str]
    created_by: int
    created_at: str
    dibatalkan: bool


def _ringkasan_hari(cur, tgl):
    out = {}
    for kunci, tabel, kolom, aktif in (("truk_masuk", "ops_penerimaan", "tanggal", "dibatalkan_pada IS NULL"),
                                       ("produksi", "ops_produksi_sak", "tanggal", "dibatalkan_pada IS NULL"),
                                       ("mutasi_sak", "ops_sak_kosong_mutasi", "tanggal", "dibatalkan_pada IS NULL"),
                                       ("kas", "ops_kas_kecil", "tanggal", "dibatalkan_pada IS NULL"),
                                       ("upah", "ops_upah_harian", "tanggal", "dibatalkan_pada IS NULL"),
                                       ("pengiriman", "ops_pengiriman", "tanggal", "dibatalkan_pada IS NULL"),
                                       # ops_lot_tahap tidak punya kolom batal: ikut lot induknya
                                       ("tahap_lot", "ops_lot_tahap", "tanggal_mulai",
                                        "EXISTS (SELECT 1 FROM ops_lot l WHERE l.id=ops_lot_tahap.lot_id AND l.dibatalkan_pada IS NULL)")):
        cur.execute(f"SELECT count(*) FROM {tabel} WHERE {kolom}=%s AND {aktif}", (tgl,))
        out[kunci] = cur.fetchone()[0]
    cur.execute("SELECT coalesce(sum(kubik_masuk),0) FROM ops_penerimaan WHERE tanggal=%s AND dibatalkan_pada IS NULL", (tgl,))
    out["kubik_masuk"] = _num(cur.fetchone()[0])
    cur.execute("SELECT coalesce(sum(jumlah_sak),0) FROM ops_produksi_sak WHERE tanggal=%s AND dibatalkan_pada IS NULL", (tgl,))
    out["sak_diproduksi"] = int(cur.fetchone()[0])
    cur.execute("SELECT coalesce(sum(jumlah_sak),0) FROM ops_pengiriman WHERE tanggal=%s AND dibatalkan_pada IS NULL", (tgl,))
    out["sak_dikirim"] = int(cur.fetchone()[0])
    cur.execute("SELECT saldo FROM v_ops_saldo_sak_kosong")
    out["saldo_sak_kosong"] = cur.fetchone()[0]
    cur.execute("SELECT saldo FROM v_ops_saldo_stok_jadi")
    out["saldo_stok_jadi"] = cur.fetchone()[0]
    cur.execute("SELECT saldo FROM v_ops_saldo_kas")
    out["saldo_kas"] = _num(cur.fetchone()[0])
    cur.execute("SELECT cuaca_teks, hujan_mm FROM ops_cuaca WHERE tanggal=%s ORDER BY sumber='manual' DESC LIMIT 1", (tgl,))
    c = cur.fetchone()
    out["cuaca"] = {"teks": c[0], "hujan_mm": _num(c[1])} if c else None
    out["ada_input"] = any(out[k] > 0 for k in ("truk_masuk", "produksi", "mutasi_sak", "kas", "upah", "pengiriman", "tahap_lot"))
    return out


def _tutup_rows(cur, where="", params=()):
    cur.execute("SELECT id, tanggal, ringkasan, catatan, created_by, created_at, dibatalkan_pada IS NOT NULL FROM ops_tutup_hari " +
                where + " ORDER BY tanggal DESC, id DESC", params)
    return [TutupHariOut(id=r[0], tanggal=r[1], ringkasan=r[2] if isinstance(r[2], dict) else json.loads(r[2]), catatan=r[3],
                         created_by=r[4], created_at=r[5].isoformat(), dibatalkan=r[6]) for r in cur.fetchall()]


@router.get("/tutup-hari", response_model=List[TutupHariOut])
def list_tutup_hari(hari: int = Query(default=31, ge=1, le=366), conn=Depends(get_db),
                    user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    return _tutup_rows(conn.cursor(), "WHERE tanggal >= current_date - %s", (hari,))


@router.get("/tutup-hari/ringkasan")
def ringkasan_hari_ini(tanggal: Optional[date] = None, conn=Depends(get_db),
                       user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    """Pratinjau isi tutup hari (dipakai UI sebelum menekan 'Tutup Hari')."""
    tgl = tanggal or date.today()
    cur = conn.cursor()
    cur.execute("SELECT id FROM ops_tutup_hari WHERE tanggal=%s AND dibatalkan_pada IS NULL", (tgl,))
    r = cur.fetchone()
    return {"tanggal": tgl, "sudah_ditutup": bool(r), "tutup_hari_id": r[0] if r else None, "ringkasan": _ringkasan_hari(cur, tgl)}


@router.post("/tutup-hari", response_model=TutupHariOut, status_code=status.HTTP_201_CREATED)
def tutup_hari(body: TutupHariIn, conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """Penanda kedisiplinan (§6): satu per tanggal, tidak mengunci input apa pun; input susulan tetap boleh."""
    cur = conn.cursor()
    if body.tanggal > date.today():
        raise HTTPException(status_code=422, detail="Tidak bisa menutup hari yang belum terjadi")
    cur.execute("SELECT id FROM ops_tutup_hari WHERE tanggal=%s AND dibatalkan_pada IS NULL", (body.tanggal,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Hari {body.tanggal} sudah ditutup")
    ring = _ringkasan_hari(cur, body.tanggal)
    cur.execute("INSERT INTO ops_tutup_hari (tanggal, ringkasan, catatan, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
                (body.tanggal, json.dumps(ring), body.catatan, user.id))
    tid = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_tutup_hari", "ops_tutup_hari", tid, {"tanggal": body.tanggal.isoformat(), "ada_input": ring["ada_input"]})
    conn.commit()
    return _tutup_rows(cur, "WHERE id=%s", (tid,))[0]


@router.post("/tutup-hari/{row_id}/batal", response_model=TutupHariOut)
def tutup_hari_batal(row_id: int, body: BatalIn, conn=Depends(get_db),
                     user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    cur.execute("SELECT dibatalkan_pada FROM ops_tutup_hari WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    if r[0] is not None:
        raise HTTPException(status_code=409, detail="Sudah dibatalkan sebelumnya")
    cur.execute("UPDATE ops_tutup_hari SET dibatalkan_oleh=%s, dibatalkan_pada=now(), alasan_batal=%s WHERE id=%s",
                (user.id, body.alasan, row_id))
    log_audit(conn, user.id, "ops_tutup_hari_batal", "ops_tutup_hari", row_id, {"alasan": body.alasan})
    conn.commit()
    return _tutup_rows(cur, "WHERE id=%s", (row_id,))[0]


# ============================================================ AUDIT A1-A10
class TemuanOut(BaseModel):
    id: int
    kode: str
    nama_cek: str
    tingkat: str
    ref_tabel: Optional[str]
    ref_id: Optional[int]
    pesan: str
    detail: Optional[dict]
    usulan_potongan_sak: Optional[int]
    status: str
    tanggal_audit: date
    terakhir_dilihat: date
    penjelasan: Optional[str]
    penjelasan_oleh: Optional[int]
    ditutup_oleh: Optional[int]
    ditutup_pada: Optional[str]
    catatan_tutup: Optional[str]


def _temuan_rows(cur, where="", params=()):
    cur.execute("SELECT id, kode, tingkat, ref_tabel, ref_id, pesan, detail, usulan_potongan_sak, status, tanggal_audit, "
                "terakhir_dilihat, penjelasan, penjelasan_oleh, ditutup_oleh, ditutup_pada, catatan_tutup FROM ops_audit_temuan " +
                where + " ORDER BY status='terbuka' DESC, id DESC LIMIT 300", params)
    out = []
    for r in cur.fetchall():
        det = r[6] if isinstance(r[6], dict) or r[6] is None else json.loads(r[6])
        out.append(TemuanOut(id=r[0], kode=r[1], nama_cek=audit_pabrik.NAMA_CEK.get(r[1], r[1]), tingkat=r[2], ref_tabel=r[3],
                             ref_id=r[4], pesan=r[5], detail=det, usulan_potongan_sak=r[7], status=r[8], tanggal_audit=r[9],
                             terakhir_dilihat=r[10], penjelasan=r[11], penjelasan_oleh=r[12], ditutup_oleh=r[13],
                             ditutup_pada=r[14].isoformat() if r[14] else None, catatan_tutup=r[15]))
    return out


@router.get("/audit", response_model=List[TemuanOut])
def list_temuan(status_: str = Query(default="terbuka", alias="status", pattern="^(terbuka|ditutup|selesai_otomatis|semua)$"),
                kode: Optional[str] = None, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    syarat, params = [], []
    if status_ != "semua":
        syarat.append("status=%s")
        params.append(status_)
    if kode:
        syarat.append("kode=%s")
        params.append(kode.upper())
    return _temuan_rows(cur, ("WHERE " + " AND ".join(syarat)) if syarat else "", tuple(params))


@router.get("/audit/daftar-cek")
def daftar_cek(user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    return [{"kode": k, "nama": v} for k, v in audit_pabrik.NAMA_CEK.items()]


@router.post("/audit/jalankan")
def audit_jalankan(kirim: bool = False, tanggal: Optional[date] = None, conn=Depends(get_db),
                   user: security.CurrentUser = Depends(security.require_owner)):
    """Jalankan A1-A10 sekarang (owner). kirim=true juga mengirim laporan ke Telegram owner."""
    return audit_pabrik.jalankan(conn, tanggal, kirim=kirim, dipicu_oleh=user.id)


class PenjelasanIn(BaseModel):
    penjelasan: str = Field(min_length=5, max_length=1000)


@router.post("/audit/{row_id}/penjelasan", response_model=TemuanOut)
def temuan_penjelasan(row_id: int, body: PenjelasanIn, conn=Depends(get_db),
                      user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    """A1 dkk: penjelasan tertulis dari lapangan (admin/kepala setara, K2). Tidak menutup temuan."""
    cur = conn.cursor()
    cur.execute("SELECT status, penjelasan FROM ops_audit_temuan WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Temuan tidak ditemukan")
    if r[0] != "terbuka":
        raise HTTPException(status_code=409, detail=f"Temuan sudah {r[0]}")
    cur.execute("UPDATE ops_audit_temuan SET penjelasan=%s, penjelasan_oleh=%s, penjelasan_pada=now() WHERE id=%s",
                (body.penjelasan, user.id, row_id))
    log_audit(conn, user.id, "ops_audit_penjelasan", "ops_audit_temuan", row_id,
              {"penjelasan": body.penjelasan, "sebelumnya": r[1]})
    conn.commit()
    return _temuan_rows(cur, "WHERE id=%s", (row_id,))[0]


class TutupIn(BaseModel):
    catatan: str = Field(min_length=3, max_length=500)


@router.post("/audit/{row_id}/tutup", response_model=TemuanOut)
def temuan_tutup(row_id: int, body: TutupIn, conn=Depends(get_db), user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT status FROM ops_audit_temuan WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Temuan tidak ditemukan")
    if r[0] != "terbuka":
        raise HTTPException(status_code=409, detail=f"Temuan sudah {r[0]}")
    cur.execute("UPDATE ops_audit_temuan SET status='ditutup', ditutup_oleh=%s, ditutup_pada=now(), catatan_tutup=%s WHERE id=%s",
                (user.id, body.catatan, row_id))
    log_audit(conn, user.id, "ops_audit_tutup", "ops_audit_temuan", row_id, {"catatan": body.catatan})
    conn.commit()
    return _temuan_rows(cur, "WHERE id=%s", (row_id,))[0]


class TerimaPotonganIn(BaseModel):
    sak: Optional[int] = Field(default=None, gt=0)   # default = usulan audit
    keterangan: Optional[str] = Field(default=None, max_length=300)


@router.post("/audit/{row_id}/terima-potongan", status_code=status.HTTP_201_CREATED)
def temuan_terima_potongan(row_id: int, body: TerimaPotonganIn, conn=Depends(get_db),
                           user: security.CurrentUser = Depends(security.require_owner)):
    """A3/A4: owner menerima usulan -> baris ops_potongan (sebab opname_sak / susut) merujuk opname, temuan ditutup.
    Ditolak bila rekap bulan itu sudah dibekukan (P8)."""
    cur = conn.cursor()
    cur.execute("SELECT kode, status, ref_tabel, ref_id, usulan_potongan_sak, detail FROM ops_audit_temuan WHERE id=%s FOR UPDATE", (row_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Temuan tidak ditemukan")
    kode, st, ref_tabel, ref_id, usulan, det = r
    if kode not in ("A3", "A4") or ref_tabel != "ops_stock_opname":
        raise HTTPException(status_code=422, detail="Hanya temuan A3/A4 (opname) yang punya usulan potongan")
    if st != "terbuka":
        raise HTTPException(status_code=409, detail=f"Temuan sudah {st}")
    det = det if isinstance(det, dict) else json.loads(det or "{}")
    bulan = det.get("bulan_potongan")
    cur.execute("SELECT 1 FROM ops_rekap_bonus_bulanan WHERE bulan=%s AND status='dibekukan'", (bulan,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Rekap {bulan} sudah dibekukan (P8); potongan masuk lewat bulan berjalan secara manual")
    sak = body.sak or usulan
    sebab = "opname_sak" if kode == "A3" else "susut"
    ket = body.keterangan or f"Diterima dari audit {kode}#{row_id}: selisih opname #{ref_id}"
    cur.execute("INSERT INTO ops_potongan (bulan, sebab, sak, ref_tabel, ref_id, keterangan, created_by) VALUES (%s,%s,%s,'ops_stock_opname',%s,%s,%s) RETURNING id",
                (bulan, sebab, sak, ref_id, ket, user.id))
    pid = cur.fetchone()[0]
    cur.execute("UPDATE ops_audit_temuan SET status='ditutup', ditutup_oleh=%s, ditutup_pada=now(), catatan_tutup=%s WHERE id=%s",
                (user.id, f"Potongan {sak} sak diterima (ops_potongan #{pid})", row_id))
    log_audit(conn, user.id, "ops_audit_terima_potongan", "ops_potongan", pid, {"temuan_id": row_id, "bulan": bulan, "sebab": sebab, "sak": sak})
    conn.commit()
    return {"potongan_id": pid, "bulan": bulan, "sebab": sebab, "sak": sak, "temuan_id": row_id}
