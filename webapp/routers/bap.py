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
    "n.created_at, n.sumber, n.mitra_pt_id, pt.nama, n.deteksi_status, "
    "n.dipakai_invoice, n.nopol, n.ocr_json->>'jumlah_sak' "
    "FROM app_bap_nota n LEFT JOIN app_mitra_pt pt ON pt.id = n.mitra_pt_id"
)


class BAPMitraIn(BaseModel):
    pt_id: int


def _int_atau_none(v):
    """jumlah_sak di ocr_json bisa "180", 180, 180.0, "" atau None."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _nota_row(r) -> schemas.BAPNotaOut:
    return schemas.BAPNotaOut(
        id=r[0], badan_usaha_kode=r[1], jenis=r[2], no_bap=r[3], site=r[4],
        tanggal=r[5],
        qty_kg=float(r[6]) if r[6] is not None else None,
        qty_m3=float(r[7]) if r[7] is not None else None,
        confidence=r[8], original_filename=r[9], downloaded_at=r[10], created_at=r[11],
        sumber=r[12], mitra_pt_id=r[13], mitra_pt_nama=r[14], deteksi_status=r[15],
        dipakai_invoice=r[16],
        nopol=r[17], sak=_int_atau_none(r[18]),
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
        import sys
        print(f"[OCR] gagal membaca {filename}: {e}", file=sys.stderr)   # 30 Sep 2026: jangan diam-diam
        return {"jenis": "LAIN", "confidence": "low", "error": str(e)[:200], "catatan": str(e)[:200]}


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

    # 19 Agu 2026 (revisi): ocr_doc.bagian_dari_berkas() merender PDF halaman 1 DAN 2
    # (pdftoppm -l 2) lalu mengirim KEDUA gambar dalam satu permintaan, sementara PROMPT
    # meminta SATU objek JSON. Kontraknya ambigu -> model kadang membalas array.
    # Dua kemungkinan yang HARUS dibedakan, bukan ditolak semua:
    #   (a) satu BAP yang panjangnya >1 halaman  -> gabungkan jadi satu dict
    #   (b) beberapa BAP BERBEDA dalam satu berkas -> tolak, jangan pernah menebak
    #       (mengambil elemen pertama = BAP kedua hilang diam-diam & PO terpotong kurang)
    if isinstance(ocr, list):
        entri = [e for e in ocr if isinstance(e, dict)]
        nomor = []
        for e in entri:
            n = (e.get("no_bap") or "").strip()
            if n and n not in nomor:
                nomor.append(n)

        if len(nomor) > 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Berkas ini berisi {len(nomor)} BAP dengan nomor berbeda "
                    f"({', '.join(nomor)}). Sistem menerima satu BAP per berkas. "
                    f"Pecah jadi {len(nomor)} file, unggah satu per satu, lalu centang "
                    "semuanya saat menerbitkan invoice -- hasilnya tetap satu invoice."
                ),
            )

        # <=1 nomor unik -> halaman lanjutan dari BAP yang sama. Gabungkan.
        PENTING = ("no_bap", "tanggal", "qty_kg", "qty_m3", "site")

        def _kosong(v):
            """Halaman kosong/lanjutan sering dibaca model sebagai 0 atau "" --
            itu BUKAN informasi, jadi tidak boleh dihitung sebagai nilai yang
            bentrok. qty_kg=0 pada BAP KKS (satuan m3) juga berarti 'tidak berlaku'.
            """
            if v is None:
                return True
            if isinstance(v, bool):
                return False
            if isinstance(v, str):
                return v.strip() in ("", "0", "-")
            if isinstance(v, (int, float)):
                return v == 0
            if isinstance(v, (list, dict)):
                return len(v) == 0
            return False

        gabung = {}
        for e in entri:
            for k, v in e.items():
                if _kosong(v):
                    continue
                if k not in gabung:
                    gabung[k] = v
                elif gabung[k] != v and k in PENTING:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Halaman-halaman berkas ini memberi nilai berbeda untuk "
                            f"'{k}' ({gabung[k]} vs {v}), jadi sistem tidak bisa memastikan "
                            "mana yang benar. Unggah halaman BAP-nya saja sebagai satu "
                            "berkas, atau periksa apakah berkas ini memuat lebih dari satu BAP."
                        ),
                    )
        ocr = gabung or {"jenis": "LAIN", "confidence": "low"}

    elif not isinstance(ocr, dict):
        ocr = {"jenis": "LAIN", "confidence": "low"}

    # Fase 1: tolak BAP dgn nomor yang sama persis kalau sudah pernah tercatat
    # (server-side -- pengecekan client-side di wizard bisa dilewati dgn
    # panggilan API langsung/UI lain). Dicek server SEBELUM diarsipkan supaya
    # tidak ada baris app_bap_nota duplikat yang keburu tersimpan.
    no_bap_baca = (ocr.get("no_bap") or "").strip()
    if no_bap_baca:
        cur_dup = conn.cursor()
        cur_dup.execute(
            "SELECT id, original_filename, created_at FROM app_bap_nota "
            "WHERE no_bap = %s ORDER BY id DESC LIMIT 1",
            (no_bap_baca,),
        )
        dup = cur_dup.fetchone()
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"BAP nomor {no_bap_baca} sudah pernah diunggah sebelumnya "
                    f"(arsip id={dup[0]}, berkas '{dup[1]}', pada {dup[2]}). "
                    f"Kalau ini memang pengganti, hapus dulu arsip lama di menu BAP, "
                    f"atau periksa apakah nomor BAP terbaca keliru."
                ),
            )

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
    belum_invoice: bool = Query(default=False),
    badan_usaha_kode: Optional[str] = Query(default=None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Default: HANYA yang belum diunduh (permintaan owner: begitu diunduh, nota
    hilang dari daftar -- arsip tetap ada, set include_downloaded=true utk lihat).
    belum_invoice=true (31 Jul 2026): filter tambahan independen dari downloaded_at --
    HANYA nota yang dipakai_invoice IS NULL (belum pernah dipakai generate invoice).
    Dipakai kartu 'BAP Belum Diterbitkan Invoice' di /bap supaya BAP yang sudah
    terunggah tetap kelihatan lintas navigasi halaman (akar perbaikan bug 'unggah
    ulang ditolak')."""
    sql = _NOTA_SELECT + " WHERE 1=1"
    params = []
    if not include_downloaded:
        sql += " AND n.downloaded_at IS NULL"
    if belum_invoice:
        sql += " AND n.dipakai_invoice IS NULL"
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


@router.delete("/nota/{nota_id}")
def hapus_bap_nota(
    nota_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Hapus arsip BAP nota yang SALAH diunggah (record DB + file nota cetak).
    Dipakai tombol 'Hapus' di Arsip BAP pada wizard Terbit Invoice. TIDAK
    menyentuh invoice/PO -- hanya membuang arsip nota yang keliru."""
    cur = conn.cursor()
    cur.execute("SELECT nota_pdf_path, no_bap FROM app_bap_nota WHERE id = %s", (nota_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Nota BAP tidak ditemukan")
    nota_path, no_bap = row
    cur.execute("DELETE FROM app_bap_nota WHERE id = %s", (nota_id,))
    log_audit(conn, user.id, "hapus_bap_nota", "app_bap_nota", nota_id, {"no_bap": no_bap})
    conn.commit()
    try:
        jp = bap_arsip.jalur(nota_path) if nota_path else None
        if jp and os.path.exists(jp):
            os.remove(jp)
    except Exception:
        pass
    return {"deleted": nota_id, "no_bap": no_bap}
