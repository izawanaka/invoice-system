import os
import uuid
from typing import List, Optional

import psycopg2

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query, UploadFile,
                     status)
from fastapi.responses import FileResponse

import settings  # noqa: F401 -- import pertama, lihat settings.py
import config
import db_helper
import po_ocr
import schemas
import security
from audit import log_audit
from deps import get_db
from settings import DASHBOARD_BADAN_USAHA, DEFAULT_PO_WARNING_THRESHOLD_PCT

router = APIRouter(prefix="/po", tags=["po"])

# Field JSON tracker per badan usaha yang PUNYA skrip invoice (lihat baca_po_tracker
# di bap_to_invoice.py/_kks.py -- nama field ini HARUS PERSIS sama, jangan diubah).
_TRACKER_REFRESH = {
    "DKP": {"file": config.PO_FILE, "qty": "total_kg", "used": "used_kg", "price": "rp_kg", "unit": "kg"},
    "KKS": {"file": config.PO_FILE_KKS, "qty": "total_m3", "used": "used_m3", "price": "rp_m3", "unit": "m3"},
}


def _get_badan_usaha(conn, kode: str):
    # Ranah sistem = cocopeat (DKP/KKS) SAJA -- TBS/SSMJ/GBU ditolak eksplisit
    # (keputusan owner 28 Jul 2026, lihat settings.DASHBOARD_BADAN_USAHA).
    if kode.upper() not in DASHBOARD_BADAN_USAHA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Badan usaha '{kode}' di luar ranah sistem invoice cocopeat (hanya DKP & KKS)",
        )
    cur = conn.cursor()
    cur.execute("SELECT id, aktif FROM badan_usaha WHERE kode = %s", (kode.upper(),))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Badan usaha '{kode}' tidak dikenal")
    return row  # (id, aktif)


