"""
users.py -- kelola akun pengguna (permintaan owner 28 Jul 2026: "bisa buatkan
akun admin untuk input data").

SEMUA endpoint di sini WAJIB owner (dependency security.require_owner). Staf
tidak boleh melihat daftar akun, apalagi membuat/mereset akun.

Keputusan owner yang dikodekan di sini:
  - Akun staf boleh melakukan APA SAJA di operasional KECUALI hal yang menyangkut
    PELUNASAN invoice -- lihat security.boleh_lihat_pelunasan().
  - Akun TIDAK PERNAH DIHAPUS, hanya dinonaktifkan (app_audit_log punya FK ke
    app_users(id); menghapus user memutus jejak "siapa mengubah apa").
  - Yang disimpan cuma hash bcrypt -- password mentah tidak pernah ditulis ke DB,
    ke berkas, maupun ke log/audit.

Ditambah 5 Sep 2026 (keputusan owner, gaya Cantabile):
  - USERNAME: identitas yang diketik saat login. Diatur owner di /pengaturan.
    Unik (case-insensitive), 3-30 karakter huruf kecil/angka/titik/underscore.
    Email tetap identitas internal + identitas Google.
  - PASSWORD AWAL BOLEH DIINPUT OWNER (Buat Akun & Reset Password). Kosong ->
    sistem tetap membuat acak seperti sebelumnya. Minimal 8 karakter.
  - login_via_google = IZIN masuk lewat Google, bisa diubah owner.
  - RESET PASSWORD MENGOSONGKAN google_terbukti_pada: ini jalur pemulihan. Untuk
    staff/viewer yang sudah terbukti Google, password ditolak (routers/auth.py);
    reset oleh owner membuat password awal berlaku lagi sampai Google terbukti ulang.
"""
import re
import secrets
from typing import List, Optional

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

_KOLOM = ("id, email, nama, role, aktif, created_at, last_login_at, "
          "username, login_via_google, google_terbukti_pada")

_POLA_USERNAME = re.compile(r"^[a-z0-9._]{3,30}$")


def _buat_password() -> str:
    return "".join(secrets.choice(_ALFABET) for _ in range(_PANJANG_PASSWORD))


def _normalisasi_username(u: str) -> str:
    """Lowercase + trim; tolak kalau tidak sesuai pola (sama dengan CHECK di DB)."""
    u = (u or "").strip().lower()
    if not _POLA_USERNAME.match(u):
        raise HTTPException(
            status_code=400,
            detail="Username harus 3-30 karakter: huruf kecil, angka, titik, atau underscore.",
        )
    return u


def _cek_username_unik(conn, username: str, kecuali_id: Optional[int] = None):
    cur = conn.cursor()
    if kecuali_id is None:
        cur.execute("SELECT id FROM app_users WHERE lower(username) = %s", (username,))
    else:
        cur.execute("SELECT id FROM app_users WHERE lower(username) = %s AND id <> %s",
                    (username, kecuali_id))
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail=f"Username '{username}' sudah dipakai akun lain")


def _baris_ke_out(r) -> schemas.UserOut:
    return schemas.UserOut(
        id=r[0], email=r[1], nama=r[2], role=r[3], aktif=r[4],
        created_at=r[5], last_login_at=r[6],
        username=r[7], login_via_google=bool(r[8]), google_terbukti_pada=r[9],
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
    Pengaman: sistem TIDAK BOLEH kehilangan owner aktif terakhir."""
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
    username = _normalisasi_username(body.username)
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_users WHERE lower(email) = %s", (email,))
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail=f"Email {email} sudah dipakai akun lain")
    _cek_username_unik(conn, username)

    password = body.password if body.password else _buat_password()
    cur.execute(
        "INSERT INTO app_users (email, username, password_hash, nama, role, aktif, login_via_google) "
        "VALUES (%s, %s, %s, %s, %s, true, %s) RETURNING " + _KOLOM,
        (email, username, security.hash_password(password), body.nama.strip(), body.role,
         bool(body.login_via_google)),
    )
    row = cur.fetchone()
    # Audit sengaja TIDAK memuat password -- hanya fakta bahwa akun dibuat.
    log_audit(conn, user.id, "create_user", "app_users", row[0],
              {"email": email, "username": username, "role": body.role,
               "login_via_google": bool(body.login_via_google),
               "password_manual": bool(body.password)})
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

    username_baru = row[7]
    if body.username is not None:
        username_baru = _normalisasi_username(body.username)
        if username_baru != (row[7] or "").lower():
            _cek_username_unik(conn, username_baru, kecuali_id=user_id)

    lvg_baru = body.login_via_google if body.login_via_google is not None else bool(row[8])

    cur = conn.cursor()
    cur.execute(
        "UPDATE app_users SET nama = %s, role = %s, aktif = %s, username = %s, "
        "login_via_google = %s WHERE id = %s RETURNING " + _KOLOM,
        (nama_baru, role_baru, aktif_baru, username_baru, lvg_baru, user_id),
    )
    baru = cur.fetchone()
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")
    log_audit(conn, user.id, "update_user", "app_users", user_id,
              {"nama": nama_baru, "role": role_baru, "aktif": aktif_baru,
               "username": username_baru, "login_via_google": lvg_baru})
    conn.commit()
    return _baris_ke_out(baru)


@router.post("/{user_id}/reset-password", response_model=schemas.UserCreateResult)
def reset_password(
    user_id: int,
    body: Optional[schemas.ResetPasswordRequest] = None,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    """Terbitkan password baru untuk akun tsb (diinput owner, atau acak kalau
    kosong). Password lama langsung tidak berlaku.

    JALUR PEMULIHAN GATE GOOGLE (5 Sep 2026): google_terbukti_pada DIKOSONGKAN,
    sehingga staff/viewer yang sebelumnya hanya bisa masuk lewat Google boleh
    memakai password awal ini lagi -- sampai Google terbukti ulang.

    Token JWT yang sudah terlanjur dipegang user itu TIDAK otomatis mati --
    kalau tujuannya mencabut akses, nonaktifkan akunnya."""
    row = _ambil(conn, user_id)
    manual = bool(body and body.password)
    password = body.password if manual else _buat_password()
    cur = conn.cursor()
    cur.execute(
        "UPDATE app_users SET password_hash = %s, google_terbukti_pada = NULL "
        "WHERE id = %s RETURNING " + _KOLOM,
        (security.hash_password(password), user_id),
    )
    baru = cur.fetchone()
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")
    log_audit(conn, user.id, "reset_password", "app_users", user_id,
              {"email": row[1], "username": row[7], "password_manual": manual,
               "google_terbukti_dibuka": row[9] is not None})
    conn.commit()
    return schemas.UserCreateResult(user=_baris_ke_out(baru), password_sementara=password)
