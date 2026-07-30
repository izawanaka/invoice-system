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


class PTIn(BaseModel):
    group_id: int
    nama: str = Field(min_length=1)
    site: str = Field(min_length=1)


class RenameIn(BaseModel):
    nama: str = Field(min_length=1)


class PTEditIn(BaseModel):
    nama: str = Field(min_length=1)
    site: str = Field(min_length=1)


@router.get("/tree")
def mitra_tree(conn=Depends(get_db),
               user: security.CurrentUser = Depends(security.get_current_user)):
    """Group -> PT (dengan jumlah PO aktif terhubung BERDASAR SITE). Untuk daftar Mitra."""
    cur = conn.cursor()
    cur.execute("SELECT id, nama FROM app_mitra_group ORDER BY lower(nama)")
    groups = cur.fetchall()
    cur.execute(
        "SELECT pt.id, pt.group_id, pt.nama, pt.aktif, pt.site, "
        "(SELECT count(*) FROM purchase_orders p WHERE p.status = 'aktif' "
        " AND pt.site IS NOT NULL AND lower(p.site) = lower(pt.site)) "
        "FROM app_mitra_pt pt ORDER BY lower(pt.nama)"
    )
    by_group = {}
    for pid, gid, nama, aktif, site, jml in cur.fetchall():
        by_group.setdefault(gid, []).append(
            {"id": pid, "group_id": gid, "nama": nama, "aktif": aktif, "site": site, "jml_po_aktif": int(jml)}
        )
    return [{"id": gid, "nama": gnama, "pt": by_group.get(gid, [])} for gid, gnama in groups]


@router.post("/groups")
def create_group(body: GroupIn, conn=Depends(get_db),
                 user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE lower(nama) = lower(%s)", (nama,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"Group '{nama}' sudah ada")
    cur.execute("INSERT INTO app_mitra_group (nama) VALUES (%s) RETURNING id", (nama,))
    gid = cur.fetchone()[0]
    log_audit(conn, user.id, "create_mitra_group", "app_mitra_group", gid, {"nama": nama})
    conn.commit()
    return {"id": gid, "nama": nama, "pt": []}


@router.post("/pt")
def create_pt(body: PTIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_group WHERE id = %s", (body.group_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Group tidak ditemukan")
    site = body.site.strip()
    cur.execute("SELECT id FROM app_mitra_pt WHERE lower(nama) = lower(%s)", (nama,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"PT '{nama}' sudah ada")
    cur.execute("INSERT INTO app_mitra_pt (group_id, nama, site) VALUES (%s, %s, %s) RETURNING id",
                (body.group_id, nama, site))
    pid = cur.fetchone()[0]
    log_audit(conn, user.id, "create_mitra_pt", "app_mitra_pt", pid,
              {"nama": nama, "group_id": body.group_id, "site": site})
    conn.commit()
    return {"id": pid, "group_id": body.group_id, "nama": nama, "aktif": True, "site": site, "jml_po_aktif": 0}


@router.get("/pt/{pt_id}")
def pt_detail(pt_id: int, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    """Detail PT: PO AKTIF yang site-nya cocok dengan site PT ini (auto, bukan tautan
    manual) + invoice tiap PO."""
    lihat = security.boleh_lihat_pelunasan(user)
    cur = conn.cursor()
    cur.execute(
        "SELECT pt.id, pt.nama, pt.aktif, pt.group_id, g.nama, pt.site "
        "FROM app_mitra_pt pt LEFT JOIN app_mitra_group g ON g.id = pt.group_id "
        "WHERE pt.id = %s", (pt_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="PT tidak ditemukan")
    pt = {"id": r[0], "nama": r[1], "aktif": r[2], "group_id": r[3], "group_nama": r[4], "site": r[5]}

    if pt["site"]:
        cur.execute(
            "SELECT p.id, p.po_no, bu.kode, p.site, p.customer, p.status, p.satuan, "
            "p.total_qty, p.used_qty, v.sisa_qty, v.pct_used "
            "FROM purchase_orders p JOIN badan_usaha bu ON bu.id = p.badan_usaha_id "
            "LEFT JOIN v_po_sisa v ON v.po_no = p.po_no AND v.kode = bu.kode "
            "WHERE p.status = 'aktif' AND lower(p.site) = lower(%s) ORDER BY p.po_no",
            (pt["site"],))
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
    cur.execute("UPDATE app_mitra_group SET nama = %s WHERE id = %s", (nama, group_id))
    log_audit(conn, user.id, "rename_mitra_group", "app_mitra_group", group_id, {"nama": nama})
    conn.commit()
    return {"id": group_id, "nama": nama}


@router.patch("/pt/{pt_id}")
def rename_pt(pt_id: int, body: PTEditIn, conn=Depends(get_db),
              user: security.CurrentUser = Depends(security.get_current_user)):
    nama = body.nama.strip()
    site = body.site.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_mitra_pt WHERE id = %s", (pt_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="PT tidak ditemukan")
    cur.execute("SELECT id FROM app_mitra_pt WHERE lower(nama) = lower(%s) AND id <> %s",
                (nama, pt_id))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"PT '{nama}' sudah ada")
    cur.execute("UPDATE app_mitra_pt SET nama = %s, site = %s WHERE id = %s", (nama, site, pt_id))
    log_audit(conn, user.id, "rename_mitra_pt", "app_mitra_pt", pt_id, {"nama": nama, "site": site})
    conn.commit()
    return {"id": pt_id, "nama": nama, "site": site}
