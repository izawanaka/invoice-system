"""
resi.py -- Bukti Resi Pengiriman sebagai ENTITAS BERSAMA (tabel app_resi).

Model baru (31 Jul 2026, permintaan owner "Invoice Gantung"):
- Satu baris `app_resi` = satu resi/kiriman. SATU resi bisa mengirim BANYAK invoice
  (invoices.resi_id -> app_resi.id).
- Invoice "gantung" = tahap_dok <> 'terkirim' (belum ada resi). Begitu dimasukkan ke
  sebuah resi -> tahap_dok = 'terkirim' -> pindah ke Rekap.
- Hapus resi / lepas invoice -> invoice yang menempel BALIK ke gantung
  (resi_id = NULL, tahap_dok = 'terbit').
- Semua aksi = OPERASIONAL, staf boleh (Aturan #11), dicatat app_audit_log.
- Berkas resi diarsipkan lokal ke INVOICE_DATA/resi/ (path relatif di app_resi.resi_path).
  Dorong/tarik Paperless menyusul (T4).
"""
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import settings  # noqa: F401 -- import pertama, lihat settings.py
import config
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/resi", tags=["resi"])

MAX_BYTES = 15 * 1024 * 1024


def _parse_no_invoices(raw: str) -> List[str]:
    """Terima daftar nomor invoice dipisah koma atau baris baru; buang duplikat."""
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _parse_tgl(s: Optional[str]):
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail=f"Format tanggal tidak dikenali: {s}")


def _simpan_berkas(data: bytes, filename: Optional[str]) -> str:
    folder = config.d("resi")
    os.makedirs(folder, exist_ok=True)
    ext = (filename.rsplit(".", 1)[-1].lower()
           if filename and "." in filename else "bin")
    rel = os.path.join("resi", f"resi_{uuid.uuid4().hex}.{ext}")
    with open(config.d(rel), "wb") as f:
        f.write(data)
    return rel


def _cek_status(cur, no_list):
    """Kembalikan (valid_gantung, sudah_terpasang, tak_ada) untuk daftar nomor invoice."""
    if not no_list:
        return [], [], []
    cur.execute(
        "SELECT no_invoice, resi_id FROM invoices WHERE no_invoice = ANY(%s)",
        (no_list,),
    )
    found = {row[0]: row[1] for row in cur.fetchall()}
    valid, terpasang, tak_ada = [], [], []
    for no in no_list:
        if no not in found:
            tak_ada.append(no)
        elif found[no] is not None:
            terpasang.append(no)
        else:
            valid.append(no)
    return valid, terpasang, tak_ada


def _resi_detail(conn, resi_id: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.no_resi, r.kurir, r.tgl_kirim, r.created_at, bu.kode, "
        "r.resi_path, r.paperless_doc_id "
        "FROM app_resi r LEFT JOIN badan_usaha bu ON bu.id = r.badan_usaha_id WHERE r.id = %s",
        (resi_id,),
    )
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Resi tidak ditemukan")
    cur.execute(
        "SELECT i.no_invoice, i.tgl_invoice, i.site, i.customer, i.grand_total, bu.kode "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "WHERE i.resi_id = %s ORDER BY i.seq_no DESC NULLS LAST, i.id DESC",
        (resi_id,),
    )
    invs = [
        {"no_invoice": x[0], "tgl_invoice": str(x[1]) if x[1] else None,
         "site": x[2], "customer": x[3],
         "grand_total": float(x[4]) if x[4] is not None else None,
         "badan_usaha_kode": x[5]}
        for x in cur.fetchall()
    ]
    return {
        "id": r[0], "no_resi": r[1], "kurir": r[2],
        "tgl_kirim": str(r[3]) if r[3] else None,
        "created_at": str(r[4]) if r[4] else None,
        "badan_usaha_kode": r[5],
        "ada_berkas": bool(r[6]),
        "paperless_doc_id": r[7],
        "invoices": invs,
    }


