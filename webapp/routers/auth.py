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

# ---------------------------------------------------------------------------
# MODEL LOGIN = SALINAN CANTABILE (keputusan owner 5 Sep 2026:
# "susun persis seperti cantabile ... copy paste sistemnya, jangan berubah")
#
# Alur: user mengetik USERNAME saja, lalu klik "Masuk dengan Google".
#   - Username TIDAK diverifikasi sebagai kredensial di jalur Google; ia hanya
#     dipakai untuk `login_hint` (saran akun di halaman Google), persis Cantabile.
#   - Identitas SEMATA dari email yang dikonfirmasi Google, dicocokkan ke
#     app_users.email. Password tidak pernah singgah di cocopeat.
#
# PASSWORD AWAL = TIKET SEKALI PAKAI (keputusan owner 5 Sep 2026):
#   "pass awal itu hanya sebagai tanda mereka bisa masuk, dan begitu bisa masuk,
#    sudah otomatis mati (flag off)".
#
#   app_users.password_aktif = true  -> tiket masih berlaku, boleh masuk SEKALI
#                                       dengan password awal dari owner.
#   Setelah login password BERHASIL   -> password_aktif otomatis di-set false.
#   Setelah login Google BERHASIL     -> password_aktif juga di-set false
#                                       (tiket tidak diperlukan lagi).
#   password_aktif = false            -> non-owner WAJIB lewat Google.
#
#   OWNER DIKECUALIKAN (keputusan owner 4 & 5 Sep 2026): owner selalu boleh
#   memakai password, karena dialah satu-satunya yang bisa memulihkan akun
#   orang lain. Kalau owner ikut terkunci, tidak ada siapa pun di atasnya.
#
# PEMULIHAN kalau Google bermasalah untuk seseorang: owner menekan Reset
#   Password di /pengaturan -> terbit tiket baru (password_aktif=true). Izin
#   Google TIDAK diutak-atik oleh reset.
# ---------------------------------------------------------------------------

_PESAN_SALAH = "Username atau password salah"
_PESAN_GOOGLE_ONLY = ("Akun ini masuk lewat Google. Ketik username Anda lalu tekan "
                      "\"Masuk dengan Google\". Kalau bermasalah, minta Owner "
                      "menerbitkan kata sandi awal baru.")


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest):
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, nama, role, aktif, username, password_aktif "
            "FROM app_users WHERE lower(username) = lower(%s)",
            (body.username.strip(),),
        )
        row = cur.fetchone()
        if row is None or not row[5]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_PESAN_SALAH)
        user_id, email, password_hash, nama, role, _aktif, username, password_aktif = row
        # Tiket sudah terpakai/tidak pernah diterbitkan -> non-owner wajib Google.
        # Dicek SEBELUM memverifikasi password, supaya jalur ini tidak bisa
        # dipakai menebak-nebak password akun yang sudah pindah ke Google.
        if role != "owner" and not password_aktif:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_PESAN_GOOGLE_ONLY)
        if not security.verify_password(body.password, password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_PESAN_SALAH)

        # TIKET LANGSUNG HANGUS setelah berhasil dipakai (non-owner).
        cur.execute(
            "UPDATE app_users SET last_login_at = %s, "
            "password_aktif = CASE WHEN role = 'owner' THEN password_aktif ELSE false END "
            "WHERE id = %s",
            (datetime.now(timezone.utc), user_id),
        )
        conn.commit()
        if role != "owner":
            print(f"[TIKET SANDI TERPAKAI] {username} ({email}) -- selanjutnya wajib Google",
                  flush=True)

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
# Tidak pernah hidup: 0 pin_hash, app_login_otp kosong, GMAIL_APP_PASSWORD kosong.
# Endpoint dipertahankan sebagai 410 supaya klien lama dapat pesan jelas.

_PESAN_OTP_MATI = "Login PIN/OTP sudah dimatikan (5 Sep 2026). Ketik username lalu masuk lewat Google."


@router.post("/login/start", status_code=status.HTTP_410_GONE)
def login_start_dimatikan():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PESAN_OTP_MATI)


@router.post("/login/verify", status_code=status.HTTP_410_GONE)
def login_verify_dimatikan():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PESAN_OTP_MATI)


# ---------- Login Google -- salinan Cantabile ----------

