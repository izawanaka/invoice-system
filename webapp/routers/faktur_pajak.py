"""
faktur_pajak.py -- Router web utk modul Faktur Pajak (Fase 3, 30 Jul 2026).

TUJUAN (kata owner): minimalkan risiko "beda Invoice vs Faktur Pajak". Faktur
Pajak adalah dokumen pajak resmi yang diterbitkan Konsultan/Coretax DJP
SETELAH invoice terbit (lihat Vault Aturan Bisnis #12, 01_architecture_flow.md
"Alur C"), lalu diunggah kembali ke sini utk arsip & cross-check tiga arah
(PO vs BAP vs Invoice vs Faktur Pajak).

ALUR:
  1. POST /faktur-pajak/ocr   -- unggah foto/PDF, HANYA ekstraksi pratinjau
                                 (OCR) + daftar kandidat Invoice yang mungkin
                                 cocok. TIDAK menulis apa pun ke DB/file.
  2. POST /faktur-pajak       -- user SUDAH memilih invoice_id (wajib, tidak
                                 pernah auto-assign) + field (mungkin sudah
                                 diedit user). Baru di sini berkas diarsipkan
                                 & baris faktur_pajak disimpan, cross-check
                                 dijalankan (validation.py), status_cocok
                                 di-set. Invoice terkait ikut diperbarui
                                 (no_faktur_pajak/faktur_pajak_path) & tahap_dok
                                 di-auto-advance ke 'faktur_ada' (tidak pernah
                                 mundur) -- SELARAS dgn Vault Aturan Bisnis #12
                                 (unggahan faktur pajak = tanda faktur pajak
                                 sudah ada), TANPA mengubah endpoint lama
                                 apa pun.
  3. GET /faktur-pajak        -- daftar, filter badan_usaha_kode.
  4. DELETE /faktur-pajak/{id}-- hapus baris yang salah unggah + berkasnya.

ATURAN KETAT (owner): field OCR yang tidak yakin WAJIB null, JANGAN ditebak.
Pemilihan invoice_id SELALU aksi eksplisit user, tidak pernah otomatis.
Mismatch TIDAK ditolak (409) -- faktur pajak legitim bisa beda (mis. tagihan
sebagian) -- hanya ditandai jelas supaya user menyelidiki (Bahasa Indonesia).
"""
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

import settings  # noqa: F401 -- import pertama, lihat settings.py
import config
import db_helper
import faktur_ocr
import schemas
import security
import validation
from audit import log_audit
from deps import get_db
from settings import DASHBOARD_BADAN_USAHA

router = APIRouter(prefix="/faktur-pajak", tags=["faktur-pajak"])

# Toleransi selisih Rupiah yang masih dianggap wajar (pembulatan) -- nilai
# faktur pajak & invoice pada sistem ini biasanya bulat Rupiah, jadi toleransi
# kecil (tidak memakai persentase seperti validation.check_calc_consistency
# krn itu utk cross-check qty x harga, bukan utk dua dokumen independen yang
# semestinya identik persis).
TOLERANSI_RUPIAH = 25.0


def _get_badan_usaha(conn, kode: str):
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
    return row


def _cari_kandidat_invoice(conn, bu_id: int, total_hint: Optional[float], limit: int = 15):
    """Kandidat Invoice utk dipilih user (TIDAK pernah auto-assign). Kalau OCR
    berhasil membaca 'total', invoice dgn grand_total PALING DEKAT ditampilkan
    paling atas; kalau tidak, cukup invoice terbaru per badan usaha. User
    tetap yang memutuskan/mengonfirmasi lewat dropdown di web."""
    cur = conn.cursor()
    if total_hint is not None:
        cur.execute(
            "SELECT id, no_invoice, customer, grand_total, tgl_invoice, dpp, ppn "
            "FROM invoices WHERE badan_usaha_id = %s "
            "ORDER BY abs(grand_total - %s) ASC, tgl_invoice DESC LIMIT %s",
            (bu_id, total_hint, limit),
        )
    else:
        cur.execute(
            "SELECT id, no_invoice, customer, grand_total, tgl_invoice, dpp, ppn "
            "FROM invoices WHERE badan_usaha_id = %s "
            "ORDER BY tgl_invoice DESC, id DESC LIMIT %s",
            (bu_id, limit),
        )
    return [
        schemas.FakturPajakCandidateInvoice(
            invoice_id=r[0], no_invoice=r[1], customer=r[2],
            grand_total=float(r[3]) if r[3] is not None else None,
            tgl_invoice=r[4],
            dpp=float(r[5]) if r[5] is not None else None,
            ppn=float(r[6]) if r[6] is not None else None,
        )
        for r in cur.fetchall()
    ]


