"""
email_otp.py -- OTP login via email (Gmail SMTP). Implementasi sendiri (pola OTP
standar). Kredensial dibaca dari INVOICE_DATA/.email_creds (format KEY=VALUE),
TIDAK di-hardcode / tidak masuk git.
"""
import os
import ssl
import smtplib
import secrets
from email.mime.text import MIMEText

import config
import security

OTP_TTL_MENIT = 10
OTP_MAX_SALAH = 5


def _creds():
    path = config.d(".email_creds")
    d = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                        v = v[1:-1]
                    d[k.strip()] = v
    except FileNotFoundError:
        pass
    return d


def buat_kode():
    return "%06d" % secrets.randbelow(1000000)


def hash_kode(kode):
    return security.hash_password(kode)


def cek_kode(kode, kode_hash):
    return security.verify_password(kode, kode_hash)


def kirim_otp(email_tujuan, kode, nama=None):
    """Kirim OTP via Gmail SMTP SSL. Return True kalau terkirim, False kalau
    kredensial tidak lengkap / mode dummy (dev). Exception SMTP dilempar ke pemanggil."""
    c = _creds()
    user = c.get("GMAIL_USER")
    pw = c.get("GMAIL_APP_PASSWORD")
    frm = c.get("EMAIL_FROM") or user
    mode = (c.get("EMAIL_MODE") or "smtp").lower()
    if mode == "dummy" or not (user and pw):
        return False
    subject = "Kode OTP Login Invoice System"
    body = (
        "Halo %s,\n\n"
        "Kode OTP login Anda: %s\n"
        "Berlaku %d menit. Jangan bagikan kode ini ke siapa pun.\n\n"
        "-- Invoice System"
    ) % (nama or "", kode, OTP_TTL_MENIT)
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = email_tujuan
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(user, pw)
        s.sendmail(frm, [email_tujuan], msg.as_string())
    return True
