"""
security.py -- hashing password, JWT, dan dependency FastAPI untuk auth/role.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
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
    def __init__(self, user_id: int, email: str, role: str, nama: str):
        self.id = user_id
        self.email = email
        self.role = role
        self.nama = nama

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


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
            "SELECT id, email, role, nama, aktif FROM app_users WHERE id = %s",
            (int(user_id),),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None or not row[4]:
        raise _unauthorized("User tidak ditemukan atau sudah dinonaktifkan")

    return CurrentUser(user_id=row[0], email=row[1], role=row[2], nama=row[3])


def boleh_lihat_pelunasan(user: CurrentUser) -> bool:
    """Keputusan owner 28 Jul 2026: akun staf boleh melakukan apa saja di
    operasional KECUALI melihat pelunasan invoice (status bayar, tanggal bayar,
    umur outstanding). Jadi bukan sekadar disembunyikan di tampilan -- data itu
    tidak dikirim sama sekali oleh API untuk staf, supaya tidak bisa dilihat
    lewat DevTools/panggilan API langsung.
    """
    return user.is_owner


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
