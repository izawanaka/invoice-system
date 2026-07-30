"""
users.py -- kelola akun pengguna (permintaan owner 28 Jul 2026: "bisa buatkan
akun admin untuk input data").

SEMUA endpoint di sini WAJIB owner (dependency security.require_owner). Staf
tidak boleh melihat daftar akun, apalagi membuat/mereset akun.

Keputusan owner yang dikodekan di sini:
  - Akun staf boleh melakukan APA SAJA di operasional (catat PO, unggah scan PO,
    unggah BAP, terbitkan invoice, unggah faktur pajak, cetak paket) KECUALI
    hal yang menyangkut PELUNASAN invoice -- lihat security.boleh_lihat_pelunasan()
    dan penerapannya di routers/invoices.py & routers/po.py.
  - Akun TIDAK PERNAH DIHAPUS, hanya dinonaktifkan. Alasannya bukan kenyamanan:
    app_audit_log punya FK ke app_users(id), jadi menghapus user akan memutus
    jejak "siapa mengubah apa" pada data finansial yang sudah terjadi.
  - Password dibuat SISTEM (acak kuat) dan ditampilkan SEKALI di respons untuk
    disalin owner. Yang disimpan cuma hash bcrypt -- password mentah tidak
    pernah ditulis ke DB, ke berkas, maupun ke log/audit.

Rencana lanjutan (belum dibangun): owner berencana menyambungkan login ke Google
Authenticator. Skema saat ini sengaja tidak menghalangi itu -- penambahan nanti
cukup 1 kolom rahasia TOTP di app_users + langkah verifikasi kedua di
routers/auth.py, tanpa mengubah endpoint di file ini.
"""
import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

import settings  # noqa: F401 -- import pertama, lihat settings.py
import schemas
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/users", tags=["users"])

# Alfabet password sengaja tanpa karakter yang gampang salah baca saat disalin
# manual / didikte lewat WhatsApp: 0/O, 1/l/I, dan simbol yang bermasalah di
# keyboard ponsel.
_ALFABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
_PANJANG_PASSWORD = 14

_KOLOM = "id, email, nama, role, aktif, created_at, last_login_at"


def _buat_password() -> str:
    return "".join(secrets.choice(_ALFABET) for _ in range(_PANJANG_PASSWORD))


def _baris_ke_out(r) -> schemas.UserOut:
    return schemas.UserOut(
        id=r[0], email=r[1], nama=r[2], role=r[3], aktif=r[4],
        created_at=r[5], last_login_at=r[6],
    )


def _ambil(conn, user_id: int):
    cur = conn.cursor()
    cur.execute(f"SELECT {_KOLOM} FROM app_users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Akun id {user_id} tidak ditemukan")
    return row


def _jumlah_owner_aktif(conn, kecuali_id: int = None) -> int:
    """Berapa owner aktif yang tersisa kalau akun `kecuali_id` tidak dihitung.

    Dipakai sebagai pengaman: sistem TIDAK BOLEH sampai kehilangan owner aktif
    terakhir, karena hanya owner yang bisa mengelola akun -- kalau itu terjadi,
    tidak ada jalan masuk lagi lewat aplikasi (harus dibetulkan manual lewat SQL
    di server).
    """
    cur = conn.cursor()
    if kecuali_id is None:
        cur.execute("SELECT count(*) FROM app_users WHERE role = 'owner' AND aktif = true")
    else:
        cur.execute(
            "SELECT count(*) FROM app_users WHERE role = 'owner' AND aktif = true AND id <> %s",
            (kecuali_id,),
        )
    return int(cur.fetchone()[0])


@router.get("", response_model=List[schemas.UserOut])
def list_users(
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    cur = conn.cursor()
    cur.execute(f"SELECT {_KOLOM} FROM app_users ORDER BY role, nama")
    return [_baris_ke_out(r) for r in cur.fetchall()]


@router.post("", response_model=schemas.UserCreateResult, status_code=status.HTTP_201_CREATED)
def create_user(
    body: schemas.UserCreateRequest,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    email = body.email.strip().lower()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_users WHERE lower(email) = %s", (email,))
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail=f"Email {email} sudah dipakai akun lain")

    password = _buat_password()
    cur.execute(
        "INSERT INTO app_users (email, password_hash, nama, role, aktif) "
        "VALUES (%s, %s, %s, %s, true) RETURNING " + _KOLOM,
        (email, security.hash_password(password), body.nama.strip(), body.role),
    )
    row = cur.fetchone()
    # Audit sengaja TIDAK memuat password -- hanya fakta bahwa akun dibuat.
    log_audit(conn, user.id, "create_user", "app_users", row[0],
              {"email": email, "role": body.role})
    conn.commit()
    return schemas.UserCreateResult(user=_baris_ke_out(row), password_sementara=password)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    body: schemas.UserUpdateRequest,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    row = _ambil(conn, user_id)
    role_lama, aktif_lama = row[3], row[4]

    role_baru = body.role if body.role is not None else role_lama
    aktif_baru = body.aktif if body.aktif is not None else aktif_lama

    # Pengaman 1: jangan sampai owner mengunci dirinya sendiri keluar.
    if user_id == user.id and (role_baru != "owner" or aktif_baru is False):
        raise HTTPException(
            status_code=400,
            detail="Anda tidak bisa menurunkan peran atau menonaktifkan akun Anda sendiri. "
                   "Minta owner lain yang melakukannya.",
        )
    # Pengaman 2: sistem harus selalu punya minimal 1 owner aktif.
    if role_lama == "owner" and aktif_lama and (role_baru != "owner" or not aktif_baru):
        if _jumlah_owner_aktif(conn, kecuali_id=user_id) == 0:
            raise HTTPException(
                status_code=400,
                detail="Ini satu-satunya Owner aktif. Angkat Owner lain dulu sebelum "
                       "menurunkan/menonaktifkan akun ini.",
            )

    nama_baru = body.nama.strip() if body.nama is not None else row[2]
    if not nama_baru:
        raise HTTPException(status_code=400, detail="Nama tidak boleh kosong")

    cur = conn.cursor()
    cur.execute(
        "UPDATE app_users SET nama = %s, role = %s, aktif = %s WHERE id = %s RETURNING " + _KOLOM,
        (nama_baru, role_baru, aktif_baru, user_id),
    )
    baru = cur.fetchone()
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")
    log_audit(conn, user.id, "update_user", "app_users", user_id,
              {"nama": nama_baru, "role": role_baru, "aktif": aktif_baru})
    conn.commit()
    return _baris_ke_out(baru)


@router.post("/{user_id}/reset-password", response_model=schemas.UserCreateResult)
def reset_password(
    user_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    """Terbitkan password baru untuk akun tsb. Password lama langsung tidak
    berlaku. Token JWT yang sudah terlanjur dipegang user itu TIDAK otomatis
    mati -- kalau tujuannya mencabut akses (bukan sekadar lupa password),
    nonaktifkan akunnya, karena get_current_user memeriksa kolom `aktif` di
    setiap request."""
    row = _ambil(conn, user_id)
    password = _buat_password()
    cur = conn.cursor()
    cur.execute(
        "UPDATE app_users SET password_hash = %s WHERE id = %s",
        (security.hash_password(password), user_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")
    log_audit(conn, user.id, "reset_password", "app_users", user_id, {"email": row[1]})
    conn.commit()
    return schemas.UserCreateResult(user=_baris_ke_out(row), password_sementara=password)