@router.get("/google/mulai")
def google_mulai(username: str = ""):
    """username hanya untuk login_hint (saran akun di halaman Google), persis
    Cantabile. Username yang tidak dikenal TIDAK ditolak di sini -- membalas
    'user tidak ada' pada langkah ini akan membocorkan daftar akun. Kalau email
    Google-nya nanti tidak cocok, penolakan terjadi di callback."""
    if not google_login.tersedia():
        raise HTTPException(status_code=503, detail="Login Google belum dikonfigurasi di server.")
    hint = None
    u = (username or "").strip()
    if u:
        conn = db_helper.get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT email FROM app_users WHERE lower(username)=lower(%s) AND aktif", (u,))
            r = cur.fetchone()
            if r:
                hint = r[0]
        finally:
            conn.close()
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(google_login.build_authorize_url(state, login_hint=hint), status_code=303)
    resp.set_cookie(
        google_login.GSTATE_COOKIE, google_login.make_gstate_cookie_value(state),
        max_age=google_login.GSTATE_MAX_AGE, httponly=True, samesite="lax", secure=True, path="/",
    )
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    def _gagal(pesan: str, sebab: str):
        # Sebab dicatat ke log server untuk diagnosis. TIDAK memuat code/token.
        print(f"[GOOGLE-LOGIN GAGAL] {sebab}", flush=True)
        r = RedirectResponse(f"/login?google_error={quote(pesan)}", status_code=303)
        r.delete_cookie(google_login.GSTATE_COOKIE, path="/")
        return r

    if error:
        return _gagal("Login Google dibatalkan.", f"Google mengembalikan error={error}")
    ck = request.cookies.get(google_login.GSTATE_COOKIE)
    saved_state = google_login.read_gstate_cookie(ck)
    if not saved_state or saved_state != state or not code:
        return _gagal(
            "Login Google gagal (sesi kedaluwarsa). Coba lagi.",
            f"state mismatch: cookie_ada={bool(ck)} cookie_terbaca={bool(saved_state)} "
            f"cocok={saved_state == state if saved_state else False} code_ada={bool(code)}",
        )

    hasil = google_login.tukar_kode_dan_verifikasi(code)
    if not hasil.ok:
        return _gagal(hasil.error or "Login Google gagal.", f"tukar_kode gagal: {hasil.error}")

    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, nama, role, aktif, login_via_google FROM app_users WHERE lower(email)=lower(%s)",
            (hasil.email,),
        )
        row = cur.fetchone()
        if row is None:
            return _gagal("Email Google ini tidak terdaftar untuk akun mana pun di cocopeat.",
                          f"email dari Google tidak ada di app_users: {hasil.email}")
        if not row[4]:
            return _gagal("Akun ini sudah dinonaktifkan.", f"akun nonaktif: {hasil.email}")
        if not row[5]:
            return _gagal("Akun ini belum diizinkan masuk lewat Google. Hubungi owner.",
                          f"login_via_google=false: {hasil.email}")
        uid, email, nama, role, _aktif, _lvg = row
        now = datetime.now(timezone.utc)
        # google_terbukti_pada = catatan bahwa Google BENAR-BENAR pernah berhasil
        # untuk akun ini (dipakai owner di /pengaturan sbg tanda "sudah teruji").
        # Tiket sandi ikut hangus: kalau Google sudah jalan, tiket tidak perlu lagi.
        # pin_ditutup diteruskan seperti sebelumnya; owner tidak pernah ditutup.
        cur.execute(
            "UPDATE app_users SET last_login_at=%s, "
            "google_terbukti_pada = COALESCE(google_terbukti_pada, %s), "
            "password_aktif = CASE WHEN role = 'owner' THEN password_aktif ELSE false END, "
            "pin_ditutup = CASE WHEN role = 'owner' THEN pin_ditutup ELSE true END "
            "WHERE id=%s",
            (now, now, uid),
        )
        conn.commit()
        print(f"[GOOGLE-LOGIN SUKSES] {email} role={role}", flush=True)
    finally:
        conn.close()

    token = security.create_access_token(uid, email, role)
    # Token lewat FRAGMENT (#) -- tidak pernah dikirim ke server, jadi tidak
    # masuk log akses/proxy (koreksi terhadap Cantabile).
    r = RedirectResponse(f"/login#gtoken={token}", status_code=303)
    r.delete_cookie(google_login.GSTATE_COOKIE, path="/")
    return r