@router.get("")
def list_resi(conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.no_resi, r.kurir, r.tgl_kirim, r.created_at, bu.kode, "
        "(SELECT count(*) FROM invoices i WHERE i.resi_id = r.id), "
        "(SELECT string_agg(i.no_invoice, ', ' ORDER BY i.no_invoice) "
        " FROM invoices i WHERE i.resi_id = r.id) "
        "FROM app_resi r LEFT JOIN badan_usaha bu ON bu.id = r.badan_usaha_id "
        "ORDER BY r.id DESC"
    )
    return [
        {"id": r[0], "no_resi": r[1], "kurir": r[2],
         "tgl_kirim": str(r[3]) if r[3] else None,
         "created_at": str(r[4]) if r[4] else None,
         "badan_usaha_kode": r[5], "jml_invoice": int(r[6] or 0),
         "daftar_invoice": r[7] or ""}
        for r in cur.fetchall()
    ]


@router.get("/{resi_id}")
def detail_resi(resi_id: int, conn=Depends(get_db),
                user: security.CurrentUser = Depends(security.get_current_user)):
    return _resi_detail(conn, resi_id)


@router.get("/{resi_id}/file")
def download_resi_file(resi_id: int, conn=Depends(get_db),
                       user: security.CurrentUser = Depends(security.get_current_user)):
    cur = conn.cursor()
    cur.execute("SELECT resi_path FROM app_resi WHERE id = %s", (resi_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Resi tidak ditemukan")
    rel = row[0]
    if not rel:
        raise HTTPException(status_code=404, detail="Berkas resi belum ada")
    path = rel if os.path.isabs(rel) else config.d(rel)
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Berkas resi tidak ada lagi di server")
    nama = f"resi_{resi_id}.{rel.rsplit('.', 1)[-1]}"
    return FileResponse(path, filename=nama)


@router.post("", status_code=201)
async def buat_resi(
    file: UploadFile = File(...),
    no_invoices: str = Form(...),
    no_resi: Optional[str] = Form(None),
    kurir: Optional[str] = Form(None),
    tgl_kirim: Optional[str] = Form(None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Buat resi baru + tautkan invoice gantung yang dicentang -> pindah 'terkirim'."""
    no_list = _parse_no_invoices(no_invoices)
    if not no_list:
        raise HTTPException(status_code=400, detail="Pilih minimal satu invoice untuk resi ini")
    tgl = _parse_tgl(tgl_kirim)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Berkas resi kosong")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Berkas terlalu besar (maks 15 MB)")

    cur = conn.cursor()
    valid, terpasang, tak_ada = _cek_status(cur, no_list)
    if tak_ada:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan: " + ", ".join(tak_ada))
    if terpasang:
        raise HTTPException(status_code=409,
                            detail="Invoice sudah menempel di resi lain: " + ", ".join(terpasang))

    cur.execute("SELECT badan_usaha_id FROM invoices WHERE no_invoice = %s", (valid[0],))
    bu_row = cur.fetchone()
    bu_id = bu_row[0] if bu_row else None

    rel = _simpan_berkas(data, file.filename)
    cur.execute(
        "INSERT INTO app_resi (badan_usaha_id, no_resi, kurir, tgl_kirim, resi_path, uploaded_by) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (bu_id, (no_resi or None), (kurir or None), tgl, rel, user.id),
    )
    resi_id = cur.fetchone()[0]
    cur.execute(
        "UPDATE invoices SET resi_id = %s, tahap_dok = 'terkirim' "
        "WHERE no_invoice = ANY(%s) AND resi_id IS NULL",
        (resi_id, valid),
    )
    log_audit(conn, user.id, "buat_resi", "app_resi", resi_id,
              {"invoices": valid, "no_resi": no_resi, "kurir": kurir, "file": file.filename})
    conn.commit()
    # ---- Arsip Paperless (fail-safe): dorong berkas resi ----
    try:
        import paperless_push
        if paperless_push.pc.paperless_aktif():
            _doc_id, _st = paperless_push.arsip_path(
                config.d(rel), "Resi %s" % (no_resi or resi_id), created=tgl)
            if _doc_id and paperless_push.set_doc_id(conn, "app_resi", "id", resi_id,
                                                     "paperless_doc_id", _doc_id):
                conn.commit()
    except Exception as e:
        print(f"  PERINGATAN: resi {resi_id} sukses tapi arsip Paperless gagal: {e}")
    return _resi_detail(conn, resi_id)


@router.patch("/{resi_id}")
async def edit_resi(
    resi_id: int,
    file: Optional[UploadFile] = File(None),
    no_resi: Optional[str] = Form(None),
    kurir: Optional[str] = Form(None),
    tgl_kirim: Optional[str] = Form(None),
    tambah: Optional[str] = Form(None),
    lepas: Optional[str] = Form(None),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Edit resi: ganti berkas &/atau metadata, dan/atau tambah/lepas invoice.
    Lepas -> invoice balik ke gantung (tahap_dok 'terbit')."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_resi WHERE id = %s", (resi_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Resi tidak ditemukan")

    sets, params = [], []
    if no_resi is not None:
        sets.append("no_resi = %s"); params.append(no_resi or None)
    if kurir is not None:
        sets.append("kurir = %s"); params.append(kurir or None)
    if tgl_kirim is not None:
        sets.append("tgl_kirim = %s"); params.append(_parse_tgl(tgl_kirim))

    if file is not None:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Berkas resi kosong")
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Berkas terlalu besar (maks 15 MB)")
        rel = _simpan_berkas(data, file.filename)
        sets.append("resi_path = %s"); params.append(rel)
        sets.append("paperless_doc_id = NULL")

    if sets:
        params.append(resi_id)
        cur.execute("UPDATE app_resi SET " + ", ".join(sets) + " WHERE id = %s", params)

    tambah_list = _parse_no_invoices(tambah or "")
    lepas_list = _parse_no_invoices(lepas or "")

    if tambah_list:
        valid, terpasang, tak_ada = _cek_status(cur, tambah_list)
        if tak_ada:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Invoice tidak ditemukan: " + ", ".join(tak_ada))
        if terpasang:
            cur.execute(
                "SELECT no_invoice FROM invoices WHERE no_invoice = ANY(%s) AND resi_id <> %s",
                (terpasang, resi_id))
            beda = [x[0] for x in cur.fetchall()]
            if beda:
                conn.rollback()
                raise HTTPException(status_code=409,
                                    detail="Invoice sudah di resi lain: " + ", ".join(beda))
        if valid:
            cur.execute(
                "UPDATE invoices SET resi_id = %s, tahap_dok = 'terkirim' "
                "WHERE no_invoice = ANY(%s) AND resi_id IS NULL",
                (resi_id, valid),
            )

    if lepas_list:
        cur.execute(
            "UPDATE invoices SET resi_id = NULL, tahap_dok = 'terbit' "
            "WHERE no_invoice = ANY(%s) AND resi_id = %s",
            (lepas_list, resi_id),
        )

    log_audit(conn, user.id, "edit_resi", "app_resi", resi_id,
              {"tambah": tambah_list, "lepas": lepas_list, "ganti_berkas": file is not None})
    conn.commit()
    return _resi_detail(conn, resi_id)


@router.delete("/{resi_id}")
def hapus_resi(resi_id: int, conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.get_current_user)):
    """Hapus resi -> semua invoice yang menempel BALIK ke Invoice Gantung."""
    cur = conn.cursor()
    cur.execute("SELECT resi_path FROM app_resi WHERE id = %s", (resi_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Resi tidak ditemukan")
    rel = row[0]
    cur.execute(
        "UPDATE invoices SET resi_id = NULL, tahap_dok = 'terbit' "
        "WHERE resi_id = %s RETURNING no_invoice",
        (resi_id,),
    )
    balik = [x[0] for x in cur.fetchall()]
    cur.execute("DELETE FROM app_resi WHERE id = %s", (resi_id,))
    log_audit(conn, user.id, "hapus_resi", "app_resi", resi_id, {"invoice_balik_gantung": balik})
    conn.commit()
    if rel:
        try:
            path = rel if os.path.isabs(rel) else config.d(rel)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"  PERINGATAN: gagal hapus berkas resi {rel}: {e}")
    return {"ok": True, "invoice_balik_gantung": balik}
