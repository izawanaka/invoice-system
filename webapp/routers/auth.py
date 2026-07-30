from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

import schemas
import security
import db_helper
import email_otp
from deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest):
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, nama, role, aktif FROM app_users WHERE email = %s",
            (body.email,),
        )
        row = cur.fetchone()
        if row is None or not row[5]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau password salah")
        user_id, email, password_hash, nama, role, aktif = row
        if not security.verify_password(body.password, password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau password salah")

        cur.execute(
            "UPDATE app_users SET last_login_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), user_id),
        )
        conn.commit()

        token = security.create_access_token(user_id, email, role)
        return schemas.LoginResponse(
            access_token=token,
            user=schemas.MeResponse(id=user_id, email=email, nama=nama, role=role),
        )
    finally:
        conn.close()


@router.get("/me", response_model=schemas.MeResponse)
def me(user: security.CurrentUser = Depends(security.get_current_user)):
    return schemas.MeResponse(id=user.id, email=user.email, nama=user.nama, role=user.role)


@router.post("/change-password")
def change_password(
    body: schemas.ChangePasswordRequest,
    user: security.CurrentUser = Depends(security.get_current_user),
    conn=Depends(get_db),
):
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM app_users WHERE id = %s", (user.id,))
    row = cur.fetchone()
    if row is None or not security.verify_password(body.password_lama, row[0]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password lama salah")
    new_hash = security.hash_password(body.password_baru)
    cur.execute("UPDATE app_users SET password_hash = %s WHERE id = %s", (new_hash, user.id))
    conn.commit()
    return {"ok": True}


# ---------- Login gaya Cantabile: email + PIN -> OTP email -> JWT ----------
# Catatan: login password lama (/auth/login) SENGAJA dipertahankan sbg fallback
# selama transisi (anti-lockout) sampai login Google (Phase B) terbukti jalan.

@router.post("/login/start")
def login_start(body: schemas.LoginPinStart):
    """Langkah 1: verifikasi email + PIN, lalu kirim OTP ke email user."""
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,email,nama,role,aktif,pin_hash,pin_ditutup,failed_pin,locked_until "
            "FROM app_users WHERE lower(email)=lower(%s)",
            (body.email,),
        )
        row = cur.fetchone()
        gagal = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau PIN salah")
        if row is None or not row[4]:
            raise gagal
        uid, email, nama, role, aktif, pin_hash, pin_ditutup, failed_pin, locked_until = row
        now = datetime.now(timezone.utc)
        if locked_until and locked_until > now:
            raise HTTPException(status_code=423, detail="Akun terkunci sementara (PIN salah berulang). Coba lagi nanti atau hubungi owner.")
        if pin_ditutup or not pin_hash:
            raise HTTPException(status_code=409, detail="PIN sudah ditutup. Silakan login lewat Google.")
        if not security.verify_password(body.pin, pin_hash):
            fp = (failed_pin or 0) + 1
            lock = now + timedelta(minutes=15) if fp >= 5 else None
            cur.execute("UPDATE app_users SET failed_pin=%s, locked_until=%s WHERE id=%s", (fp, lock, uid))
            conn.commit()
            raise gagal
        cur.execute("UPDATE app_users SET failed_pin=0, locked_until=NULL WHERE id=%s", (uid,))
        kode = email_otp.buat_kode()
        cur.execute(
            "INSERT INTO app_login_otp (user_id, kode_hash, kedaluwarsa_pada) VALUES (%s,%s,%s)",
            (uid, email_otp.hash_kode(kode), now + timedelta(minutes=email_otp.OTP_TTL_MENIT)),
        )
        conn.commit()
        terkirim = False
        try:
            terkirim = email_otp.kirim_otp(email, kode, nama)
        except Exception as e:
            print("  OTP kirim gagal:", e)
        return {
            "ok": True,
            "otp_terkirim": terkirim,
            "email": email,
            "ttl_menit": email_otp.OTP_TTL_MENIT,
            "pesan": ("Kode OTP dikirim ke email Anda." if terkirim
                      else "OTP dibuat, tapi pengiriman email gagal/nonaktif -- hubungi owner."),
        }
    finally:
        conn.close()


@router.post("/login/verify", response_model=schemas.LoginResponse)
def login_verify(body: schemas.LoginOtpVerify):
    """Langkah 2: verifikasi OTP terbaru -> terbitkan JWT."""
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id,email,nama,role,aktif FROM app_users WHERE lower(email)=lower(%s)", (body.email,))
        u = cur.fetchone()
        gagal = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kode OTP salah atau kedaluwarsa")
        if u is None or not u[4]:
            raise gagal
        uid, email, nama, role, aktif = u
        now = datetime.now(timezone.utc)
        cur.execute(
            "SELECT id,kode_hash,kedaluwarsa_pada,dipakai_pada,percobaan_salah "
            "FROM app_login_otp WHERE user_id=%s ORDER BY dibuat_pada DESC LIMIT 1",
            (uid,),
        )
        o = cur.fetchone()
        if o is None:
            raise gagal
        oid, kode_hash, exp, dipakai, salah = o
        if dipakai is not None or exp <= now or (salah or 0) >= email_otp.OTP_MAX_SALAH:
            raise gagal
        if not security.verify_password(body.kode, kode_hash):
            cur.execute("UPDATE app_login_otp SET percobaan_salah = percobaan_salah + 1 WHERE id=%s", (oid,))
            conn.commit()
            raise gagal
        cur.execute("UPDATE app_login_otp SET dipakai_pada=%s WHERE id=%s", (now, oid))
        cur.execute("UPDATE app_users SET last_login_at=%s WHERE id=%s", (now, uid))
        conn.commit()
        token = security.create_access_token(uid, email, role)
        return schemas.LoginResponse(
            access_token=token,
            user=schemas.MeResponse(id=uid, email=email, nama=nama, role=role),
        )
    finally:
        conn.close()
