"""
routers/pembayaran.py -- pembayaran invoice dengan CICILAN (owner-only).

Model: tiap pembayaran = 1 baris `app_invoice_bayar` (nominal + tgl). Status
invoice diturunkan dari total dibayar vs grand_total:
  total = 0                 -> 'generated' (belum bayar)
  0 < total < grand_total   -> 'sebagian'  (cicilan)
  total >= grand_total      -> 'paid'      (lunas)
invoices.status & tgl_bayar disinkronkan tiap ada perubahan (tgl_bayar diisi
tanggal cicilan TERAKHIR saat lunas; NULL selain itu).

Pelunasan = wewenang OWNER (keputusan owner 28 Jul 2026). SEMUA endpoint di sini
require_owner -- staf tidak boleh melihat/mengubah pelunasan.

Prefix /pembayaran (beda dari /invoices yang route-nya greedy).
  GET    /pembayaran/{no_invoice}     -> ringkasan + daftar cicilan
  POST   /pembayaran/{no_invoice}     -> catat 1 cicilan (atau lunaskan sisa)
  DELETE /pembayaran/hapus/{bayar_id} -> hapus 1 baris cicilan (koreksi)
"""
from datetime import date as date_cls
from typing import Optional

import settings  # noqa: F401
import security
from audit import log_audit
from deps import get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/pembayaran", tags=["pembayaran"])


def _ringkas(cur, no_invoice: str) -> dict:
    cur.execute("SELECT grand_total FROM invoices WHERE no_invoice = %s", (no_invoice,))
    inv = cur.fetchone()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice %s tidak ditemukan" % no_invoice)
    grand = float(inv[0]) if inv[0] is not None else 0.0
    cur.execute("SELECT COALESCE(SUM(nominal), 0) FROM app_invoice_bayar WHERE no_invoice = %s", (no_invoice,))
    dibayar = float(cur.fetchone()[0] or 0)
    sisa = round(grand - dibayar, 2)
    if dibayar <= 0.0001:
        status = "generated"
    elif dibayar + 0.5 >= grand:
        status = "paid"
    else:
        status = "sebagian"
    cur.execute(
        "SELECT id, nominal, tgl_bayar, catatan, created_at FROM app_invoice_bayar "
        "WHERE no_invoice = %s ORDER BY tgl_bayar, id",
        (no_invoice,),
    )
    daftar = [
        {
            "id": r[0],
            "nominal": float(r[1]),
            "tgl_bayar": r[2].isoformat() if r[2] else None,
            "catatan": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in cur.fetchall()
    ]
    return {
        "no_invoice": no_invoice,
        "grand_total": grand,
        "total_dibayar": dibayar,
        "sisa": sisa if sisa > 0 else 0.0,
        "status": status,
        "daftar": daftar,
    }


def _sinkron_status(cur, no_invoice: str, status: str) -> None:
    if status == "paid":
        cur.execute("SELECT MAX(tgl_bayar) FROM app_invoice_bayar WHERE no_invoice = %s", (no_invoice,))
        tgl = cur.fetchone()[0] or date_cls.today()
        cur.execute("UPDATE invoices SET status = 'paid', tgl_bayar = %s WHERE no_invoice = %s", (tgl, no_invoice))
    elif status == "sebagian":
        cur.execute("UPDATE invoices SET status = 'sebagian', tgl_bayar = NULL WHERE no_invoice = %s", (no_invoice,))
    else:
        cur.execute("UPDATE invoices SET status = 'generated', tgl_bayar = NULL WHERE no_invoice = %s", (no_invoice,))


@router.get("/{no_invoice:path}")
def lihat_pembayaran(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    return _ringkas(conn.cursor(), no_invoice)


class BayarReq(BaseModel):
    nominal: Optional[float] = None
    tgl_bayar: Optional[str] = None
    catatan: Optional[str] = None
    lunaskan: bool = False


@router.post("/{no_invoice:path}")
def catat_pembayaran(
    no_invoice: str,
    body: BayarReq,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    cur = conn.cursor()
    r0 = _ringkas(cur, no_invoice)
    if body.lunaskan:
        nominal = r0["sisa"]
        if nominal <= 0:
            raise HTTPException(status_code=400, detail="Invoice sudah lunas / tidak ada sisa tagihan")
    else:
        if body.nominal is None or float(body.nominal) <= 0:
            raise HTTPException(status_code=400, detail="Nominal pembayaran harus lebih dari 0")
        nominal = round(float(body.nominal), 2)
    tgl = body.tgl_bayar or date_cls.today().isoformat()
    cur.execute(
        "INSERT INTO app_invoice_bayar (no_invoice, nominal, tgl_bayar, catatan, created_by) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (no_invoice, nominal, tgl, (body.catatan or None), user.id),
    )
    pid = cur.fetchone()[0]
    r = _ringkas(cur, no_invoice)
    _sinkron_status(cur, no_invoice, r["status"])
    log_audit(conn, user.id, "catat_pembayaran", "app_invoice_bayar", pid,
              {"no_invoice": no_invoice, "nominal": nominal, "lunaskan": body.lunaskan})
    conn.commit()
    return r


@router.delete("/hapus/{bayar_id}")
def hapus_pembayaran(
    bayar_id: int,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.require_owner),
):
    cur = conn.cursor()
    cur.execute("SELECT no_invoice FROM app_invoice_bayar WHERE id = %s", (bayar_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pembayaran tidak ditemukan")
    no_invoice = row[0]
    cur.execute("DELETE FROM app_invoice_bayar WHERE id = %s", (bayar_id,))
    r = _ringkas(cur, no_invoice)
    _sinkron_status(cur, no_invoice, r["status"])
    log_audit(conn, user.id, "hapus_pembayaran", "app_invoice_bayar", bayar_id, {"no_invoice": no_invoice})
    conn.commit()
    return r
