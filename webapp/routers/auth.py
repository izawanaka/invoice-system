from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

import schemas
import security
import db_helper
from deps import get_db

import secrets
from urllib.parse import quote
from fastapi import Request
from fastapi.responses import RedirectResponse
import google_login

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------- Login pakai USERNAME + password (keputusan owner 5 Sep 2026) ----------
# "input-nya cuma username, tetapi di belakangnya tetap menggunakan email" (gaya
# Cantabile). Username adalah yang DIKETIK; email tetap identitas internal (JWT,
# audit) sekaligus identitas Google. Email TIDAK diterima di kolom login.
#
# GATE GOOGLE (keputusan owner 5 Sep 2026, "otomatis setelah Google terbukti 1x"):
#   staff & viewer -> begitu app_users.google_terbukti_pada terisi (login Google
#   pertama SUKSES), jalur password DITOLAK; mereka hanya bisa masuk lewat Google.
#   owner -> TIDAK PERNAH kena gate ini (anti-lockout: owner adalah satu-satunya
#   yang bisa memulihkan akun orang lain, jadi ia harus selalu punya >1 pintu).
# JALAN PULANG: owner mereset password di /pengaturan -> google_terbukti_pada
#   dikosongkan lagi -> password awal berlaku sampai Google terbukti ulang.

_PESAN_SALAH = "Username atau password salah"


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest):
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, nama, role, aktif, username, google_terbukti_pada "
            "FROM app_users WHERE lower(username) = lower(%s)",
            (body.username.strip(),),
        )
        row = cur.fetchone()
        if row is None or not row[5]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_PESAN_SALAH)
        user_id, email, password_hash, nama, role, _aktif, username, google_terbukti = row
        if not security.verify_password(body.password, password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_PESAN_SALAH)
        if role != "owner" and google_terbukti is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akun ini sudah masuk lewat Google, password tidak berlaku lagi. "
                       "Gunakan tombol \"Masuk dengan Google\".",
            )

        cur.execute(
            "UPDATE app_users SET last_login_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), user_id),
        )
        conn.commit()

        token = security.create_access_token(user_id, email, role)
        return schemas.LoginResponse(
            access_token=token,
            user=schemas.MeResponse(id=user_id, email=email, nama=nama, role=role, username=username),
        )
    finally:
        conn.close()


@router.get("/me", response_model=schemas.MeResponse)
def me(user: security.CurrentUser = Depends(security.get_current_user)):
    return schemas.MeResponse(id=user.id, email=user.email, nama=user.nama, role=user.role,
                              username=user.username)


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


# ---------- Jalur Email + PIN + OTP (Fase A) DIMATIKAN 5 Sep 2026 ----------
# Keputusan owner: "dimatikan saja kirim OTP". Faktanya jalur ini tidak pernah
# hidup: tidak ada akun yang punya pin_hash, app_login_otp kosong, dan
# GMAIL_APP_PASSWORD tidak pernah terpasang. Endpoint dibiarkan ada (410 Gone)
# supaya klien lama mendapat pesan yang jelas, bukan 404 yang membingungkan.
# Tabel app_login_otp & kolom pin_* di app_users DIBIARKAN (historis, tidak dipakai).

_PESAN_OTP_MATI = "Login PIN/OTP sudah dimatikan (5 Sep 2026). Masuk dengan username + password, atau lewat Google."


@router.post("/login/start", status_code=status.HTTP_410_GONE)
def login_start_dimatikan():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PESAN_OTP_MATI)


@router.post("/login/verify", status_code=status.HTTP_410_GONE)
def login_verify_dimatikan():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PESAN_OTP_MATI)


# ---------- Login Google (Fase B) -- meniru cantabile-app, 4 Sep 2026 ----------
# app_users.login_via_google = IZIN masuk lewat Google (dinyalakan owner di /pengaturan).
# app_users.google_terbukti_pada = BUKTI Google pernah sukses (diisi di callback).

@router.get("/google/mulai")
def google_mulai():
    if not google_login.tersedia():
        raise HTTPException(status_code=503, detail="Login Google belum dikonfigurasi di server.")
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(google_login.build_authorize_url(state), status_code=303)
    resp.set_cookie(
        google_login.GSTATE_COOKIE, google_login.make_gstate_cookie_value(state),
        max_age=google_login.GSTATE_MAX_AGE, httponly=True, samesite="lax", secure=True, path="/",
    )
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    def _gagal(pesan: str):
        r = RedirectResponse(f"/login?google_error={quote(pesan)}", status_code=303)
        r.delete_cookie(google_login.GSTATE_COOKIE, path="/")
        return r

    if error:
        return _gagal("Login Google dibatalkan.")
    saved_state = google_login.read_gstate_cookie(request.cookies.get(google_login.GSTATE_COOKIE))
    if not saved_state or saved_state != state or not code:
        return _gagal("Login Google gagal (sesi kedaluwarsa). Coba lagi.")

    hasil = google_login.tukar_kode_dan_verifikasi(code)
    if not hasil.ok:
        return _gagal(hasil.error or "Login Google gagal.")

    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, nama, role, aktif, login_via_google FROM app_users WHERE lower(email)=lower(%s)",
            (hasil.email,),
        )
        row = cur.fetchone()
        if row is None or not row[4] or not row[5]:
            return _gagal("Email Google ini tidak terdaftar untuk akun mana pun di cocopeat.")
        uid, email, nama, role, _aktif, _lvg = row
        now = datetime.now(timezone.utc)
        # Google TERBUKTI untuk akun ini -> catat (sekali; nilai pertama dipertahankan).
        # Untuk staff & viewer, sejak titik ini jalur password DITOLAK di /auth/login.
        # PIN (warisan Fase A) ikut ditutup untuk non-owner seperti sebelumnya (§40-B);
        # owner tidak pernah dimatikan pintunya oleh sistem.
        cur.execute(
            "UPDATE app_users SET last_login_at=%s, "
            "google_terbukti_pada = COALESCE(google_terbukti_pada, %s), "
            "pin_ditutup = CASE WHEN role = 'owner' THEN pin_ditutup ELSE true END "
            "WHERE id=%s",
            (now, now, uid),
        )
        conn.commit()
    finally:
        conn.close()

    token = security.create_access_token(uid, email, role)
    # Token dikirim lewat FRAGMENT (#), bukan query string: fragment tidak pernah
    # dikirim ke server -> tidak masuk log akses/proxy (pelajaran dari log Cantabile).
    r = RedirectResponse(f"/login#gtoken={token}", status_code=303)
    r.delete_cookie(google_login.GSTATE_COOKIE, path="/")
    return r
