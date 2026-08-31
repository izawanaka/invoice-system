"""
mitra.py -- Mitra (Group -> PT -> PO aktif -> Invoice). Master data relasi mitra
usaha + navigasi berjenjang. Ditambah 29 Juli 2026 atas permintaan owner.

Prinsip:
- "Group" mengelompokkan beberapa "PT" (customer). PO ditautkan MANUAL oleh owner
  ke sebuah PT (app_mitra_po, 1 PO -> maks 1 PT). Invoice mengikuti PO (invoices.po_id).
- Tidak menyentuh logika invoice/pajak; hanya lapisan relasi + baca.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import settings  # noqa: F401 -- import pertama, lihat settings.py
import security
from audit import log_audit
from deps import get_db

router = APIRouter(prefix="/mitra", tags=["mitra"])


class GroupIn(BaseModel):
    nama: str = Field(min_length=1)
    alamat: str | None = None
    npwp: str | None = None


class PTIn(BaseModel):
    group_id: int
    nama: str = Field(min_length=1)


class RenameIn(BaseModel):
    nama: str = Field(min_length=1)
    alamat: str | None = None
    npwp: str | None = None


class PTEditIn(BaseModel):
    nama: str = Field(min_length=1)


@router.get("/tree")
def mitra_tree(conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.get_current_user)):
    """Group -> PT (dengan jumlah PO aktif terhubung BERDASAR SITE). Untuk daftar Mitra."""
    cur = conn.cursor()
    cur.execute("SELECT id, nama, alamat, npwp FROM app_mitra_group ORDER BY lower(nama)")
    groups = cur.fetchall()
    cur.execute(
        "SELECT pt.id, pt.group_id, pt.nama, pt.aktif, "
        "(SELECT count(*) FROM purchase_orders p WHERE p.status = 'aktif' "
        " AND p.site IS NOT NULL AND p.site <> '' AND position(lower(p.site) in lower(pt.nama)) > 0) "
        "FROM app_mitra_pt pt ORDER BY lower(pt.nama)"
    )
    by_group = {}
    for pid, gid, nama, aktif, jml in cur.fetchall():
        by_group.setdefault(gid, []).append(
            {"id": pid, "group_id": gid, "nama": nama, "aktif": aktif, "jml_po_aktif": int(jml)}
        )
    return [{"id": gid, "nama": gnama, "alamat": galamat, "npwp": gnpwp, "pt": by_group.get(gid, [])} for gid, gnama, galamat, gnpwp in groups]


@router.post("/groups")
def create_group(body: GroupIn, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE lower(nama) = lower(%s)", (nama,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"Group '{nama}' sudah ada")
    alamat = (body.alamat or "").strip() or None
    npwp = (body.npwp or "").strip() or None
    cur.execute("INSERT INTO app_mitra_group (nama, alamat, npwp) VALUES (%s, %s, %s) RETURNING id",
                (nama, alamat, npwp))
    gid = cur.fetchone()[0]
    log_audit(conn, user.id, "create_mitra_group", "app_mitra_group", gid,
              {"nama": nama, "alamat": alamat, "npwp": npwp})
    conn.commit()
    return {"id": gid, "nama": nama, "alamat": alamat, "npwp": npwp, "pt": []}


@router.post("/pt")
def create_pt(body: PTIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE id = %s", (body.group_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Group tidak ditemukan")
    cur.execute("SELECT id FROM app_mitra_pt WHERE lower(nama) = lower(%s)", (nama,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"PT '{nama}' sudah ada")
    cur.execute("INSERT INTO app_mitra_pt (group_id, nama) VALUES (%s, %s) RETURNING id",
                (body.group_id, nama))
    pid = cur.fetchone()[0]
    log_audit(conn, user.id, "create_mitra_pt", "app_mitra_pt", pid,
              {"nama": nama, "group_id": body.group_id})
    conn.commit()
    return {"id": pid, "group_id": body.group_id, "nama": nama, "aktif": True, "jml_po_aktif": 0}


@router.get("/pt/{pt_id}")
def pt_detail(pt_id: int, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    """Detail PT: PO AKTIF yang site-nya cocok dengan site PT ini (auto, bukan tautan
    manual) + invoice tiap PO."""
    lihat = security.boleh_lihat_pelunasan(user)
    cur = conn.cursor()
    cur.execute(
        "SELECT pt.id, pt.nama, pt.aktif, pt.group_id, g.nama "
        "FROM app_mitra_pt pt LEFT JOIN app_mitra_group g ON g.id = pt.group_id "
        "WHERE pt.id = %s", (pt_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="PT tidak ditemukan")
    pt = {"id": r[0], "nama": r[1], "aktif": r[2], "group_id": r[3], "group_nama": r[4]}

    if pt["nama"]:
        cur.execute(
            "SELECT p.id, p.po_no, bu.kode, p.site, p.customer, p.status, p.satuan, "
            "p.total_qty, p.used_qty, v.sisa_qty, v.pct_used "
            "FROM purchase_orders p JOIN badan_usaha bu ON bu.id = p.badan_usaha_id "
            "LEFT JOIN v_po_sisa v ON v.po_no = p.po_no AND v.kode = bu.kode "
            "WHERE p.status = 'aktif' AND p.site IS NOT NULL AND p.site <> '' AND position(lower(p.site) in lower(%s)) > 0 ORDER BY p.po_no",
            (pt["nama"],))
        po_rows = cur.fetchall()
    else:
        po_rows = []
    po_list = []
    for (poid, po_no, kode, site, customer, status, satuan, tqty, uqty, sisa, pct) in po_rows:
        cur.execute(
            "SELECT i.no_invoice, i.tgl_invoice, i.grand_total, i.status, i.tahap_dok, i.satuan, i.total_qty "
            "FROM invoices i WHERE i.id IN "
            "(SELECT invoice_id FROM invoice_items WHERE po_id = %s "
            " UNION SELECT id FROM invoices WHERE po_id = %s) "
            "ORDER BY i.seq_no DESC NULLS LAST, i.id DESC", (poid, poid))
        invs = [
            {"no_invoice": ir[0], "tgl_invoice": str(ir[1]) if ir[1] else None,
             "grand_total": float(ir[2]) if ir[2] is not None else None,
             "status": (ir[3] if lihat else None), "tahap_dok": ir[4],
             "satuan": ir[5], "total_qty": float(ir[6]) if ir[6] is not None else None}
            for ir in cur.fetchall()
        ]
        sisa_val = sisa if sisa is not None else ((tqty or 0) - (uqty or 0))
        po_list.append({
            "po_id": poid, "po_no": po_no, "badan_usaha_kode": kode, "site": site,
            "customer": customer, "status": status, "satuan": satuan,
            "total_qty": float(tqty) if tqty is not None else None,
            "used_qty": float(uqty) if uqty is not None else None,
            "sisa_qty": float(sisa_val) if sisa_val is not None else None,
            "pct_used": float(pct) if pct is not None else None,
            "invoices": invs,
        })

    return {"pt": pt, "po_terhubung": po_list}


@router.patch("/groups/{group_id}")
def rename_group(group_id: int, body: RenameIn, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE id = %s", (group_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Group tidak ditemukan")
    cur.execute("SELECT id FROM app_mitra_group WHERE lower(nama) = lower(%s) AND id <> %s",
                (nama, group_id))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"Group '{nama}' sudah ada")
    alamat = (body.alamat or "").strip() or None
    npwp = (body.npwp or "").strip() or None
    cur.execute("UPDATE app_mitra_group SET nama = %s, alamat = %s, npwp = %s WHERE id = %s",
                (nama, alamat, npwp, group_id))
    log_audit(conn, user.id, "rename_mitra_group", "app_mitra_group", group_id,
              {"nama": nama, "alamat": alamat, "npwp": npwp})
    conn.commit()
    return {"id": group_id, "nama": nama, "alamat": alamat, "npwp": npwp}


@router.patch("/pt/{pt_id}")
def rename_pt(pt_id: int, body: PTEditIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_pt WHERE id = %s", (pt_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="PT tidak ditemukan")
    cur.execute("SELECT id FROM app_mitra_pt WHERE lower(nama) = lower(%s) AND id <> %s",
                (nama, pt_id))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"PT '{nama}' sudah ada")
    cur.execute("UPDATE app_mitra_pt SET nama = %s WHERE id = %s", (nama, pt_id))
    log_audit(conn, user.id, "rename_mitra_pt", "app_mitra_pt", pt_id, {"nama": nama})
    conn.commit()
    return {"id": pt_id, "nama": nama}


# ======================================================================
# Kontrak (dokumen kontrak payung, dilekatkan per Group) -- ditambah 3 Agu 2026
# Staff & owner boleh unggah/lihat; difilter per badan usaha (DKP/KKS).
# Berkas disimpan lokal (relatif INVOICE_DATA, pola bap_arsip) + best-effort
# dorong ke Paperless. Kolom `ringkasan` diisi Claude (konsep naratif).
# ======================================================================
import os as _os
import uuid as _uuid
from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse
import config as _config
import paperless_push as _pp

_SUB_KONTRAK = "kontrak"


def _kontrak_jalur(rel):
    if not rel:
        return None
    return rel if _os.path.isabs(rel) else _config.d(rel)


def _kontrak_ext(fn):
    return (fn.rsplit(".", 1)[-1].lower() if fn and "." in fn else "bin")


class KontrakOut(BaseModel):
    id: int
    group_id: int
    badan_usaha_kode: str | None = None
    nomor_kontrak: str | None = None
    judul: str | None = None
    tanggal: str | None = None
    masa_berlaku: str | None = None
    nilai: float | None = None
    catatan: str | None = None
    original_filename: str | None = None
    punya_file: bool = False
    paperless_doc_id: str | None = None
    ringkasan: str | None = None
    ringkasan_at: str | None = None
    created_at: str | None = None


_K_COLS = ("id, group_id, badan_usaha_kode, nomor_kontrak, judul, tanggal, masa_berlaku, "
           "nilai, catatan, original_filename, original_path, paperless_doc_id, ringkasan, "
           "ringkasan_at, created_at")


def _kontrak_row(r) -> KontrakOut:
    return KontrakOut(
        id=r[0], group_id=r[1], badan_usaha_kode=r[2], nomor_kontrak=r[3], judul=r[4],
        tanggal=str(r[5]) if r[5] else None, masa_berlaku=r[6],
        nilai=float(r[7]) if r[7] is not None else None, catatan=r[8],
        original_filename=r[9], punya_file=bool(r[10]), paperless_doc_id=r[11],
        ringkasan=r[12], ringkasan_at=str(r[13]) if r[13] else None,
        created_at=str(r[14]) if r[14] else None,
    )


class RingkasanIn(BaseModel):
    ringkasan: str = Field(min_length=1)


@router.get("/groups/{group_id}/kontrak", response_model=list[KontrakOut])
def list_kontrak(group_id: int, badan_usaha_kode: str | None = None,
                 conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.get_current_user)):
    """Daftar kontrak sebuah Group. Filter opsional per badan usaha (DKP/KKS);
    kontrak tanpa badan usaha (NULL) selalu tampil."""
    cur = conn.cursor()
    bu = (badan_usaha_kode or "").upper() or None
    cur.execute(
        f"SELECT {_K_COLS} FROM app_mitra_kontrak "
        "WHERE group_id = %s AND (%s IS NULL OR badan_usaha_kode = %s OR badan_usaha_kode IS NULL) "
        "ORDER BY created_at DESC, id DESC",
        (group_id, bu, bu),
    )
    return [_kontrak_row(r) for r in cur.fetchall()]


@router.post("/groups/{group_id}/kontrak", response_model=KontrakOut, status_code=201)
async def upload_kontrak(group_id: int,
                         file: UploadFile = File(...),
                         badan_usaha_kode: str | None = Form(default=None),
                         nomor_kontrak: str | None = Form(default=None),
                         judul: str | None = Form(default=None),
                         tanggal: str | None = Form(default=None),
                         masa_berlaku: str | None = Form(default=None),
                         nilai: str | None = Form(default=None),
                         catatan: str | None = Form(default=None),
                         conn=Depends(get_db),
                         user: security.CurrentUser = Depends(security.get_current_user)):
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE id = %s", (group_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Group tidak ditemukan")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Berkas kosong")
    folder = _config.d(_SUB_KONTRAK)
    _os.makedirs(folder, exist_ok=True)
    rel = _os.path.join(_SUB_KONTRAK, f"{_uuid.uuid4().hex}.{_kontrak_ext(file.filename)}")
    with open(_config.d(rel), "wb") as f:
        f.write(data)
    bu = (badan_usaha_kode or "").upper() or None
    nilai_num = None
    if nilai:
        try:
            nilai_num = float(str(nilai).replace(".", "").replace(",", "."))
        except ValueError:
            nilai_num = None
    cur.execute(
        "INSERT INTO app_mitra_kontrak (group_id, badan_usaha_kode, nomor_kontrak, judul, "
        "tanggal, masa_berlaku, nilai, catatan, original_filename, original_path, uploaded_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        f"RETURNING {_K_COLS}",
        (group_id, bu, (nomor_kontrak or None), (judul or None),
         (tanggal or None), (masa_berlaku or None), nilai_num, (catatan or None),
         file.filename, rel, user.id),
    )
    row = cur.fetchone()
    log_audit(conn, user.id, "upload_kontrak", "app_mitra_kontrak", row[0],
              {"group_id": group_id, "nomor_kontrak": nomor_kontrak, "badan_usaha_kode": bu})
    conn.commit()
    kid = row[0]
    # best-effort arsip ke Paperless (TIDAK menggagalkan unggah)
    try:
        judul_pl = "Kontrak %s" % (nomor_kontrak or judul or file.filename)
        doc_id, _st = _pp.arsip_path(rel, judul_pl)
        if doc_id:
            _pp.set_doc_id(conn, "app_mitra_kontrak", "id", kid, "paperless_doc_id", doc_id)
            conn.commit()
    except Exception:
        conn.rollback()
    cur.execute(f"SELECT {_K_COLS} FROM app_mitra_kontrak WHERE id = %s", (kid,))
    return _kontrak_row(cur.fetchone())


@router.get("/kontrak/{kontrak_id}/file")
def download_kontrak(kontrak_id: int, conn=Depends(get_db),
                     user: security.CurrentUser = Depends(security.get_current_user)):
    cur = conn.cursor()
    cur.execute("SELECT original_path, original_filename FROM app_mitra_kontrak WHERE id = %s",
                (kontrak_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Kontrak tidak ditemukan")
    path = _kontrak_jalur(r[0])
    if not path or not _os.path.exists(path):
        raise HTTPException(status_code=404, detail="Berkas kontrak tidak ada di server")
    nama = r[1] or _os.path.basename(path)
    return FileResponse(path, filename=nama)


@router.patch("/kontrak/{kontrak_id}/ringkasan", response_model=KontrakOut)
def set_ringkasan_kontrak(kontrak_id: int, body: RingkasanIn, conn=Depends(get_db),
                          user: security.CurrentUser = Depends(security.get_current_user)):
    """Simpan/replace konsep ringkasan naratif (diisi Claude setelah membaca kontrak)."""
    cur = conn.cursor()
    cur.execute("UPDATE app_mitra_kontrak SET ringkasan = %s, ringkasan_at = now() WHERE id = %s",
                (body.ringkasan.strip(), kontrak_id))
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=404, detail="Kontrak tidak ditemukan")
    log_audit(conn, user.id, "set_ringkasan_kontrak", "app_mitra_kontrak", kontrak_id, {})
    conn.commit()
    cur.execute(f"SELECT {_K_COLS} FROM app_mitra_kontrak WHERE id = %s", (kontrak_id,))
    return _kontrak_row(cur.fetchone())


@router.delete("/kontrak/{kontrak_id}")
def hapus_kontrak(kontrak_id: int, conn=Depends(get_db),
                  user: security.CurrentUser = Depends(security.get_current_user)):
    cur = conn.cursor()
    cur.execute("SELECT original_path FROM app_mitra_kontrak WHERE id = %s", (kontrak_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Kontrak tidak ditemukan")
    cur.execute("DELETE FROM app_mitra_kontrak WHERE id = %s", (kontrak_id,))
    log_audit(conn, user.id, "hapus_kontrak", "app_mitra_kontrak", kontrak_id, {})
    conn.commit()
    try:
        p = _kontrak_jalur(r[0])
        if p and _os.path.exists(p):
            _os.remove(p)
    except Exception:
        pass
    return {"ok": True}
