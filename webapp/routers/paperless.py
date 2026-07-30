import asyncio
import os
import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import settings  # noqa: F401 -- import pertama, lihat settings.py
import config
import schemas
import security
from audit import log_audit
from deps import get_db
from settings import PAPERLESS_BRIDGE_URL, PAPERLESS_POLL_ATTEMPTS, PAPERLESS_POLL_DELAY_SEC

router = APIRouter(prefix="/invoices", tags=["paperless"])


def _get_invoice_badan_usaha(conn, no_invoice: str) -> str:
    cur = conn.cursor()
    cur.execute(
        "SELECT bu.kode FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    return row[0]


async def _check_task(client: httpx.AsyncClient, task_id: str) -> dict:
    resp = await client.post(PAPERLESS_BRIDGE_URL, json={"action": "check_task", "task_id": task_id})
    resp.raise_for_status()
    return resp.json()


@router.post("/{no_invoice:path}/faktur-pajak", response_model=schemas.PaperlessUploadResult)
async def upload_faktur_pajak(
    no_invoice: str,
    file: UploadFile = File(...),
    no_faktur_pajak: str = Form(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Upload lewat bridge n8n "ZZ - Invoice Web - Paperless Bridge"
    (workflow id G7rQLwIu4EbNkyVY) -- TIDAK menyimpan token Paperless di app ini
    (lihat 05_web_platform_plan.md §6b/§6d). Setelah task SUCCESS, document_id
    disimpan ke invoices.paperless_doc_id lewat UPDATE terarah (assert rowcount==1)."""
    kode = _get_invoice_badan_usaha(conn, no_invoice)
    file_bytes = await file.read()
    judul = f"Faktur Pajak {no_invoice}"

    # Arsip LOKAL selain kirim ke Paperless: paket cetak (print_packet.py) butuh
    # berkas fisiknya utk digabung jadi 1 PDF, sedangkan menarik balik dari
    # Paperless butuh jalur download baru di bridge n8n. Menyimpan salinan di
    # sini jauh lebih sederhana & tidak menambah kredensial baru.
    arsip_path = None
    try:
        folder = config.d("faktur_pajak")
        os.makedirs(folder, exist_ok=True)
        ext = (file.filename.rsplit(".", 1)[-1].lower()
               if file.filename and "." in file.filename else "pdf")
        arsip_path = os.path.join(folder, f"fp_{uuid.uuid4().hex}.{ext}")
        with open(arsip_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        arsip_path = None
        print(f"  PERINGATAN: gagal mengarsipkan faktur pajak {no_invoice} secara lokal: {e}")

    async with httpx.AsyncClient(timeout=30) as client:
        files = {"file0": (file.filename or "faktur_pajak.pdf", file_bytes, file.content_type or "application/pdf")}
        data = {"action": "upload", "badan_usaha_kode": kode, "no_invoice": no_invoice, "judul": judul}
        try:
            resp = await client.post(PAPERLESS_BRIDGE_URL, data=data, files=files)
            resp.raise_for_status()
            upload_result = resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Gagal menghubungi bridge Paperless: {e}")

        if not upload_result.get("ok"):
            raise HTTPException(status_code=502, detail=f"Bridge Paperless menolak upload: {upload_result}")
        task_id = upload_result.get("task_id")

        final = None
        for _ in range(PAPERLESS_POLL_ATTEMPTS):
            await asyncio.sleep(PAPERLESS_POLL_DELAY_SEC)
            try:
                check = await _check_task(client, task_id)
            except httpx.HTTPError:
                continue
            if check.get("status") in ("SUCCESS", "FAILURE"):
                final = check
                break

    if final is None:
        # Belum selesai dalam waktu tunggu -- bukan error, tinggal cek lagi nanti
        # lewat GET /invoices/{no_invoice}/faktur-pajak/status?task_id=...
        return schemas.PaperlessUploadResult(ok=True, task_id=task_id, status="PENDING")

    if final.get("status") == "FAILURE":
        return schemas.PaperlessUploadResult(
            ok=False, task_id=task_id, status="FAILURE",
            message="Paperless gagal memproses dokumen (lihat log n8n utk detail)",
        )

    document_id = final.get("document_id")
    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET paperless_doc_id = %s, "
        "no_faktur_pajak = COALESCE(%s, no_faktur_pajak), "
        "faktur_pajak_path = COALESCE(%s, faktur_pajak_path), "
        "tahap_dok = CASE WHEN tahap_dok IN ('terbit','ke_konsultan') THEN 'faktur_ada' ELSE tahap_dok END "
        "WHERE no_invoice = %s RETURNING id",
        (document_id, no_faktur_pajak, arsip_path, no_invoice),
    )
    row = cur.fetchone()
    if row is None or cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Gagal menyimpan document_id ke invoice (rowcount != 1)")
    log_audit(conn, user.id, "upload_faktur_pajak", "invoices", no_invoice,
               {"paperless_doc_id": document_id, "task_id": task_id})
    conn.commit()

    return schemas.PaperlessUploadResult(ok=True, task_id=task_id, status="SUCCESS", document_id=document_id)


@router.get("/{no_invoice:path}/faktur-pajak/status", response_model=schemas.PaperlessUploadResult)
async def check_faktur_pajak_status(
    no_invoice: str,
    task_id: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Dipakai frontend utk polling ulang kalau upload sebelumnya balas PENDING."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            check = await _check_task(client, task_id)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Gagal menghubungi bridge Paperless: {e}")

    st = check.get("status", "unknown")
    if st == "SUCCESS":
        document_id = check.get("document_id")
        cur = conn.cursor()
        cur.execute(
            "UPDATE invoices SET paperless_doc_id = %s, "
            "tahap_dok = CASE WHEN tahap_dok IN ('terbit','ke_konsultan') THEN 'faktur_ada' ELSE tahap_dok END "
            "WHERE no_invoice = %s RETURNING id",
            (document_id, no_invoice),
        )
        row = cur.fetchone()
        if row is not None and cur.rowcount == 1:
            log_audit(conn, user.id, "upload_faktur_pajak", "invoices", no_invoice,
                       {"paperless_doc_id": document_id, "task_id": task_id, "via": "status_poll"})
            conn.commit()
        return schemas.PaperlessUploadResult(ok=True, task_id=task_id, status="SUCCESS", document_id=document_id)
    if st == "FAILURE":
        return schemas.PaperlessUploadResult(ok=False, task_id=task_id, status="FAILURE")
    return schemas.PaperlessUploadResult(ok=True, task_id=task_id, status=st)
