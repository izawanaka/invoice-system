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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import settings  # HARUS diimpor PALING AWAL -- ini yang menambahkan folder kode
                 # invoice (config.py, db_helper.py, dst) ke sys.path. Modul lain
                 # di bawah ini (termasuk semua routers/*) bergantung pada urutan ini.
import db_helper
from routers import auth, badan_usaha, bap, dokumen, faktur_pajak, invoices, mitra, paperless, pembayaran, po, resi, users

app = FastAPI(
    title="Invoice Web Dashboard API",
    description="Fase 1 -- dashboard PO/BAP/Invoice multi-badan-usaha + bridge Paperless",
    version="0.1.0",
)

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
