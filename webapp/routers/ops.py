"""
ops.py -- workspace PABRIK (hulu: pabrik cocopeat). Tahap B1, 9 Sep 2026.

Kontrak: Business/Cocopeat/DESIGN-PABRIK.md (K1..K10, P1..P10).
  - Semua tabel berprefiks ops_; tabel invoice TIDAK disentuh (K1).
  - Peran admin & kepala SETARA penuh untuk input, tanpa flag/alasan (K2).
  - Admin & kepala tidak pernah menerima data penjualan (K3) -- di B1 belum ada
    endpoint yang menyentuh bap/invoice; penjaga global ada di main.py.
  - Parameter yang memengaruhi uang effective-dated (P9); koreksi = baris baru
    + baris lama dibatalkan/ditutup, bukan UPDATE nilai (P1).
  - created_by/created_at + app_audit_log untuk setiap tulis (P10).

B1 hanya berisi: ping, parameter, tarif bonus, pengali klaim, pemasok, petak,
karyawan. Modul operasional (terima truk, lot, produksi, sak, kas) menyusul di
B2-B4 di file router terpisah (ops_*.py) supaya file ini tidak membengkak.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import settings  # noqa: F401 -- import pertama, lihat settings.py
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/ops", tags=["pabrik"])

# Kode parameter yang dikenal sistem. Menambah kode baru = ubah daftar ini
# (sengaja bukan bebas, supaya salah ketik tidak diam-diam membuat parameter baru).
KODE_PARAMETER = (
    "kg_per_sak", "sak_per_m3_kks", "rendemen_sak_per_kubik", "rendemen_min",
    "rendemen_max", "bonus_cap_bulan", "berat_sak_min_kg", "kadar_air_max_pct",
    "ec_max", "toleransi_susut_pct", "batas_hari_karung", "upah_buruh",
    "upah_langsir", "upah_supir",
)

_KOLOM_STD = "created_by, created_at, dibatalkan_oleh, dibatalkan_pada, alasan_batal"


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


# ============================================================ skema respons/req
class PingOut(BaseModel):
    workspace: str = "PABRIK"
    role: str
    nama: str


class ParameterOut(BaseModel):
    id: int
    kode: str
    nilai: Optional[float]
    berlaku_mulai: date
    berlaku_sampai: Optional[date]
    catatan: Optional[str]
    created_by: int
    dibatalkan_pada: Optional[str] = None


class ParameterCreate(BaseModel):
    kode: str
    nilai: Optional[float] = Field(default=None, ge=0)
    berlaku_mulai: date
    catatan: Optional[str] = Field(default=None, max_length=300)


class TarifBonusOut(BaseModel):
    id: int
    jenjang: int
    sak_dari: int
    sak_sampai: Optional[int]
    tarif_per_sak: float
    berlaku_mulai: date
    berlaku_sampai: Optional[date]


class PengaliOut(BaseModel):
    id: int
    batas_pct: float
    inklusif: bool
    pengali: float
    berlaku_mulai: date
    berlaku_sampai: Optional[date]


class PemasokOut(BaseModel):
    id: int
    nama: str
    jenis: str
    kontak: Optional[str]
    aktif: bool


class PemasokCreate(BaseModel):
    nama: str = Field(min_length=2, max_length=120)
    jenis: str = Field(pattern="^(sabut|sak|lainnya)$")
    kontak: Optional[str] = Field(default=None, max_length=120)


class PemasokUpdate(BaseModel):
    nama: Optional[str] = Field(default=None, min_length=2, max_length=120)
    kontak: Optional[str] = Field(default=None, max_length=120)
    aktif: Optional[bool] = None


class PetakOut(BaseModel):
    id: int
    nomor: str
    panjang_m: Optional[float]
    lebar_m: Optional[float]
    tinggi_maks_m: Optional[float]
    aktif: bool


class PetakCreate(BaseModel):
    nomor: str = Field(min_length=1, max_length=20)
    panjang_m: Optional[float] = Field(default=None, gt=0)
    lebar_m: Optional[float] = Field(default=None, gt=0)
    tinggi_maks_m: Optional[float] = Field(default=None, gt=0)


class PetakUpdate(BaseModel):
    panjang_m: Optional[float] = Field(default=None, gt=0)
    lebar_m: Optional[float] = Field(default=None, gt=0)
    tinggi_maks_m: Optional[float] = Field(default=None, gt=0)
    aktif: Optional[bool] = None


class KaryawanOut(BaseModel):
    id: int
    nama: str
    peran: str
    gaji_pokok: float
    uang_makan: float
    user_id: Optional[int]
    berlaku_mulai: date
    berlaku_sampai: Optional[date]
    catatan: Optional[str]


class KaryawanCreate(BaseModel):
    nama: str = Field(min_length=2, max_length=120)
    peran: str = Field(pattern="^(kepala|buruh|langsir|supir)$")
    gaji_pokok: float = Field(default=0, ge=0)
    uang_makan: float = Field(default=0, ge=0)
    user_id: Optional[int] = None
    berlaku_mulai: date
    catatan: Optional[str] = Field(default=None, max_length=300)


# ============================================================ ping
@router.get("/ping", response_model=PingOut)
def ping(user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    """Cek cepat: peran ini boleh masuk workspace Pabrik."""
    return PingOut(role=user.role, nama=user.nama)


# ============================================================ parameter (P9)
@router.get("/parameter", response_model=List[ParameterOut])
def parameter_efektif(
    tanggal: Optional[date] = None,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_pabrik_baca),
):
    """Satu baris per kode: yang berlaku pada `tanggal` (default hari ini).
    nilai None = belum diputuskan owner -- UI wajib menampilkannya sebagai 'belum diisi'."""
    tgl = tanggal or date.today()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT ON (kode) id, kode, nilai, berlaku_mulai, berlaku_sampai, catatan, created_by "
        "FROM ops_parameter WHERE dibatalkan_pada IS NULL AND berlaku_mulai <= %s "
        "AND (berlaku_sampai IS NULL OR berlaku_sampai >= %s) "
        "ORDER BY kode, berlaku_mulai DESC, id DESC",
        (tgl, tgl),
    )
    return [ParameterOut(id=r[0], kode=r[1], nilai=_num(r[2]), berlaku_mulai=r[3],
                         berlaku_sampai=r[4], catatan=r[5], created_by=r[6]) for r in cur.fetchall()]


@router.get("/parameter/riwayat", response_model=List[ParameterOut])
def parameter_riwayat(
    kode: Optional[str] = None,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    cur = conn.cursor()
    if kode:
        cur.execute("SELECT id, kode, nilai, berlaku_mulai, berlaku_sampai, catatan, created_by, dibatalkan_pada "
                    "FROM ops_parameter WHERE kode = %s ORDER BY berlaku_mulai DESC, id DESC", (kode,))
    else:
        cur.execute("SELECT id, kode, nilai, berlaku_mulai, berlaku_sampai, catatan, created_by, dibatalkan_pada "
                    "FROM ops_parameter ORDER BY kode, berlaku_mulai DESC, id DESC")
    return [ParameterOut(id=r[0], kode=r[1], nilai=_num(r[2]), berlaku_mulai=r[3], berlaku_sampai=r[4],
                         catatan=r[5], created_by=r[6], dibatalkan_pada=str(r[7]) if r[7] else None)
            for r in cur.fetchall()]


@router.post("/parameter", response_model=ParameterOut, status_code=status.HTTP_201_CREATED)
def parameter_baru(
    body: ParameterCreate,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    """Owner menetapkan nilai baru mulai tanggal tertentu (effective-dated, P9).

    Baris terbuka sebelumnya (berlaku_sampai NULL) DITUTUP pada berlaku_mulai-1;
    kalau tanggal mulainya sama persis, baris lama dibatalkan (P1: jejak tetap ada).
    Tidak boleh mundur ke tanggal sebelum baris terbuka terakhir -- riwayat tidak
    boleh ditulis ulang.
    """
    if body.kode not in KODE_PARAMETER:
        raise HTTPException(status_code=422, detail=f"Kode parameter tidak dikenal: {body.kode}")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, berlaku_mulai FROM ops_parameter WHERE kode = %s AND dibatalkan_pada IS NULL "
        "AND berlaku_sampai IS NULL ORDER BY berlaku_mulai DESC, id DESC LIMIT 1 FOR UPDATE",
        (body.kode,),
    )
    terbuka = cur.fetchone()
    if terbuka:
        lama_id, lama_mulai = terbuka
        if body.berlaku_mulai < lama_mulai:
            raise HTTPException(
                status_code=409,
                detail=f"Tanggal mulai {body.berlaku_mulai} mendahului baris aktif ({lama_mulai}); riwayat tidak boleh ditulis ulang",
            )
        if body.berlaku_mulai == lama_mulai:
            cur.execute(
                "UPDATE ops_parameter SET dibatalkan_oleh=%s, dibatalkan_pada=now(), "
                "alasan_batal='Diganti nilai baru dgn tanggal mulai sama' WHERE id=%s",
                (user.id, lama_id),
            )
        else:
            cur.execute("UPDATE ops_parameter SET berlaku_sampai=%s WHERE id=%s",
                        (body.berlaku_mulai - timedelta(days=1), lama_id))
    cur.execute(
        "INSERT INTO ops_parameter (kode, nilai, berlaku_mulai, catatan, created_by) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (body.kode, body.nilai, body.berlaku_mulai, body.catatan, user.id),
    )
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_parameter_baru", "ops_parameter", new_id,
              {"kode": body.kode, "nilai": body.nilai, "berlaku_mulai": str(body.berlaku_mulai),
               "menutup_id": terbuka[0] if terbuka else None})
    conn.commit()
    return ParameterOut(id=new_id, kode=body.kode, nilai=body.nilai, berlaku_mulai=body.berlaku_mulai,
                        berlaku_sampai=None, catatan=body.catatan, created_by=user.id)


# ============================================================ tarif & pengali (baca)
@router.get("/tarif-bonus", response_model=List[TarifBonusOut])
def tarif_bonus(conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT id, jenjang, sak_dari, sak_sampai, tarif_per_sak, berlaku_mulai, berlaku_sampai "
                "FROM ops_tarif_bonus WHERE dibatalkan_pada IS NULL ORDER BY berlaku_mulai DESC, jenjang")
    return [TarifBonusOut(id=r[0], jenjang=r[1], sak_dari=r[2], sak_sampai=r[3], tarif_per_sak=_num(r[4]),
                          berlaku_mulai=r[5], berlaku_sampai=r[6]) for r in cur.fetchall()]


@router.get("/pengali-klaim", response_model=List[PengaliOut])
def pengali_klaim(conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT id, batas_pct, inklusif, pengali, berlaku_mulai, berlaku_sampai "
                "FROM ops_pengali_klaim WHERE dibatalkan_pada IS NULL ORDER BY berlaku_mulai DESC, batas_pct")
    return [PengaliOut(id=r[0], batas_pct=_num(r[1]), inklusif=r[2], pengali=_num(r[3]),
                       berlaku_mulai=r[4], berlaku_sampai=r[5]) for r in cur.fetchall()]


# ============================================================ pemasok (master)
@router.get("/pemasok", response_model=List[PemasokOut])
def list_pemasok(hanya_aktif: bool = False, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT id, nama, jenis, kontak, aktif FROM ops_pemasok "
                + ("WHERE aktif " if hanya_aktif else "") + "ORDER BY jenis, lower(nama)")
    return [PemasokOut(id=r[0], nama=r[1], jenis=r[2], kontak=r[3], aktif=r[4]) for r in cur.fetchall()]


@router.post("/pemasok", response_model=PemasokOut, status_code=status.HTTP_201_CREATED)
def pemasok_baru(body: PemasokCreate, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM ops_pemasok WHERE lower(nama)=lower(%s) AND jenis=%s", (nama, body.jenis))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Pemasok dengan nama & jenis itu sudah ada")
    cur.execute("INSERT INTO ops_pemasok (nama, jenis, kontak, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
                (nama, body.jenis, body.kontak, user.id))
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_pemasok_baru", "ops_pemasok", new_id, {"nama": nama, "jenis": body.jenis})
    conn.commit()
    return PemasokOut(id=new_id, nama=nama, jenis=body.jenis, kontak=body.kontak, aktif=True)


@router.patch("/pemasok/{pemasok_id}", response_model=PemasokOut)
def pemasok_ubah(pemasok_id: int, body: PemasokUpdate, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.require_pabrik_tulis)):
    cur = conn.cursor()
    cur.execute("SELECT id, nama, jenis, kontak, aktif FROM ops_pemasok WHERE id=%s FOR UPDATE", (pemasok_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Pemasok tidak ditemukan")
    nama = body.nama.strip() if body.nama is not None else r[1]
    kontak = body.kontak if body.kontak is not None else r[3]
    aktif = body.aktif if body.aktif is not None else r[4]
    cur.execute("UPDATE ops_pemasok SET nama=%s, kontak=%s, aktif=%s WHERE id=%s", (nama, kontak, aktif, pemasok_id))
    log_audit(conn, user.id, "ops_pemasok_ubah", "ops_pemasok", pemasok_id,
              {"sebelum": {"nama": r[1], "kontak": r[3], "aktif": r[4]},
               "sesudah": {"nama": nama, "kontak": kontak, "aktif": aktif}})
    conn.commit()
    return PemasokOut(id=pemasok_id, nama=nama, jenis=r[2], kontak=kontak, aktif=aktif)


# ============================================================ petak (master, owner)
@router.get("/petak", response_model=List[PetakOut])
def list_petak(conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_pabrik_baca)):
    cur = conn.cursor()
    cur.execute("SELECT id, nomor, panjang_m, lebar_m, tinggi_maks_m, aktif FROM ops_petak ORDER BY nomor")
    return [PetakOut(id=r[0], nomor=r[1], panjang_m=_num(r[2]), lebar_m=_num(r[3]),
                     tinggi_maks_m=_num(r[4]), aktif=r[5]) for r in cur.fetchall()]


@router.post("/petak", response_model=PetakOut, status_code=status.HTTP_201_CREATED)
def petak_baru(body: PetakCreate, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_owner)):
    nomor = body.nomor.strip().upper()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM ops_petak WHERE nomor=%s", (nomor,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="Nomor petak sudah ada")
    cur.execute("INSERT INTO ops_petak (nomor, panjang_m, lebar_m, tinggi_maks_m, created_by) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (nomor, body.panjang_m, body.lebar_m, body.tinggi_maks_m, user.id))
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_petak_baru", "ops_petak", new_id, body.model_dump())
    conn.commit()
    return PetakOut(id=new_id, nomor=nomor, panjang_m=body.panjang_m, lebar_m=body.lebar_m,
                    tinggi_maks_m=body.tinggi_maks_m, aktif=True)


@router.patch("/petak/{petak_id}", response_model=PetakOut)
def petak_ubah(petak_id: int, body: PetakUpdate, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT id, nomor, panjang_m, lebar_m, tinggi_maks_m, aktif FROM ops_petak WHERE id=%s FOR UPDATE",
                (petak_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Petak tidak ditemukan")
    p = body.panjang_m if body.panjang_m is not None else _num(r[2])
    l_ = body.lebar_m if body.lebar_m is not None else _num(r[3])
    t = body.tinggi_maks_m if body.tinggi_maks_m is not None else _num(r[4])
    aktif = body.aktif if body.aktif is not None else r[5]
    cur.execute("UPDATE ops_petak SET panjang_m=%s, lebar_m=%s, tinggi_maks_m=%s, aktif=%s WHERE id=%s",
                (p, l_, t, aktif, petak_id))
    log_audit(conn, user.id, "ops_petak_ubah", "ops_petak", petak_id, body.model_dump(exclude_none=True))
    conn.commit()
    return PetakOut(id=petak_id, nomor=r[1], panjang_m=p, lebar_m=l_, tinggi_maks_m=t, aktif=aktif)


# ============================================================ karyawan (owner)
@router.get("/karyawan", response_model=List[KaryawanOut])
def list_karyawan(conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_owner)):
    cur = conn.cursor()
    cur.execute("SELECT id, nama, peran, gaji_pokok, uang_makan, user_id, berlaku_mulai, berlaku_sampai, catatan "
                "FROM ops_karyawan WHERE dibatalkan_pada IS NULL ORDER BY peran, nama, berlaku_mulai DESC")
    return [KaryawanOut(id=r[0], nama=r[1], peran=r[2], gaji_pokok=_num(r[3]), uang_makan=_num(r[4]),
                        user_id=r[5], berlaku_mulai=r[6], berlaku_sampai=r[7], catatan=r[8])
            for r in cur.fetchall()]


@router.post("/karyawan", response_model=KaryawanOut, status_code=status.HTTP_201_CREATED)
def karyawan_baru(body: KaryawanCreate, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.require_owner)):
    """Baris karyawan effective-dated. Perubahan gaji = baris baru dgn berlaku_mulai
    baru; baris lama untuk nama+peran yang sama ditutup di berlaku_mulai-1."""
    cur = conn.cursor()
    if body.user_id is not None:
        cur.execute("SELECT role FROM app_users WHERE id=%s AND aktif", (body.user_id,))
        u = cur.fetchone()
        if not u:
            raise HTTPException(status_code=422, detail="user_id tidak ada / tidak aktif")
        if body.peran == "kepala" and u[0] != "kepala":
            raise HTTPException(status_code=422, detail="Akun untuk kepala harus berperan 'kepala'")
    cur.execute(
        "SELECT id, berlaku_mulai FROM ops_karyawan WHERE lower(nama)=lower(%s) AND peran=%s "
        "AND dibatalkan_pada IS NULL AND berlaku_sampai IS NULL ORDER BY berlaku_mulai DESC LIMIT 1 FOR UPDATE",
        (body.nama.strip(), body.peran),
    )
    lama = cur.fetchone()
    if lama:
        if body.berlaku_mulai <= lama[1]:
            raise HTTPException(status_code=409, detail=f"Tanggal mulai harus setelah baris aktif ({lama[1]})")
        cur.execute("UPDATE ops_karyawan SET berlaku_sampai=%s WHERE id=%s",
                    (body.berlaku_mulai - timedelta(days=1), lama[0]))
    cur.execute(
        "INSERT INTO ops_karyawan (nama, peran, gaji_pokok, uang_makan, user_id, berlaku_mulai, catatan, created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (body.nama.strip(), body.peran, body.gaji_pokok, body.uang_makan, body.user_id,
         body.berlaku_mulai, body.catatan, user.id),
    )
    new_id = cur.fetchone()[0]
    log_audit(conn, user.id, "ops_karyawan_baru", "ops_karyawan", new_id,
              {"nama": body.nama, "peran": body.peran, "berlaku_mulai": str(body.berlaku_mulai),
               "menutup_id": lama[0] if lama else None})
    conn.commit()
    return KaryawanOut(id=new_id, nama=body.nama.strip(), peran=body.peran, gaji_pokok=body.gaji_pokok,
                       uang_makan=body.uang_makan, user_id=body.user_id, berlaku_mulai=body.berlaku_mulai,
                       berlaku_sampai=None, catatan=body.catatan)
