"""patch_b1.py -- patch anchor-assert (gaya Sawit): setiap anchor harus muncul TEPAT 1x,
kalau tidak, berhenti tanpa menulis apa pun. Idempoten: kalau sudah dipatch, keluar 0."""
import sys

ROOT = "/home/izawa/invoice-system/webapp/"
TANDA = "PABRIK_B1_9SEP2026"


def patch(path, edits):
    p = ROOT + path
    s = open(p, encoding="utf-8").read()
    if TANDA in s:
        print(f"skip {path}: sudah dipatch")
        return
    for anchor, new, count in edits:
        n = s.count(anchor)
        assert n == count, f"{path}: anchor ditemukan {n}x, harap {count}x -> {anchor[:60]!r}"
        s = s.replace(anchor, new)
    open(p, "w", encoding="utf-8").write(s)
    print(f"ok   {path}")


# ---------------- security.py: peran & dependency Pabrik (K2, K3)
security_tail = '''
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
'''
_sp = ROOT + "security.py"
_ss = open(_sp, encoding="utf-8").read()
if TANDA in _ss:
    print("skip security.py: sudah dipatch")
else:
    assert _ss.count("def require_owner(") == 1 and "def require_pabrik_tulis" not in _ss
    assert _ss.rstrip().endswith("return user"), "security.py tidak berakhir di require_owner seperti dugaan"
    open(_sp, "w", encoding="utf-8").write(_ss.rstrip("\n") + "\n" + security_tail)
    print("ok   security.py (append)")

# ---------------- main.py: penjaga global admin/kepala + daftarkan router ops
patch("main.py", [
    ("JALUR_BEBAS_VIEWER = ('/auth/',)\n",
     "JALUR_BEBAS_VIEWER = ('/auth/',)\n"
     "# PABRIK_B1_9SEP2026: admin/kepala HANYA boleh /ops/* (workspace Pabrik), /auth/*, /health.\n"
     "# Gagal-tertutup: endpoint invoice yang ada maupun yang baru otomatis tertutup (K1, K3).\n"
     "JALUR_PABRIK = ('/auth/', '/ops/', '/health')\n", 1),
    ("    peran = security.role_dari_request(request)\n\n    if peran == 'viewer' and request.method in METODE_TULIS",
     "    peran = security.role_dari_request(request)\n\n"
     "    if peran in security.PERAN_PABRIK and not request.url.path.startswith(JALUR_PABRIK):\n"
     "        return JSONResponse(\n"
     "            status_code=403,\n"
     "            content={'detail': 'Peran Pabrik hanya boleh mengakses workspace Pabrik.'},\n"
     "        )\n\n"
     "    if peran == 'viewer' and request.method in METODE_TULIS", 1),
    ("from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, paperless, pembayaran, po, resi, users\n",
     "from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, ops, paperless, pembayaran, po, resi, users\n", 1),
    ("app.include_router(pembayaran.router)\n",
     "app.include_router(pembayaran.router)\napp.include_router(ops.router)  # workspace Pabrik\n", 1),
])

# ---------------- schemas.py: peran baru boleh dibuat/diubah owner
patch("schemas.py", [
    ('pattern="^(owner|staff|viewer)$"', 'pattern="^(owner|staff|viewer|admin|kepala)$"', 2),
])
print("PATCH_B1_OK")