@router.get("", response_model=List[schemas.POSisaOut])
def list_po(
    badan_usaha_kode: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    warning_only: bool = Query(default=False),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Sumber: view v_po_sisa (sudah menghitung sisa_qty & pct_used dari Postgres --
    JANGAN hitung ulang di Python, lihat 02_db_schema.md). warning_threshold_pct
    diambil lewat join ke purchase_orders karena kolom ini belum ada di view."""
    sql = (
        "SELECT v.kode, v.po_no, v.site, v.customer, v.satuan, v.total_qty, v.used_qty, "
        "v.sisa_qty, v.harga_satuan, v.pct_used, v.status, po.warning_threshold_pct "
        "FROM v_po_sisa v "
        "JOIN badan_usaha bu ON bu.kode = v.kode "
        "JOIN purchase_orders po ON po.badan_usaha_id = bu.id AND po.po_no = v.po_no "
        "WHERE 1=1"
    )
    params = []
    if badan_usaha_kode:
        sql += " AND v.kode = %s"
        params.append(badan_usaha_kode.upper())
    if status_filter:
        sql += " AND v.status = %s"
        params.append(status_filter)
    sql += " ORDER BY v.kode, v.po_no"

    cur = conn.cursor()
    cur.execute(sql, params)
    out = []
    for r in cur.fetchall():
        kode, po_no, site, customer, satuan, total_qty, used_qty, sisa_qty, harga_satuan, pct_used, st, threshold = r
        thr = float(threshold) if threshold is not None else DEFAULT_PO_WARNING_THRESHOLD_PCT
        is_warning = (st == "aktif") and ((100 - float(pct_used)) <= thr)
        item = schemas.POSisaOut(
            kode=kode, po_no=po_no, site=site, customer=customer, satuan=satuan,
            total_qty=float(total_qty), used_qty=float(used_qty), sisa_qty=float(sisa_qty),
            harga_satuan=float(harga_satuan) if harga_satuan is not None else None,
            pct_used=float(pct_used), status=st,
            warning_threshold_pct=float(threshold) if threshold is not None else None,
            is_warning=is_warning,
        )
        if warning_only and not is_warning:
            continue
        out.append(item)
    return out


@router.get("/{po_no}/invoices", response_model=List[schemas.POInvoiceCutOut])
def list_po_invoices(
    po_no: str,
    badan_usaha_kode: str = Query(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Permintaan owner (28 Jul): klik PO -> tampil invoice apa saja yang memotong
    PO tsb. Sumber utama = invoice_items.po_id (rincian alokasi per BAP, akurat utk
    invoice multi-PO/FIFO). Fallback = invoices.po_id langsung utk invoice lama yg
    (kalau ada) tidak punya baris invoice_items menunjuk PO ini."""
    bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s",
        (bu_id, po_no),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PO {po_no} tidak ditemukan utk badan usaha ini")
    po_id = row[0]

    cur.execute(
        "SELECT i.no_invoice, i.tgl_invoice, i.status, ii.no_bap, ii.qty, ii.satuan, ii.subtotal, i.seq_no "
        "FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id "
        "WHERE ii.po_id = %s "
        "UNION ALL "
        "SELECT i.no_invoice, i.tgl_invoice, i.status, NULL, i.total_qty, i.satuan, i.sub_total, i.seq_no "
        "FROM invoices i "
        "WHERE i.po_id = %s AND NOT EXISTS ("
        "  SELECT 1 FROM invoice_items x WHERE x.invoice_id = i.id AND x.po_id = i.po_id"
        ") "
        "ORDER BY 8, 1",
        (po_id, po_id),
    )
    # Halaman rincian PO ikut menampilkan status invoice pemotong -- itu juga
    # informasi pelunasan, jadi disembunyikan dari staf dgn aturan yang sama.
    lihat_pelunasan = security.boleh_lihat_pelunasan(user)
    return [
        schemas.POInvoiceCutOut(
            no_invoice=r[0], tgl_invoice=r[1],
            status=r[2] if lihat_pelunasan else None, no_bap=r[3],
            qty=float(r[4]) if r[4] is not None else 0.0, satuan=r[5],
            subtotal=float(r[6]) if r[6] is not None else None,
        )
        for r in cur.fetchall()
    ]


@router.post("", response_model=schemas.POOut, status_code=status.HTTP_201_CREATED)
def create_po(
    body: schemas.POCreateRequest,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Invariant I8 (DESIGN.md): PO baru WAJIB masuk Postgres dulu. po_tracker*.json
    di-regenerate dari DB SETELAH commit -- file JSON tidak pernah jadi sumber
    independen. Hanya berlaku regenerate utk DKP/KKS (satu-satunya yang punya
    tracker JSON yang benar-benar dibaca skrip invoice)."""
    bu_id, bu_aktif = _get_badan_usaha(conn, body.badan_usaha_kode)
    if not bu_aktif:
        raise HTTPException(status_code=400, detail=f"Badan usaha '{body.badan_usaha_kode}' tidak aktif")

    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s",
        (bu_id, body.po_no),
    )
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail=f"PO {body.po_no} sudah ada untuk badan usaha ini")

    try:
        cur.execute(
            "INSERT INTO purchase_orders "
            "(badan_usaha_id, po_no, site, customer, total_qty, used_qty, satuan, harga_satuan, "
            "cust_addr, payment_terms, status, tgl_masuk, catatan, warning_threshold_pct) "
            "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s, 'aktif', %s, %s, %s) "
            "RETURNING id, created_at",
            (
                bu_id, body.po_no, body.site, body.customer, body.total_qty, body.satuan,
                body.harga_satuan, body.cust_addr, body.payment_terms,
                body.tgl_masuk, body.catatan, body.warning_threshold_pct,
            ),
        )
        new_id, created_at = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        # Fase 1: jaring pengaman race-condition -- pengecekan 409 di atas sudah
        # ada, tapi kalau dua request PO yang sama persis lolos bersamaan
        # (celah waktu antara SELECT cek di atas dan INSERT ini), constraint DB
        # uq_po_per_badu yang jadi penjaga terakhir. Tanpa except ini, klien akan
        # menerima 500 mentah alih-alih pesan yang jelas.
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"PO {body.po_no} sudah ada untuk badan usaha ini (terdeteksi saat commit)",
        )
    log_audit(conn, user.id, "create", "purchase_orders", new_id, body.model_dump(mode="json"))
    conn.commit()

    kode_upper = body.badan_usaha_kode.upper()
    if kode_upper in _TRACKER_REFRESH:
        t = _TRACKER_REFRESH[kode_upper]
        try:
            db_helper.refresh_po_tracker_json(conn, bu_id, t["file"], t["qty"], t["used"], t["price"], t["unit"])
        except Exception as e:
            # PO SUDAH tersimpan di Postgres (sumber kebenaran, I5) -- kegagalan
            # menulis file JSON turunan TIDAK BOLEH membatalkan itu, tapi harus
            # dilaporkan supaya owner tahu tracker perlu di-refresh manual.
            print(f"  PERINGATAN: PO tersimpan di DB tapi gagal refresh {t['file']}: {e}")

    return schemas.POOut(
        id=new_id, badan_usaha_kode=kode_upper, po_no=body.po_no, site=body.site,
        customer=body.customer, total_qty=body.total_qty, used_qty=0, satuan=body.satuan,
        harga_satuan=body.harga_satuan, status="aktif", tgl_masuk=body.tgl_masuk,
        catatan=body.catatan, warning_threshold_pct=body.warning_threshold_pct,
        created_at=created_at,
    )


# ---------- Ekstraksi OCR PO (Fase 2, 30 Jul 2026) ----------
# Endpoint ini HANYA membaca dokumen & mengembalikan pratinjau JSON -- TIDAK
# menyimpan apa pun ke DB. Penyimpanan sesungguhnya tetap lewat POST /po biasa
# (di atas) setelah user meninjau/melengkapi hasil ekstraksi ini di web (aturan
# owner: "selalu tanya ke user sebelum lanjut" utk field yang tidak yakin).

@router.post("/ocr", response_model=schemas.POOcrOut)
async def ocr_po(
    file: UploadFile = File(...),
    badan_usaha_kode: Optional[str] = Form(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 20 MB)")

    try:
        hasil = po_ocr.ekstrak_po(file.filename or "dokumen.jpg", data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal membaca dokumen: {e}")

    # Kalau badan usaha & po_no sama-sama diketahui, kabari dini kalau PO ini
    # sudah ada -- pengecekan FINAL & mengikat tetap di POST /po (409) saat
    # user menyimpan, ini cuma info tambahan di pratinjau.
    if badan_usaha_kode and hasil.get("po_no"):
        try:
            bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s",
                (bu_id, hasil["po_no"]),
            )
            hasil["po_no_sudah_ada"] = cur.fetchone() is not None
        except HTTPException:
            raise
        except Exception:
            hasil["po_no_sudah_ada"] = None

    return schemas.POOcrOut(**hasil)


# ---------- Arsip scan PO asli dari customer ----------
# Keputusan owner (28 Jul 2026): lembar PO yang ikut paket cetak = SCAN ASLI dari
# customer, bukan ringkasan buatan sistem. Berkas diarsipkan permanen di
# <INVOICE_DATA>/po_docs/ dan dirujuk tabel app_po_doc.

@router.post("/{po_no}/dokumen", response_model=schemas.PODocOut, status_code=status.HTTP_201_CREATED)
async def upload_po_dokumen(
    po_no: str,
    badan_usaha_kode: str = Form(...),
    file: UploadFile = File(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)
    cur = conn.cursor()
    cur.execute("SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s",
                (bu_id, po_no))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PO {po_no} tidak ditemukan utk badan usaha ini")
    po_id = row[0]

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 20 MB)")

    folder = config.d("po_docs")
    os.makedirs(folder, exist_ok=True)
    ext = (file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "bin")
    path = os.path.join(folder, f"po_{uuid.uuid4().hex}.{ext}")
    with open(path, "wb") as f:
        f.write(data)

    cur.execute(
        "INSERT INTO app_po_doc (po_id, original_filename, file_path, uploaded_by) "
        "VALUES (%s,%s,%s,%s) RETURNING id, original_filename, created_at",
        (po_id, file.filename, path, user.id),
    )
    new_id, orig, created_at = cur.fetchone()
    log_audit(conn, user.id, "upload_po_dokumen", "app_po_doc", new_id,
              {"po_no": po_no, "file": file.filename})
    conn.commit()
    return schemas.PODocOut(id=new_id, po_no=po_no, original_filename=orig, created_at=created_at)


@router.get("/{po_no}/dokumen", response_model=List[schemas.PODocOut])
def list_po_dokumen(
    po_no: str,
    badan_usaha_kode: str = Query(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)
    cur = conn.cursor()
    cur.execute(
        "SELECT d.id, d.original_filename, d.created_at FROM app_po_doc d "
        "JOIN purchase_orders po ON po.id = d.po_id "
        "WHERE po.badan_usaha_id = %s AND po.po_no = %s ORDER BY d.created_at DESC, d.id DESC",
        (bu_id, po_no),
    )
    return [schemas.PODocOut(id=r[0], po_no=po_no, original_filename=r[1], created_at=r[2])
            for r in cur.fetchall()]


@router.get("/dokumen/{doc_id}/file")
def download_po_dokumen(
    doc_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    cur = conn.cursor()
    cur.execute("SELECT file_path, original_filename FROM app_po_doc WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Dokumen PO tidak ditemukan")
    path, orig = row
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Berkas tidak ada lagi di server")
    return FileResponse(path, filename=orig or os.path.basename(path))


@router.delete("/{po_no}")
def hapus_po(
    po_no: str,
    badan_usaha_kode: str = Query(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Hapus PO yang SALAH diunggah. Ditolak kalau PO sudah dipakai invoice
    (ada baris invoices/invoice_items yang mengacu) demi jaga integritas data.
    Dokumen scan PO & tautan PT ikut dihapus. Tracker JSON di-regenerate dari DB
    (Invariant I8)."""
    bu_id, _aktif = _get_badan_usaha(conn, badan_usaha_kode)
    cur = conn.cursor()
    cur.execute("SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s", (bu_id, po_no))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PO {po_no} tidak ditemukan untuk {badan_usaha_kode.upper()}")
    po_id = row[0]
    cur.execute("SELECT count(*) FROM invoices WHERE po_id = %s", (po_id,))
    n_inv = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM invoice_items WHERE po_id = %s", (po_id,))
    n_items = cur.fetchone()[0]
    if n_inv > 0 or n_items > 0:
        raise HTTPException(
            status_code=409,
            detail=(f"PO {po_no} tidak bisa dihapus karena sudah dipakai invoice "
                    f"({n_inv} invoice, {n_items} baris item). Batalkan/hapus invoicenya dulu."),
        )
    cur.execute("DELETE FROM app_po_doc WHERE po_id = %s", (po_id,))
    cur.execute("DELETE FROM app_mitra_po WHERE po_id = %s", (po_id,))
    cur.execute("DELETE FROM purchase_orders WHERE id = %s", (po_id,))
    log_audit(conn, user.id, "hapus_po", "purchase_orders", po_id,
              {"po_no": po_no, "badan_usaha": badan_usaha_kode.upper()})
    conn.commit()
    kode_upper = badan_usaha_kode.upper()
    if kode_upper in _TRACKER_REFRESH:
        t = _TRACKER_REFRESH[kode_upper]
        try:
            db_helper.refresh_po_tracker_json(conn, bu_id, t["file"], t["qty"], t["used"], t["price"], t["unit"])
        except Exception as e:
            print(f"  PERINGATAN: PO dihapus di DB tapi gagal refresh {t['file']}: {e}")
    return {"deleted": po_no, "badan_usaha_kode": kode_upper}


@router.post("/{po_no}/status")
def set_po_status(
    po_no: str,
    badan_usaha_kode: str = Query(...),
    status_baru: str = Query(..., alias="status"),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Ubah status PO: 'aktif' <-> 'selesai' (mis. menonaktifkan PO yang sudah
    tidak disupply lagi). PO 'selesai' tidak lagi ikut alokasi invoice. Tracker
    JSON di-regenerate dari DB (Invariant I8)."""
    allowed = {"aktif", "selesai", "batal"}
    if status_baru not in allowed:
        raise HTTPException(status_code=400, detail=f"Status tidak valid: {status_baru}. Pilihan: {sorted(allowed)}")
    bu_id, _aktif = _get_badan_usaha(conn, badan_usaha_kode)
    cur = conn.cursor()
    cur.execute("SELECT id FROM purchase_orders WHERE badan_usaha_id = %s AND po_no = %s", (bu_id, po_no))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PO {po_no} tidak ditemukan untuk {badan_usaha_kode.upper()}")
    po_id = row[0]
    cur.execute("UPDATE purchase_orders SET status = %s WHERE id = %s", (status_baru, po_id))
    log_audit(conn, user.id, "set_po_status", "purchase_orders", po_id,
              {"po_no": po_no, "status": status_baru})
    conn.commit()
    kode_upper = badan_usaha_kode.upper()
    if kode_upper in _TRACKER_REFRESH:
        t = _TRACKER_REFRESH[kode_upper]
        try:
            db_helper.refresh_po_tracker_json(conn, bu_id, t["file"], t["qty"], t["used"], t["price"], t["unit"])
        except Exception as e:
            print(f"  PERINGATAN: status PO diubah tapi gagal refresh {t['file']}: {e}")
    return {"po_no": po_no, "status": status_baru}


@router.delete("/dokumen/{doc_id}")
def hapus_po_dokumen(
    doc_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Hapus SATU scan/dokumen PO yang salah diunggah (record app_po_doc + file).
    Tidak menyentuh PO/invoice -- hanya membuang berkas scan yang keliru."""
    cur = conn.cursor()
    cur.execute("SELECT file_path, original_filename FROM app_po_doc WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Dokumen PO tidak ditemukan")
    path, orig = row
    cur.execute("DELETE FROM app_po_doc WHERE id = %s", (doc_id,))
    log_audit(conn, user.id, "hapus_po_dokumen", "app_po_doc", doc_id, {"file": orig})
    conn.commit()
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    return {"deleted": doc_id}
