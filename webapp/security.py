"""
security.py -- hashing password, JWT, dan dependency FastAPI untuk auth/role.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWTError as JWTError  # alias: jalur except JWTError di bawah tetap sama
from passlib.context import CryptContext

import settings
import db_helper

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(user_id: int, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.get_jwt_secret(), algorithm=settings.JWT_ALGORITHM)


class CurrentUser:
    def __init__(self, user_id: int, email: str, role: str, nama: str,
                 username: Optional[str] = None):
        self.id = user_id
        self.email = email
        self.role = role
        self.nama = nama
        self.username = username  # identitas yang diketik saat login (5 Sep 2026)

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_viewer(self) -> bool:
        """Peran 'viewer' (keputusan owner 4 Sep 2026): PENGAMAT MURNI.
        Boleh MEMBACA semua -- termasuk pelunasan, yang justru ditutup dari staf --
        tapi TIDAK boleh menulis apa pun dan TIDAK boleh mengunduh berkas.
        """
        return self.role == "viewer"


def _unauthorized(detail: str = "Token tidak valid atau kedaluwarsa"):
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise _unauthorized("Token tidak ditemukan")
    try:
        payload = jwt.decode(
            creds.credentials, settings.get_jwt_secret(), algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise _unauthorized()

    user_id = payload.get("sub")
    if user_id is None:
        raise _unauthorized()

    # Verifikasi user masih ada & aktif di DB tiap request -- kalau di-nonaktifkan
    # owner, token lama TIDAK BOLEH tetap bisa dipakai sampai kedaluwarsa sendiri.
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, role, nama, aktif, username FROM app_users WHERE id = %s",
            (int(user_id),),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None or not row[4]:
        raise _unauthorized("User tidak ditemukan atau sudah dinonaktifkan")

    return CurrentUser(user_id=row[0], email=row[1], role=row[2], nama=row[3], username=row[5])


def boleh_lihat_pelunasan(user: CurrentUser) -> bool:
    """Keputusan owner 28 Jul 2026: akun staf boleh melakukan apa saja di
    operasional KECUALI melihat pelunasan invoice (status bayar, tanggal bayar,
    umur outstanding). Jadi bukan sekadar disembunyikan di tampilan -- data itu
    tidak dikirim sama sekali oleh API untuk staf, supaya tidak bisa dilihat
    lewat DevTools/panggilan API langsung.
    """
    return user.is_owner or user.is_viewer


def role_dari_request(request):
    '''Baca peran user dari header Authorization TANPA melempar exception.
    Dipakai middleware penjaga tulis di main.py.

    Sengaja membaca DB, BUKAN klaim role di dalam token: kalau owner menurunkan
    seseorang jadi viewer, token lama TIDAK boleh tetap bisa menulis sampai
    kedaluwarsa sendiri. Pola yang sama dengan pemeriksaan kolom aktif di
    get_current_user().

    Balik None kalau token tidak ada/tidak sah -- penolakan auth tetap urusan
    get_current_user, middleware ini hanya soal peran.
    '''
    auth = request.headers.get('authorization') or ''
    if not auth.lower().startswith('bearer '):
        return None
    try:
        payload = jwt.decode(
            auth[7:].strip(), settings.get_jwt_secret(), algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get('sub')
        if user_id is None:
            return None
        conn = db_helper.get_conn()
        try:
            cur = conn.cursor()
            cur.execute('SELECT role FROM app_users WHERE id = %s AND aktif', (int(user_id),))
            row = cur.fetchone()
        finally:
            conn.close()
        return row[0] if row else None
    except Exception:
        return None


def require_lihat_pelunasan(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    '''MEMBACA data pelunasan: owner + viewer (keputusan owner 4 Sep 2026).

    Staf TETAP ditolak -- pelonggaran ini khusus peran pengamat, bukan pencabutan
    Aturan #11 utk staf. MENGUBAH pelunasan (catat/hapus cicilan, tandai lunas)
    tetap memakai require_owner: viewer boleh melihat, tidak boleh menyentuh.
    '''
    if not boleh_lihat_pelunasan(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Hanya Owner & Pengamat yang boleh melihat data pelunasan',
        )
    return user


def require_owner(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dipakai utk endpoint yang HARUS owner. Pemakai saat ini: routers/users.py
    (seluruh pengelolaan akun) dan pelunasan invoice (PATCH
    /invoices/{no}/payment). Modul HPP cocopeat di Fase 2 tinggal memasang
    dependency yang sama."""
    if not user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya Owner yang boleh mengakses ini",
        )
    return user

# ---------------------------------------------------------------- PABRIK_B1_9SEP2026
# Workspace PABRIK (DESIGN-PABRIK.md K1-K3). admin & kepala SETARA penuh (K2);
# keduanya hanya boleh menyentuh /ops/* -- penjaga globalnya di main.py.
PERAN_PABRIK = ("admin", "kepala")
PERAN_PABRIK_TULIS = ("owner", "admin", "kepala")
PERAN_PABRIK_BACA = ("owner", "admin", "kepala", "viewer")


def is_pabrik(user: CurrentUser) -> bool:
    return user.role in PERAN_PABRIK


def require_pabrik_tulis(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Endpoint TULIS workspace Pabrik: owner, admin, kepala (K2: setara, tanpa flag)."""
    if user.role not in PERAN_PABRIK_TULIS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya Owner, Admin, dan Kepala pabrik yang boleh mengubah data Pabrik",
        )
    return user


def require_pabrik_baca(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Endpoint BACA workspace Pabrik: owner, admin, kepala, viewer. Staf invoice tidak."""
    if user.role not in PERAN_PABRIK_BACA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Peran ini tidak punya akses ke workspace Pabrik",
        )
    return user
