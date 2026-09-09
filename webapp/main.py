"""
main.py -- entrypoint FastAPI utk Invoice Web Dashboard (Fase 1).

Jalankan (di /home/izawa/invoice-sandbox/webapp, venv sudah aktif):
    uvicorn main:app --host 0.0.0.0 --port 8100

Baca dulu 05_web_platform_plan.md & 02_db_schema.md sebelum mengubah endpoint apa
pun -- app ini HANYA boleh menyentuh tabel inti invoice (badan_usaha,
purchase_orders, bap, invoices, invoice_items, app_users, app_audit_log), jangan
pernah menyentuh tabel domain lain yang berbagi Postgres yang sama (guru,
penggajian_guru, personal_finance_transactions, dst).
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import settings  # HARUS diimpor PALING AWAL -- ini yang menambahkan folder kode
                 # invoice (config.py, db_helper.py, dst) ke sys.path. Modul lain
                 # di bawah ini (termasuk semua routers/*) bergantung pada urutan ini.
import db_helper
import security
from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, ops, paperless, pembayaran, po, resi, users

app = FastAPI(
    title="Invoice Web Dashboard API",
    description="Fase 1 -- dashboard PO/BAP/Invoice multi-badan-usaha + bridge Paperless",
    version="0.1.0",
)

METODE_TULIS = {'POST', 'PATCH', 'PUT', 'DELETE'}
JALUR_BEBAS_VIEWER = ('/auth/',)
# PABRIK_B1_9SEP2026: admin/kepala HANYA boleh /ops/* (workspace Pabrik), /auth/*, /health.
# Gagal-tertutup: endpoint invoice yang ada maupun yang baru otomatis tertutup (K1, K3).
JALUR_PABRIK = ('/auth/', '/ops/', '/health')
TIPE_BERKAS = ('application/pdf', 'application/octet-stream', 'application/zip')


@app.middleware('http')
async def penjaga_viewer(request: Request, call_next):
    '''Penjaga GLOBAL peran viewer (keputusan owner 4 Sep 2026).

    Viewer = PENGAMAT MURNI: boleh membaca apa saja (termasuk pelunasan, yang
    justru ditutup dari staf), tapi TIDAK boleh menulis dan TIDAK boleh mengunduh.

    Dua lapis, keduanya sengaja GAGAL-TERTUTUP:
      1. TULIS  -- semua POST/PATCH/PUT/DELETE ditolak. Dikecualikan /auth/*
         (login & ganti password sendiri memang POST dan wajib bisa dipakai).
      2. UNDUH  -- unduhan memakai GET, jadi tidak tertangkap lapis 1. Yang
         diperiksa BALASANNYA: kalau berupa lampiran berkas (Content-Disposition
         attachment) atau tipe berkas biner, ditolak.

    Sengaja middleware, BUKAN dependency per-endpoint: ada 8 endpoint unduhan di
    7 router; menambal satu per satu berarti endpoint BARU yang lupa dipasangi
    penjaga langsung jadi lubang. Di sini yang baru pun otomatis tertutup.

    CATATAN URUTAN: didaftarkan SEBELUM CORSMiddleware supaya CORS tetap lapisan
    terluar -- balasan 403 di sini harus tetap membawa header CORS, kalau tidak
    browser hanya melihat error jaringan tanpa keterangan.
    '''
    peran = security.role_dari_request(request)

    if peran in security.PERAN_PABRIK and not request.url.path.startswith(JALUR_PABRIK):
        return JSONResponse(
            status_code=403,
            content={'detail': 'Peran Pabrik hanya boleh mengakses workspace Pabrik.'},
        )

    if peran == 'viewer' and request.method in METODE_TULIS \
            and not request.url.path.startswith(JALUR_BEBAS_VIEWER):
        return JSONResponse(
            status_code=403,
            content={'detail': 'Peran Pengamat hanya boleh melihat -- tidak boleh mengubah data.'},
        )

    response = await call_next(request)

    if peran == 'viewer':
        cd = (response.headers.get('content-disposition') or '').lower()
        ct = (response.headers.get('content-type') or '').split(';')[0].strip().lower()
        if 'attachment' in cd or ct in TIPE_BERKAS:
            return JSONResponse(
                status_code=403,
                content={'detail': 'Peran Pengamat tidak boleh mengunduh berkas.'},
            )

    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(badan_usaha.router)
app.include_router(po.router)
app.include_router(bap.router)
app.include_router(invoices.router)
app.include_router(paperless.router)
app.include_router(users.router)
app.include_router(mitra.router)
app.include_router(faktur_pajak.router)
app.include_router(resi.router)
app.include_router(dokumen.router)
app.include_router(pembayaran.router)
app.include_router(ops.router)  # workspace Pabrik


@app.get("/health")
def health():
    """Cek konektivitas DB -- dipakai monitoring & smoke test deploy."""
    try:
        conn = db_helper.get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()
        return {"ok": True, "db": "connected"}
    except Exception as e:
        return {"ok": False, "db": f"error: {e}"}
