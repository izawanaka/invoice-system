#!/usr/bin/env python3
"""
seed_owner.py -- buat/reset SATU akun app_users (dipakai sekali di awal utk
membuat akun Owner pertama, atau menambah akun Admin/Staf). BUKAN endpoint HTTP
(sengaja) -- supaya tidak ada jalur pendaftaran akun terbuka dari internet.

Jalankan di server (venv webapp aktif, env sandbox sudah di-source):
    python3 seed_owner.py --email owner@delianterra.com --nama "Denny" --role owner
    python3 seed_owner.py --email staf@delianterra.com --nama "Staf 1" --role staff

Password digenerate acak & HANYA ditampilkan sekali di stdout -- tidak disimpan
di mana pun selain hash bcrypt-nya di app_users.password_hash.
"""
import argparse
import secrets
import string
import sys

import security  # otomatis menambah folder induk ke sys.path (lihat settings.py)
import db_helper


def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--nama", required=True)
    ap.add_argument("--role", choices=["owner", "staff"], default="staff")
    ap.add_argument("--password", default=None, help="Kalau tidak diisi, digenerate acak")
    args = ap.parse_args()

    password = args.password or generate_password()
    password_hash = security.hash_password(password)

    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM app_users WHERE email = %s", (args.email,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE app_users SET password_hash = %s, nama = %s, role = %s, aktif = true WHERE email = %s",
                (password_hash, args.nama, args.role, args.email),
            )
            print(f"User {args.email} SUDAH ADA -- password & data di-reset.", file=sys.stderr)
        else:
            cur.execute(
                "INSERT INTO app_users (email, password_hash, nama, role, aktif) "
                "VALUES (%s, %s, %s, %s, true)",
                (args.email, password_hash, args.nama, args.role),
            )
            print(f"User {args.email} dibuat.", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print("=" * 55)
    print(f"  Email    : {args.email}")
    print(f"  Password : {password}")
    print("  (simpan sekarang -- tidak akan ditampilkan lagi)")
    print("=" * 55)


if __name__ == "__main__":
    main()
