"""
settings.py -- konfigurasi web app (terpisah dari config.py milik skrip invoice lama,
supaya kita TIDAK PERNAH mengubah config.py yang sudah dipakai Telegram bot / skrip
invoice produksi. File ini HANYA dipakai oleh webapp/, tidak disentuh kode lama).
"""
import os
import sys

# Folder kode invoice lama (invoice-sandbox atau invoice-system) ada SATU TINGKAT
# di atas folder webapp/ ini. Kita tambahkan ke sys.path supaya bisa `import config`,
# `import db_helper`, dll -- persis pola yang sudah dipakai invoice_dkp.py/_kks.py
# ("_sys_path_fix" di file itu).
WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(WEBAPP_DIR)
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

# --- JWT ---
# Secret dibaca dari file terpisah (TIDAK masuk git, sejalan dengan Invariant I6 di
# DESIGN.md -- kredensial tidak pernah di-hardcode / commit).
JWT_SECRET_FILE = os.path.join(WEBAPP_DIR, ".jwt_secret")


def get_jwt_secret() -> str:
    try:
        with open(JWT_SECRET_FILE) as f:
            s = f.read().strip()
            if s:
                return s
    except FileNotFoundError:
        pass
    raise RuntimeError(
        f"JWT secret belum ada di {JWT_SECRET_FILE}. Buat dulu, mis.: "
        f"python3 -c \"import secrets; print(secrets.token_urlsafe(48))\" > {JWT_SECRET_FILE} "
        f"&& chmod 600 {JWT_SECRET_FILE}"
    )


JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("WEBAPP_JWT_EXPIRE_MINUTES", "480"))  # 8 jam

# --- CORS ---
# Origin frontend yang diizinkan. Selama Fase 1 masih dev, tambahkan localhost;
# nanti setelah frontend live tambahkan https://invoice.delianterra.com secara resmi.
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "WEBAPP_CORS_ORIGINS",
        "https://invoice.delianterra.com,http://localhost:3000",
    ).split(",")
    if o.strip()
]

# --- n8n Paperless bridge ---
PAPERLESS_BRIDGE_URL = os.environ.get(
    "WEBAPP_PAPERLESS_BRIDGE_URL",
    "https://n8n.delianterra.com/webhook/invoice-paperless",
)
PAPERLESS_POLL_ATTEMPTS = int(os.environ.get("WEBAPP_PAPERLESS_POLL_ATTEMPTS", "6"))
PAPERLESS_POLL_DELAY_SEC = float(os.environ.get("WEBAPP_PAPERLESS_POLL_DELAY_SEC", "1.5"))

# --- Badan usaha yang boleh generate invoice lewat web (Fase 1) ---
# SSM/TBS/GBU BELUM punya skrip generator PDF (bank/direktur/layout khusus per
# entitas belum dibuat) -- lihat 05_web_platform_plan.md. Dashboard baca tetap
# generik utk semua 5 badan usaha; generate invoice DIBATASI ke yang di bawah ini
# sampai skrip untuk entitas lain dibuat (owner sudah konfirmasi batasan ini).
GENERATE_INVOICE_SUPPORTED = {"DKP", "KKS"}

# --- Ranah sistem (keputusan owner, 28 Jul 2026 malam) ---
# Sistem invoice web ini KHUSUS transaksi cocopeat = PT DKP & CV KKS.
# CV TBS / CV SSMJ (SSM) / CV GBU TIDAK ada hubungan dengan sistem ini sama
# sekali -- entitas itu tetap ada di tabel badan_usaha karena DB dipakai
# bersama sistem lain (Email Hub/Paperless), tapi web app ini menolak/
# menyembunyikan semuanya di luar daftar ini.
DASHBOARD_BADAN_USAHA = {"DKP", "KKS"}

# Default ambang warning PO (persen tersisa) -- bisa di-override per PO lewat
# kolom purchase_orders.warning_threshold_pct.
DEFAULT_PO_WARNING_THRESHOLD_PCT = float(
    os.environ.get("WEBAPP_PO_WARNING_THRESHOLD_PCT", "15")
)
