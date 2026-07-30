from typing import List

from fastapi import APIRouter, Depends

import settings  # noqa: F401 -- import pertama, lihat settings.py
import schemas
import security
from deps import get_db
from settings import DASHBOARD_BADAN_USAHA

router = APIRouter(prefix="/badan-usaha", tags=["badan-usaha"])


@router.get("", response_model=List[schemas.BadanUsahaOut])
def list_badan_usaha(
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """HANYA entitas ranah cocopeat (DKP & KKS) -- keputusan owner 28 Jul 2026:
    TBS/SSMJ/GBU tidak ada hubungan dgn sistem ini (lihat settings.py)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, kode, nama, jenis, sektor, is_pkp, tarif_ppn, aktif "
        "FROM badan_usaha WHERE kode = ANY(%s) ORDER BY kode",
        (sorted(DASHBOARD_BADAN_USAHA),),
    )
    rows = cur.fetchall()
    return [
        schemas.BadanUsahaOut(
            id=r[0], kode=r[1], nama=r[2], jenis=r[3], sektor=r[4],
            is_pkp=r[5], tarif_ppn=float(r[6]) if r[6] is not None else None, aktif=r[7],
        )
        for r in rows
    ]
