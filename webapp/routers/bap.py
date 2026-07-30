from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import settings  # noqa: F401 -- import pertama, lihat settings.py
import bap_arsip
import schemas
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/bap", tags=["bap"])

# SELECT eksplisit (dengan nama PT hasil deteksi/konfirmasi) -- menggantikan
# bap_arsip.KOLOM supaya bisa ikut menampilkan mitra_pt_nama.
_NOTA_SELECT = (
    "SELECT n.id, n.badan_usaha_kode, n.jenis, n.no_bap, n.site, n.tanggal, "
    "n.qty_kg, n.qty_m3, n.confidence, n.original_filename, n.downloaded_at, "
    "n.created_at, n.sumber, n.mitra_pt_id, pt.nama, n.deteksi_status "
    "FROM app_bap_nota n LEFT JOIN app_mitra_pt pt ON pt.id = n.mitra_pt_id"
)


class BAPMitraIn(BaseModel):
    pt_id: int


def _nota_row(r) -> schemas.BAPNotaOut:
    return schemas.BAPNotaOut(
        id=r[0], badan_usaha_kode=r[1], jenis=r[2], no_bap=r[3], site=r[4],
        tanggal=r[5],
        qty_kg=float(r[6]) if r[6] is not None else None,
        qty_m3=float(r[7]) if r[7] is not None else None,
        confidence=r[8], original_filename=r[9], downloaded_at=r[10], created_at=r[11],
        sumber=r[12], mitra_pt_id=r[13], mitra_pt_nama=r[14], deteksi_status=r[15],
    )


def _fetch_nota(conn, nota_id) -> Optional[schemas.BAPNotaOut]:
    cur = conn.cursor()
    cur.execute(_NOTA_SELECT + " WHERE n.id = %s", (nota_id,))
    r = cur.fetchone()
    return _nota_row(r) if r else None


def _ocr_berkas(filename: str, data: bytes) -> dict:
    """OCR memakai fungsi ocr_doc.py yang SAMA PERSIS dgn bot Telegram (model,
    prompt, koreksi site) -- ocr_doc.py sendiri TIDAK diubah. Kegagalan OCR tidak
    menggagalkan unggahan: berkas tetap diarsipkan dgn confidence low."""
    try:
        import ocr_doc
        ocr = ocr_doc.baca_dokumen(ocr_doc.bagian_dari_berkas(filename, data))
        try:
            ocr_doc.terapkan_pt_site(ocr)
        except Exception:
            pass
        return ocr
    except Exception as e:
        return {"jenis": "LAIN", "confidence": "low", "error": str(e)[:200]}


