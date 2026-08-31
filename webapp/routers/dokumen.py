"""
routers/dokumen.py -- fitur "Cek" (Rekap Invoice) + proxy unduh dokumen dari
Paperless. Sumber unduhan adalah PAPERLESS (bukan berkas lokal), sesuai keputusan
decouple: sistem tak lagi bergantung PC/mount.

Prefix /dokumen (sengaja BEDA dari /invoices supaya tidak bentrok dgn route
greedy `/{no_invoice:path}` di routers/invoices.py & routers/paperless.py).

- GET  /dokumen/invoice/{no_invoice}  -> daftar dokumen terkait invoice yang ADA
                                         di Paperless (Invoice PDF, Faktur, BAP, Resi),
                                         tiap item: {jenis, judul, doc_id}.
- GET  /dokumen/{doc_id}/download     -> tarik isi dokumen dari Paperless & alirkan
                                         ke browser (attachment).
- POST /dokumen/lepas                 -> putus tautan doc_id dari satu baris (set NULL),
                                         berkas TETAP di Paperless (bukan hapus).
"""
import settings  # noqa: F401 -- import pertama (lihat settings.py)
import security
from audit import log_audit
from deps import get_db
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import paperless_client as pc

router = APIRouter(prefix="/dokumen", tags=["dokumen"])


@router.get("/invoice/{no_invoice:path}")
def cek_dokumen_invoice(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Kembalikan dokumen invoice yang tersedia di Paperless, siap diunduh.
    Hanya menampilkan yang doc_id-nya TIDAK NULL (sudah terarsip)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, paperless_inv_id, paperless_doc_id, no_faktur_pajak, resi_id "
        "FROM invoices WHERE no_invoice = %s",
        (no_invoice,),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice %s tidak ditemukan" % no_invoice)
    inv_id, paperless_inv_id, paperless_doc_id, no_fp, resi_id = row

    dok = []
    if paperless_inv_id:
        dok.append({"jenis": "Invoice", "judul": "Invoice %s" % no_invoice,
                    "doc_id": int(paperless_inv_id)})
    if paperless_doc_id:
        judul = "Faktur Pajak %s" % (no_fp or no_invoice)
        dok.append({"jenis": "Faktur Pajak", "judul": judul, "doc_id": int(paperless_doc_id)})

    # BAP nota yang dipakai invoice ini
    cur.execute(
        "SELECT no_bap, paperless_doc_id FROM app_bap_nota "
        "WHERE dipakai_invoice = %s AND paperless_doc_id IS NOT NULL "
        "ORDER BY id",
        (no_invoice,),
    )
    for no_bap, did in cur.fetchall():
        dok.append({"jenis": "BAP", "judul": "BAP %s" % (no_bap or "-"), "doc_id": int(did)})

    # Resi pengiriman (kalau invoice sudah masuk resi)
    if resi_id:
        cur.execute(
            "SELECT no_resi, kurir, paperless_doc_id FROM app_resi WHERE id = %s",
            (resi_id,),
        )
        r = cur.fetchone()
        if r and r[2]:
            no_resi, kurir, did = r
            judul = "Resi %s%s" % (no_resi or "-", (" (%s)" % kurir) if kurir else "")
            dok.append({"jenis": "Resi", "judul": judul, "doc_id": int(did)})

    return {"no_invoice": no_invoice, "paperless_aktif": pc.paperless_aktif(), "dokumen": dok}


@router.get("/{doc_id}/download")
def download_dokumen(
    doc_id: int,
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Proxy unduh: tarik isi dokumen dari Paperless & kirim ke browser."""
    if not pc.paperless_aktif():
        raise HTTPException(status_code=503, detail="Paperless tidak aktif")
    try:
        isi, ct, nama = pc.unduh(doc_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Gagal menghubungi Paperless: %s" % str(e)[:150])
    return Response(
        content=isi,
        media_type=ct or "application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="%s"' % nama},
    )


class LepasReq(BaseModel):
    target: str  # 'invoice' | 'faktur' | 'bap' | 'resi'
    no_invoice: Optional[str] = None
    id: Optional[int] = None


_LEPAS_MAP = {
    "invoice": ("invoices", "no_invoice", "paperless_inv_id"),
    "faktur": ("invoices", "no_invoice", "paperless_doc_id"),
    "bap": ("app_bap_nota", "id", "paperless_doc_id"),
    "resi": ("app_resi", "id", "paperless_doc_id"),
}


@router.post("/lepas")
def lepas_dokumen(
    body: LepasReq,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Putus tautan doc_id (set NULL). Berkas TETAP di Paperless (bukan hapus)."""
    if body.target not in _LEPAS_MAP:
        raise HTTPException(status_code=400, detail="target tidak dikenal")
    tabel, kolom_id, kolom_doc = _LEPAS_MAP[body.target]
    kunci = body.no_invoice if kolom_id == "no_invoice" else body.id
    if kunci is None:
        raise HTTPException(status_code=400, detail="butuh no_invoice atau id")
    cur = conn.cursor()
    cur.execute(
        "UPDATE %s SET %s = NULL WHERE %s = %%s" % (tabel, kolom_doc, kolom_id),
        (kunci,),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=404, detail="Baris tidak ditemukan")
    log_audit(conn, user.id, "lepas_paperless", tabel, str(kunci), {"target": body.target})
    conn.commit()
    return {"ok": True}
