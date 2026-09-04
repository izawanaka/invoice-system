"""google_login.py -- Login lewat akun Google (OAuth 2.0 Authorization Code flow).
Dibangun 4 Sep 2026 dengan MENIRU cantabile-app/app/google_login.py (20 Jul 2026).

Desain (sama dengan Cantabile):
- Identitas ditentukan SEMATA oleh email yang dikonfirmasi Google (klaim `email`
  + `email_verified=true` di ID token), dicocokkan ke app_users.email
  (keputusan owner 4 Sep 2026: pakai kolom email, bukan google_sub).
  Tidak cocok dengan akun mana pun -> DITOLAK. Tidak ada auto-create.
- `state` acak disimpan di cookie bertanda tangan berumur 10 menit (anti-CSRF),
  dicocokkan lagi di /auth/google/callback.
- ID token diverifikasi PENUH di server: tanda tangan RS256 lewat JWKS resmi
  Google, klaim aud (= client_id), iss, exp. Tidak pernah dipercaya mentah.

Yang BERBEDA dari Cantabile (sengaja):
- Tanpa dependensi baru: verifikasi pakai PyJWT (sudah ada) + JWKS Google,
  tanda tangan cookie pakai PyJWT HS256 dgn jwt_secret (bukan itsdangerous),
  tukar kode pakai httpx (bukan requests). Jadi TIDAK perlu rebuild image API.
- Kredensial dibaca dari .google_oauth.json (format Google Cloud Console, di
  root repo, izin 600, di-gitignore) -- bukan dari variabel settings.
- app_users.login_via_google = IZIN masuk lewat Google. TIDAK menutup jalur
  password/PIN (Vault #14: jalur lama tetap terbuka sampai Google terbukti).
  Gate penutup ala Cantabile bisa ditambah nanti setelah terbukti.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

GSTATE_COOKIE = "cocopeat_gstate"
GSTATE_MAX_AGE = 600  # 10 menit -- cukup untuk satu kali proses login di Google

OAUTH_PATH = os.path.join(settings.CODE_DIR, ".google_oauth.json")

_cfg: Optional[dict] = None
_jwks: Optional[jwt.PyJWKClient] = None


def tersedia() -> bool:
    return os.path.isfile(OAUTH_PATH)


def _config() -> dict:
    global _cfg
    if _cfg is None:
        with open(OAUTH_PATH, "r", encoding="utf-8") as f:
            web = json.load(f)["web"]
        _cfg = {
            "client_id": web["client_id"],
            "client_secret": web["client_secret"],
            "redirect_uri": web["redirect_uris"][0],
        }
    return _cfg


def build_authorize_url(state: str, login_hint: Optional[str] = None) -> str:
    c = _config()
    params = {
        "client_id": c["client_id"],
        "redirect_uri": c["redirect_uri"],
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def make_gstate_cookie_value(state: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"st": state, "iat": now, "exp": now + GSTATE_MAX_AGE},
        settings.get_jwt_secret(),
        algorithm="HS256",
    )


def read_gstate_cookie(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        data = jwt.decode(token, settings.get_jwt_secret(), algorithms=["HS256"])
        return data.get("st")
    except jwt.PyJWTError:
        return None


@dataclass
class GoogleResult:
    ok: bool
    error: Optional[str] = None
    email: Optional[str] = None


def _jwks_client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
    return _jwks


def tukar_kode_dan_verifikasi(code: str) -> GoogleResult:
    """Tukar authorization code -> id_token, lalu verifikasi id_token PENUH di server."""
    c = _config()
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": c["client_id"],
                "client_secret": c["client_secret"],
                "redirect_uri": c["redirect_uri"],
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        return GoogleResult(ok=False, error="Tidak bisa menghubungi Google. Coba lagi.")

    if resp.status_code != 200:
        return GoogleResult(ok=False, error="Login Google gagal atau dibatalkan.")

    raw_id_token = resp.json().get("id_token")
    if not raw_id_token:
        return GoogleResult(ok=False, error="Login Google gagal (token tidak lengkap).")

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(raw_id_token)
        claims = jwt.decode(
            raw_id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=c["client_id"],
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:
        return GoogleResult(ok=False, error="Login Google gagal (token tidak valid).")

    if claims.get("iss") not in GOOGLE_ISSUERS:
        return GoogleResult(ok=False, error="Login Google gagal (penerbit token tidak dikenal).")
    if not claims.get("email_verified"):
        return GoogleResult(ok=False, error="Email Google belum terverifikasi.")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        return GoogleResult(ok=False, error="Login Google gagal (email tidak ada).")

    return GoogleResult(ok=True, email=email)