@router.get("", response_model=List[schemas.BAPOut])
def list_bap(
    badan_usaha_kode: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    sql = (
        "SELECT b.id, bu.kode, b.no_bap, b.site, b.tgl_bap, b.total_qty, b.satuan, "
        "b.status, b.created_at "
        "FROM bap b JOIN badan_usaha bu ON bu.id = b.badan_usaha_id WHERE 1=1"
    )
    params = []
    if badan_usaha_kode:
        sql += " AND bu.kode = %s"
        params.append(badan_usaha_kode.upper())
    if status_filter:
        sql += " AND b.status = %s"
        params.append(status_filter)
    sql += " ORDER BY b.tgl_bap DESC NULLS LAST, b.id DESC"

    cur = conn.cursor()
    cur.execute(sql, params)
    return [
        schemas.BAPOut(
            id=r[0], badan_usaha_kode=r[1], no_bap=r[2], site=r[3], tgl_bap=r[4],
            total_qty=float(r[5]), satuan=r[6], status=r[7], created_at=r[8],
        )
        for r in cur.fetchall()
    ]


# ---------- Nota cetak (unggahan BAP dari web) ----------

@router.post("/nota", response_model=schemas.BAPNotaOut, status_code=201)
async def upload_bap_nota(
    file: UploadFile = File(...),
    badan_usaha_kode: Optional[str] = Form(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Unggah BAP (foto/PDF) -> arsip + OCR (fungsi ocr_doc.py yg sama dgn bot) +
    nota cetak, lalu sistem MENEBAK BAP ini untuk PT/mitra mana (dari PO aktif yg
    site-nya cocok & sudah ditautkan owner ke PT). Ragu -> deteksi_status=
    'perlu_konfirmasi' (admin pilih PT via POST /bap/nota/{id}/mitra)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 15 MB)")

    nama = file.filename or "unggahan.bin"
    ocr = _ocr_berkas(nama, data)
    row = bap_arsip.daftarkan(nama, data, ocr, sumber="web",
                              badan_usaha_kode=badan_usaha_kode,
                              uploaded_by=user.id, conn=conn)
    log_audit(conn, user.id, "upload_bap_nota", "app_bap_nota", row[0],
              {"no_bap": ocr.get("no_bap"), "file": nama, "sumber": "web"})
    conn.commit()
    return _fetch_nota(conn, row[0])


@router.get("/nota", response_model=List[schemas.BAPNotaOut])
def list_bap_nota(
    include_downloaded: bool = Query(default=False),
    badan_usaha_kode: Optional[str] = Query(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Default: HANYA yang belum diunduh (permintaan owner: begitu diunduh, nota
    hilang dari daftar -- arsip tetap ada, set include_downloaded=true utk lihat)."""
    sql = _NOTA_SELECT + " WHERE 1=1"
    params = []
    if not include_downloaded:
        sql += " AND n.downloaded_at IS NULL"
    if badan_usaha_kode:
        sql += " AND n.badan_usaha_kode = %s"
        params.append(badan_usaha_kode.upper())
    sql += " ORDER BY n.created_at DESC, n.id DESC"
    cur = conn.cursor()
    cur.execute(sql, params)
    return [_nota_row(r) for r in cur.fetchall()]


@router.post("/nota/{nota_id}/mitra", response_model=schemas.BAPNotaOut)
def konfirmasi_mitra(
    nota_id: int,
    body: BAPMitraIn,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Admin menegaskan BAP ini untuk PT mana (dipakai saat deteksi otomatis ragu).
    Menyetel mitra_pt_id + deteksi_status='manual'."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_bap_nota WHERE id = %s", (nota_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="BAP tidak ditemukan")
    cur.execute("SELECT id FROM app_mitra_pt WHERE id = %s", (body.pt_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="PT tidak ditemukan")
    cur.execute("UPDATE app_bap_nota SET mitra_pt_id = %s, deteksi_status = 'manual' WHERE id = %s",
                (body.pt_id, nota_id))
    log_audit(conn, user.id, "konfirmasi_bap_mitra", "app_bap_nota", nota_id, {"pt_id": body.pt_id})
    conn.commit()
    return _fetch_nota(conn, nota_id)


@router.get("/nota/{nota_id}/file")
def download_bap_nota(
    nota_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Kirim PDF nota cetak + tandai downloaded_at (sekali diunduh -> hilang dari
    daftar default). File TIDAK dihapus dari disk (arsip permanen, keputusan owner)."""
    cur = conn.cursor()
    cur.execute("SELECT nota_pdf_path, no_bap, downloaded_at FROM app_bap_nota WHERE id = %s", (nota_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Nota tidak ditemukan")
    nota_path, no_bap, downloaded_at = row

    if downloaded_at is None:
        cur.execute("UPDATE app_bap_nota SET downloaded_at = now() WHERE id = %s", (nota_id,))
        log_audit(conn, user.id, "download_bap_nota", "app_bap_nota", nota_id, {"no_bap": no_bap})
        conn.commit()

    import os
    nota_path = bap_arsip.jalur(nota_path)
    if not nota_path or not os.path.exists(nota_path):
        raise HTTPException(status_code=410, detail="File nota tidak ada lagi di server")
    nama = f"nota_cetak_{(no_bap or 'bap').replace('/', '_')}.pdf"
    return FileResponse(nota_path, media_type="application/pdf", filename=nama)