@router.post("/ocr", response_model=schemas.FakturPajakOcrOut)
async def ocr_faktur(
    file: UploadFile = File(...),
    badan_usaha_kode: str = Form(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Ekstraksi PRATINJAU SAJA (tidak menulis apa pun ke DB/file). Mengembalikan
    field OCR (null kalau tidak yakin -- aturan owner: jangan pernah menebak)
    + daftar kandidat Invoice yang bisa dipilih user di dropdown."""
    bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 20 MB)")

    try:
        hasil = faktur_ocr.ekstrak_faktur(file.filename or "faktur.jpg", data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal membaca dokumen: {e}")

    kandidat = _cari_kandidat_invoice(conn, bu_id, hasil.get("total"))

    return schemas.FakturPajakOcrOut(**hasil, kandidat_invoice=kandidat)


@router.post("", response_model=schemas.FakturPajakOut, status_code=status.HTTP_201_CREATED)
async def create_faktur_pajak(
    invoice_id: int = Form(..., description="WAJIB -- pilihan eksplisit user, tidak pernah auto-assign"),
    badan_usaha_kode: str = Form(...),
    file: UploadFile = File(...),
    nomor_faktur: Optional[str] = Form(default=None),
    tanggal_faktur: Optional[str] = Form(default=None),
    dpp: Optional[float] = Form(default=None),
    ppn: Optional[float] = Form(default=None),
    total: Optional[float] = Form(default=None),
    catatan_keraguan: Optional[str] = Form(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Simpan Faktur Pajak yang SUDAH ditinjau/dikonfirmasi user (field OCR
    boleh sudah diedit). Menjalankan cross-check dgn Invoice yg dipilih user
    (validation.py pattern) -- mismatch TIDAK ditolak (409), hanya ditandai
    'mismatch' + pesan Indonesia rinci, supaya kasus legitim (mis. tagihan
    sebagian) tetap bisa diarsipkan. Ikut memperbarui invoices.no_faktur_pajak
    /faktur_pajak_path & auto-advance tahap_dok ke 'faktur_ada' (tidak pernah
    mundur) -- selaras Vault Aturan Bisnis #12."""
    bu_id, _ = _get_badan_usaha(conn, badan_usaha_kode)

    cur = conn.cursor()
    cur.execute(
        "SELECT id, dpp, ppn, grand_total, tahap_dok FROM invoices WHERE id = %s AND badan_usaha_id = %s",
        (invoice_id, bu_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Invoice id={invoice_id} tidak ditemukan utk badan usaha ini")
    _, inv_dpp, inv_ppn, inv_grand, tahap_lama = row

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 20 MB)")

    # ---- Cross-check pasif (tidak menolak, hanya menandai) ----
    catatan_selisih_parts = []
    status_cocok = "pending"
    if total is not None or ppn is not None or dpp is not None:
        status_cocok = "matched"
        if ppn is not None and inv_ppn is not None:
            ok, _exp, diff, _pesan = validation.check_calc_consistency(1.0, float(inv_ppn), float(ppn), TOLERANSI_RUPIAH)
            if not ok:
                status_cocok = "mismatch"
                catatan_selisih_parts.append(
                    f"PPN sistem Rp {float(inv_ppn):,.0f} vs Faktur Rp {float(ppn):,.0f} "
                    f"(selisih Rp {diff:,.0f})".replace(",", ".")
                )
        if dpp is not None and inv_dpp is not None:
            ok, _exp, diff, _pesan = validation.check_calc_consistency(1.0, float(inv_dpp), float(dpp), TOLERANSI_RUPIAH)
            if not ok:
                status_cocok = "mismatch"
                catatan_selisih_parts.append(
                    f"DPP sistem Rp {float(inv_dpp):,.0f} vs Faktur Rp {float(dpp):,.0f} "
                    f"(selisih Rp {diff:,.0f})".replace(",", ".")
                )
        if total is not None and inv_grand is not None:
            ok, _exp, diff, _pesan = validation.check_calc_consistency(1.0, float(inv_grand), float(total), TOLERANSI_RUPIAH)
            if not ok:
                status_cocok = "mismatch"
                catatan_selisih_parts.append(
                    f"Total sistem Rp {float(inv_grand):,.0f} vs Faktur Rp {float(total):,.0f} "
                    f"(selisih Rp {diff:,.0f})".replace(",", ".")
                )
    catatan_selisih = "; ".join(catatan_selisih_parts) if catatan_selisih_parts else None

    folder = config.d("faktur_pajak")
    os.makedirs(folder, exist_ok=True)
    ext = (file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "bin")
    path = os.path.join(folder, f"faktur_{uuid.uuid4().hex}.{ext}")
    with open(path, "wb") as f:
        f.write(data)

    cur.execute(
        "INSERT INTO faktur_pajak "
        "(badan_usaha_id, invoice_id, nomor_faktur, tanggal_faktur, dpp, ppn, total, "
        "file_path, original_filename, catatan_keraguan, status_cocok, catatan_selisih, uploaded_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "RETURNING id, created_at",
        (bu_id, invoice_id, nomor_faktur, tanggal_faktur, dpp, ppn, total,
         path, file.filename, catatan_keraguan, status_cocok, catatan_selisih, user.id),
    )
    new_id, created_at = cur.fetchone()

    # Selaras Vault Aturan Bisnis #12: unggahan faktur pajak = tanda faktur
    # pajak sudah ada. Perbarui kolom ringkas di invoices (dipakai paket cetak
    # & tampilan lama) + auto-advance tahap_dok (tidak pernah mundur).
    urutan_tahap = {"terbit": 0, "ke_konsultan": 1, "faktur_ada": 2, "terkirim": 3}
    tahap_baru = tahap_lama
    if urutan_tahap.get(tahap_lama, 0) < urutan_tahap["faktur_ada"]:
        tahap_baru = "faktur_ada"
    cur.execute(
        "UPDATE invoices SET no_faktur_pajak = COALESCE(%s, no_faktur_pajak), "
        "faktur_pajak_path = %s, tahap_dok = %s WHERE id = %s",
        (nomor_faktur, path, tahap_baru, invoice_id),
    )

    log_audit(conn, user.id, "create", "faktur_pajak", new_id, {
        "invoice_id": invoice_id, "nomor_faktur": nomor_faktur, "status_cocok": status_cocok,
        "catatan_selisih": catatan_selisih,
    })
    conn.commit()

    cur.execute("SELECT no_invoice FROM invoices WHERE id = %s", (invoice_id,))
    no_invoice = cur.fetchone()[0]

    return schemas.FakturPajakOut(
        id=new_id, badan_usaha_kode=badan_usaha_kode.upper(), invoice_id=invoice_id,
        no_invoice=no_invoice, nomor_faktur=nomor_faktur, tanggal_faktur=tanggal_faktur,
        dpp=dpp, ppn=ppn, total=total, original_filename=file.filename,
        catatan_keraguan=catatan_keraguan, status_cocok=status_cocok,
        catatan_selisih=catatan_selisih, created_at=created_at,
    )


@router.get("", response_model=List[schemas.FakturPajakOut])
def list_faktur_pajak(
    badan_usaha_kode: Optional[str] = Query(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    sql = (
        "SELECT fp.id, bu.kode, fp.invoice_id, i.no_invoice, fp.nomor_faktur, "
        "fp.tanggal_faktur, fp.dpp, fp.ppn, fp.total, fp.original_filename, "
        "fp.catatan_keraguan, fp.status_cocok, fp.catatan_selisih, fp.created_at "
        "FROM faktur_pajak fp "
        "JOIN badan_usaha bu ON bu.id = fp.badan_usaha_id "
        "JOIN invoices i ON i.id = fp.invoice_id "
        "WHERE 1=1"
    )
    params = []
    if badan_usaha_kode:
        sql += " AND bu.kode = %s"
        params.append(badan_usaha_kode.upper())
    sql += " ORDER BY fp.created_at DESC, fp.id DESC"

    cur = conn.cursor()
    cur.execute(sql, params)
    return [
        schemas.FakturPajakOut(
            id=r[0], badan_usaha_kode=r[1], invoice_id=r[2], no_invoice=r[3],
            nomor_faktur=r[4], tanggal_faktur=str(r[5]) if r[5] else None,
            dpp=float(r[6]) if r[6] is not None else None,
            ppn=float(r[7]) if r[7] is not None else None,
            total=float(r[8]) if r[8] is not None else None,
            original_filename=r[9], catatan_keraguan=r[10], status_cocok=r[11],
            catatan_selisih=r[12], created_at=r[13],
        )
        for r in cur.fetchall()
    ]


@router.get("/{faktur_id}/file")
def download_faktur_pajak(
    faktur_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    cur = conn.cursor()
    cur.execute("SELECT file_path, original_filename FROM faktur_pajak WHERE id = %s", (faktur_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    path, orig = row
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Berkas tidak ada lagi di server")
    return FileResponse(path, filename=orig or os.path.basename(path))


@router.delete("/{faktur_id}")
def hapus_faktur_pajak(
    faktur_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Hapus baris Faktur Pajak yang SALAH diunggah + berkasnya. TIDAK mengubah
    invoices.tahap_dok (tahap operasional tidak pernah mundur otomatis, sesuai
    Vault Aturan Bisnis #12) -- kalau perlu revisi tahap, dilakukan manual lewat
    endpoint PATCH /invoices/{no}/tahap yang sudah ada."""
    cur = conn.cursor()
    cur.execute("SELECT file_path, invoice_id FROM faktur_pajak WHERE id = %s", (faktur_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    path, invoice_id = row
    cur.execute("DELETE FROM faktur_pajak WHERE id = %s", (faktur_id,))
    log_audit(conn, user.id, "hapus_faktur_pajak", "faktur_pajak", faktur_id, {"invoice_id": invoice_id})
    conn.commit()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f"  PERINGATAN: baris faktur_pajak {faktur_id} terhapus tapi gagal hapus berkas {path}: {e}")
    return {"deleted": faktur_id}
