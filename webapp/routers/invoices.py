import json
import os
import subprocess
import threading
import uuid
from datetime import date as date_cls
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

import settings  # noqa: F401 -- import pertama, lihat settings.py
import config
import db_helper
import print_packet
import schemas
import security
import validation
from audit import log_audit
from deps import get_db
from settings import GENERATE_INVOICE_SUPPORTED

router = APIRouter(prefix="/invoices", tags=["invoices"])

# bap_to_invoice.py / bap_to_invoice_kks.py membaca INPUT dari path TETAP
# (config.d("bap_input.json") / "bap_input_kks.json") -- bukan argumen CLI.
# Kalau dua request generate jalan bersamaan mereka akan REBUTAN file yang sama.
# Fase 1: volume pemakaian rendah (1 tim kecil), jadi cukup diserialisasi dgn
# lock proses ini. Kalau nanti dipakai banyak orang sekaligus, ini perlu diganti
# jadi antrian per-badan-usaha yang sesungguhnya.
_generate_lock = threading.Lock()

_TRACKER_REFRESH_INV = {
    "DKP": {"file": config.PO_FILE, "qty": "total_kg", "used": "used_kg", "price": "rp_kg", "unit": "kg"},
    "KKS": {"file": config.PO_FILE_KKS, "qty": "total_m3", "used": "used_m3", "price": "rp_m3", "unit": "m3"},
}

_INV_NO_FILE = {
    "DKP": config.d("last_invoice_no.txt"),
    "KKS": config.d("last_invoice_no_kks.txt"),
}

_ENTITY = {
    "DKP": {
        "badan_usaha_id": 4,
        "script": os.path.join(config.BASE, "bap_to_invoice.py"),
        "input_file": config.d("bap_input.json"),
        "qty_key": "qty_kg",
    },
    "KKS": {
        "badan_usaha_id": 5,
        "script": os.path.join(config.BASE, "bap_to_invoice_kks.py"),
        "input_file": config.d("bap_input_kks.json"),
        "qty_key": "qty_m3",
    },
}


def _wajib_bap_sudah_ada(body: schemas.InvoiceGenerateRequest):
    """ATURAN #1 (keputusan owner 28 Jul 2026): invoice HANYA boleh terbit kalau
    BAP-nya sudah ada di sistem.

    Kenapa perlu dipaksa di sini: baris tabel `bap` justru dibuat oleh
    invoice_dkp.py/_kks.py PADA SAAT invoice terbit (INSERT INTO bap ...), jadi
    tanpa pengecekan ini nomor BAP apa pun bisa diketik dan invoice tetap jadi --
    urutan "BAP dulu baru invoice" cuma bergantung disiplin manual.

    Sumber BAP yang diakui:
      - app_bap_nota : BAP yang diunggah lewat web ATAU lewat Telegram
                     (ocr_doc.py memanggil bap_arsip.daftarkan_dari_telegram),
      - bap          : BAP yang sudah tercatat dari invoice sebelumnya.
    Koneksi DB dibuka sendiri (bukan dependency) supaya endpoint generate tetap
    tidak memegang koneksi selama subprocess berjalan lama.
    """
    nomor = [it.no_bap.strip() for it in body.items if it.no_bap and it.no_bap.strip()]
    nota_ids = list(body.nota_ids or [])
    # BAP boleh TANPA nomor -- yang WAJIB adalah bukti BAP sudah diunggah: entah
    # nomornya tercatat (app_bap_nota/bap), ATAU ada baris unggahan app_bap_nota
    # (nota_ids) yang mengacu ke berkas BAP yang diunggah.
    if not nomor and not nota_ids:
        raise HTTPException(status_code=400, detail="Unggah BAP dulu -- belum ada BAP (bernomor maupun tanpa nomor) yang diunggah untuk invoice ini.")

    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        ada = set()
        if nomor:
            cur.execute(
                "SELECT DISTINCT no_bap FROM app_bap_nota WHERE no_bap = ANY(%s) "
                "UNION SELECT DISTINCT no_bap FROM bap WHERE no_bap = ANY(%s)",
                (nomor, nomor),
            )
            ada = {r[0] for r in cur.fetchall()}
        nota_ada = set()
        if nota_ids:
            cur.execute("SELECT id FROM app_bap_nota WHERE id = ANY(%s)", (nota_ids,))
            nota_ada = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    belum = [n for n in nomor if n not in ada]
    if belum:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invoice belum bisa terbit: BAP {', '.join(belum)} belum ada di sistem. "
                f"Unggah dulu BAP-nya (foto/PDF) di menu BAP, baru terbitkan invoice."
            ),
        )
    if [i for i in nota_ids if i not in nota_ada]:
        raise HTTPException(status_code=400, detail="Sebagian BAP terunggah tidak ditemukan lagi (mungkin sudah dihapus) -- unggah ulang BAP-nya.")


def _tolak_bap_sudah_dipakai(body: schemas.InvoiceGenerateRequest):
    """Fase 1 -- cegah dobel-invoice dari BAP yang sama. Baris tabel `bap` dibuat
    oleh invoice_dkp.py/_kks.py PADA SAAT invoice sebelumnya terbit (lihat
    docstring _wajib_bap_sudah_ada di atas). Tidak ada UNIQUE constraint di
    kolom bap.no_bap, jadi tanpa pengecekan ini nomor BAP yang sama bisa
    dipakai lagi utk invoice KEDUA tanpa error apa pun sama sekali (risiko
    dobel tagih customer utk pekerjaan yang sama). Dipanggil di preview
    (deteksi dini) dan generate (penjaga terakhir sebelum subprocess jalan).
    """
    nomor = [it.no_bap.strip() for it in body.items if it.no_bap and it.no_bap.strip()]
    nota_ids = list(body.nota_ids or [])
    if not nomor and not nota_ids:
        return
    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        dipakai = []
        if nomor:
            cur.execute("SELECT DISTINCT no_bap FROM bap WHERE no_bap = ANY(%s)", (nomor,))
            dipakai = sorted({r[0] for r in cur.fetchall()})
        nota_dipakai = []
        if nota_ids:
            cur.execute("SELECT DISTINCT dipakai_invoice FROM app_bap_nota WHERE id = ANY(%s) AND dipakai_invoice IS NOT NULL", (nota_ids,))
            nota_dipakai = sorted({r[0] for r in cur.fetchall()})
    finally:
        conn.close()
    if dipakai:
        raise HTTPException(
            status_code=409,
            detail=(
                f"BAP {', '.join(dipakai)} sudah pernah dipakai untuk invoice "
                f"sebelumnya -- tidak boleh dipakai lagi utk invoice baru (mencegah "
                f"dobel tagih ke customer untuk pekerjaan yang sama)."
            ),
        )
    if nota_dipakai:
        raise HTTPException(
            status_code=409,
            detail=(
                f"BAP yang diunggah ini sudah pernah dipakai untuk invoice "
                f"{', '.join(nota_dipakai)} -- tidak boleh dipakai lagi (mencegah dobel tagih)."
            ),
        )


@router.get("", response_model=List[schemas.InvoiceOut])
def list_invoices(
    badan_usaha_kode: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    sql = (
        "SELECT i.id, bu.kode, i.no_invoice, i.tgl_invoice, i.no_po, i.site, i.customer, "
        "i.total_qty, i.satuan, i.sub_total, i.dpp, i.ppn, i.grand_total, i.status, "
        "i.tgl_bayar, i.no_faktur_pajak, i.paperless_doc_id, v.hari_outstanding, i.seq_no, i.tahap_dok, "
        "i.dibatalkan_at, pb.total_dibayar "
        "FROM invoices i "
        "JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "LEFT JOIN v_invoice_outstanding v ON v.no_invoice = i.no_invoice "
        "LEFT JOIN (SELECT no_invoice, SUM(nominal) AS total_dibayar FROM app_invoice_bayar "
        "GROUP BY no_invoice) pb ON pb.no_invoice = i.no_invoice "
        "WHERE i.dibatalkan_at IS NULL"  # invoice yang dibatalkan TIDAK muncul di Rekap/Gantung/Dashboard
    )
    lihat_pelunasan = security.boleh_lihat_pelunasan(user)

    params = []
    if badan_usaha_kode:
        sql += " AND bu.kode = %s"
        params.append(badan_usaha_kode.upper())
    if status_filter:
        # Menyaring berdasarkan status bayar = cara tidak langsung utk mengetahui
        # invoice mana yang sudah lunas. Kalau cuma field-nya yang dikosongkan
        # tapi filter tetap boleh, staf masih bisa menyimpulkan jawabannya dari
        # daftar hasil. Jadi filternya ikut ditutup.
        if not lihat_pelunasan:
            raise HTTPException(
                status_code=403,
                detail="Akun staf tidak berwenang melihat status pelunasan invoice",
            )
        sql += " AND i.status = %s"
        params.append(status_filter)
    # Permintaan owner (28 Jul): nomor invoice SELALU tampil berurutan.
    # seq_no = nomor urut per badan usaha (sumber counter penomoran), jadi urutkan
    # berdasarkan itu, terbaru di atas -- bukan tgl_invoice (bisa sama/kosong).
    sql += " ORDER BY bu.kode, i.seq_no DESC NULLS LAST, i.id DESC"

    cur = conn.cursor()
    cur.execute(sql, params)
    out = []
    for r in cur.fetchall():
        (iid, kode, no_invoice, tgl_invoice, no_po, site, customer, total_qty, satuan,
         sub_total, dpp, ppn, grand_total, st, tgl_bayar, no_faktur_pajak, paperless_doc_id,
         hari_outstanding, seq_no, tahap_dok, dibatalkan_at, total_dibayar) = r
        out.append(schemas.InvoiceOut(
            id=iid, badan_usaha_kode=kode, no_invoice=no_invoice, seq_no=seq_no,
            tgl_invoice=tgl_invoice,
            no_po=no_po, site=site, customer=customer, total_qty=float(total_qty),
            satuan=satuan, sub_total=float(sub_total) if sub_total is not None else None,
            dpp=float(dpp) if dpp is not None else None, ppn=float(ppn) if ppn is not None else None,
            grand_total=float(grand_total) if grand_total is not None else None,
            # Pelunasan disembunyikan dari staf DI SISI SERVER (bukan cuma di UI).
            status=st if lihat_pelunasan else None,
            tgl_bayar=tgl_bayar if lihat_pelunasan else None,
            hari_outstanding=hari_outstanding if lihat_pelunasan else None,
            # total cicilan terbayar (fitur centang & jumlah otomatis di Rekap Invoice).
            # Informasi PELUNASAN -> owner-only, staf dikirim None (keputusan owner 28 Jul).
            total_dibayar=(float(total_dibayar) if total_dibayar is not None else 0.0)
            if lihat_pelunasan else None,
            no_faktur_pajak=no_faktur_pajak, paperless_doc_id=paperless_doc_id,
            tahap_dok=tahap_dok, dibatalkan_at=dibatalkan_at,
        ))
    return out


# ---------- Batal Invoice (Invoice Gantung) ----------
# Keputusan owner (31 Jul 2026): tombol "Batal Invoice" di Invoice Gantung.
# - Qty PO yang terpotong invoice ini DIKEMBALIKAN otomatis (used_qty -= qty per
#   invoice_items.po_id), supaya PO langsung bisa dipakai lagi utk invoice baru.
# - BAP yang terpakai (app_bap_nota.dipakai_invoice) DILEPAS jadi NULL lagi.
# - Baris ledger `bap` (dedup nomor BAP, lihat _tolak_bap_sudah_dipakai) utk
#   no_bap yang dipakai invoice ini DIHAPUS supaya nomor BAP itu bisa dipakai lagi.
# - Invoice TIDAK dihapus (jejak audit tetap ada) -- ditandai dibatalkan_at/oleh,
#   lalu otomatis hilang dari GET /invoices (Rekap/Gantung/Dashboard semua pakai
#   endpoint ini). Owner & staf SAMA-SAMA boleh (keputusan owner 31 Jul 2026) --
#   tidak seperti status pelunasan yang owner-only.
@router.post("/{no_invoice:path}/batal")
def batalkan_invoice(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    cur = conn.cursor()
    cur.execute(
        "SELECT i.id, i.badan_usaha_id, bu.kode, i.dibatalkan_at, i.seq_no, i.no_faktur_pajak "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    invoice_id, badan_usaha_id, kode, sudah_batal, seq_no, no_faktur_pajak = row
    if sudah_batal:
        raise HTTPException(status_code=409, detail=f"Invoice {no_invoice} sudah dibatalkan sebelumnya")

    # 0) Cek apakah invoice ini yang PALING BARU (seq_no tertinggi) utk badan
    #    usaha ini (termasuk invoice lain yang sudah batal) DAN belum punya
    #    faktur pajak terupload. Hanya kombinasi ini yang aman utk dihapus
    #    total + direklaim nomornya -- lihat langkah 4 di bawah utk detail.
    cur.execute("SELECT COALESCE(MAX(seq_no), 0) FROM invoices WHERE badan_usaha_id = %s", (badan_usaha_id,))
    max_seq = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM faktur_pajak WHERE invoice_id = %s", (invoice_id,))
    ada_faktur_pajak = cur.fetchone()[0] > 0
    nomor_direklaim = (
        seq_no is not None and int(seq_no) == int(max_seq)
        and not no_faktur_pajak and not ada_faktur_pajak
    )

    # 1) Kembalikan qty PO yang terpotong invoice ini (per baris invoice_items,
    #    supaya invoice split >1 PO ikut benar semua -- lihat catatan di
    #    invoice_dkp.py soal kenapa harus per invoice_items, bukan invoices.po_id).
    cur.execute(
        "SELECT po_id, qty FROM invoice_items WHERE invoice_id = %s AND po_id IS NOT NULL",
        (invoice_id,),
    )
    po_dikembalikan = []
    for po_id, qty in cur.fetchall():
        cur.execute(
            "UPDATE purchase_orders SET used_qty = GREATEST(used_qty - %s, 0) WHERE id = %s",
            (qty, po_id),
        )
        po_dikembalikan.append({"po_id": po_id, "qty": float(qty)})

    # 2) Lepas BAP terunggah (app_bap_nota) supaya bisa dipakai ulang.
    cur.execute(
        "UPDATE app_bap_nota SET dipakai_invoice = NULL WHERE dipakai_invoice = %s",
        (no_invoice,),
    )
    bap_nota_dilepas = cur.rowcount

    # 3) Hapus ledger `bap` (dedup nomor BAP) utk no_bap yang dipakai invoice ini --
    #    dicocokkan lewat invoice_items.no_bap (kolom yang SAMA dipakai
    #    _tolak_bap_sudah_dipakai utk menolak invoice baru), bukan field gabungan
    #    top-level yang dikirim ke skrip saat generate.
    cur.execute(
        "SELECT DISTINCT no_bap FROM invoice_items WHERE invoice_id = %s AND no_bap IS NOT NULL AND no_bap <> ''",
        (invoice_id,),
    )
    no_baps = [r[0] for r in cur.fetchall()]
    if no_baps:
        cur.execute("DELETE FROM bap WHERE badan_usaha_id = %s AND no_bap = ANY(%s)", (badan_usaha_id, no_baps))

    # 4) Kalau invoice ini paling baru & belum ada faktur pajak: HAPUS TOTAL
    #    barisnya (invoice_items ikut cascade) supaya no_invoice-nya benar2
    #    bebas, lalu mundurkan counter file (last_invoice_no*.txt) satu
    #    langkah -- supaya next_inv_no() menghasilkan nomor yang SAMA lagi
    #    pada percobaan reissue berikutnya. Kalau BUKAN yang paling baru (ada
    #    invoice lain setelahnya) atau sudah ada faktur pajak: tetap
    #    soft-cancel seperti biasa -- nomor jadi gap permanen, tidak bisa
    #    direklaim tanpa merusak skema penomoran MAX-based / dokumen pajak
    #    yang sudah terbit. LIHAT DESIGN.md sebelum mengubah bagian ini.
    if nomor_direklaim:
        cur.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
        inv_no_file = _INV_NO_FILE.get(kode)
        if inv_no_file:
            try:
                with open(inv_no_file) as f:
                    isi_sekarang = int(f.read().strip())
                if isi_sekarang == int(seq_no):
                    with open(inv_no_file, "w") as f:
                        f.write(str(int(seq_no) - 1).zfill(3))
            except Exception as e:
                print(f"  PERINGATAN: invoice {no_invoice} dihapus tapi gagal mundurkan counter file: {e}")
    else:
        cur.execute(
            "UPDATE invoices SET dibatalkan_at = now(), dibatalkan_oleh = %s WHERE id = %s",
            (user.id, invoice_id),
        )
    conn.commit()

    log_audit(conn, user.id, "batalkan_invoice", "invoices", no_invoice,
              {"po_dikembalikan": po_dikembalikan, "bap_nota_dilepas": bap_nota_dilepas,
               "bap_ledger_dihapus": no_baps, "nomor_direklaim": nomor_direklaim})
    conn.commit()

    # 5) Sinkronkan po_tracker*.json (cache baca turunan Postgres, I8) supaya
    #    bap_to_invoice.py/_kks.py langsung melihat qty PO yang sudah kembali.
    if kode in _TRACKER_REFRESH_INV:
        t = _TRACKER_REFRESH_INV[kode]
        try:
            db_helper.refresh_po_tracker_json(conn, badan_usaha_id, t["file"], t["qty"], t["used"], t["price"], t["unit"])
        except Exception as e:
            print(f"  PERINGATAN: invoice {no_invoice} dibatalkan tapi gagal refresh po_tracker: {e}")

    return {
        "status": "ok",
        "no_invoice": no_invoice,
        "po_dikembalikan": po_dikembalikan,
        "bap_nota_dilepas": bap_nota_dilepas,
        "bap_ledger_dihapus": no_baps,
        "nomor_direklaim": nomor_direklaim,
    }


@router.patch("/{no_invoice:path}/payment", response_model=schemas.InvoiceOut)
def update_payment_status(
    no_invoice: str,
    body: schemas.InvoicePaymentUpdateRequest,
    conn=Depends(get_db),
    # Pelunasan = wewenang Owner. Staf boleh input & terbitkan invoice, tapi
    # tidak boleh menandai lunas (dan tidak boleh melihatnya -- lihat
    # security.boleh_lihat_pelunasan).
    user: security.CurrentUser = Depends(security.require_owner),
):
    """UPDATE terarah WHERE no_invoice=..., assert rowcount==1 -- pola yang sama
    dipakai skrip invoice existing utk perubahan data finansial (lihat
    01_architecture_flow.md Alur B). TIDAK ada query bebas / bulk update."""
    tgl_bayar = body.tgl_bayar
    if body.status == "paid" and tgl_bayar is None:
        tgl_bayar = date_cls.today()
    if body.status == "generated":
        tgl_bayar = None  # kembali ke belum bayar -> kosongkan tanggal

    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET status = %s, tgl_bayar = %s WHERE no_invoice = %s "
        "RETURNING id",
        (body.status, tgl_bayar, no_invoice),
    )
    row = cur.fetchone()
    if row is None:
        conn.rollback()
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")

    log_audit(conn, user.id, "update_payment", "invoices", no_invoice,
               {"status": body.status, "tgl_bayar": str(tgl_bayar) if tgl_bayar else None})
    conn.commit()

    cur.execute(
        "SELECT i.id, bu.kode, i.no_invoice, i.tgl_invoice, i.no_po, i.site, i.customer, "
        "i.total_qty, i.satuan, i.sub_total, i.dpp, i.ppn, i.grand_total, i.status, "
        "i.tgl_bayar, i.no_faktur_pajak, i.paperless_doc_id, i.tahap_dok "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    r = cur.fetchone()
    return schemas.InvoiceOut(
        id=r[0], badan_usaha_kode=r[1], no_invoice=r[2], tgl_invoice=r[3], no_po=r[4],
        site=r[5], customer=r[6], total_qty=float(r[7]), satuan=r[8],
        sub_total=float(r[9]) if r[9] is not None else None,
        dpp=float(r[10]) if r[10] is not None else None,
        ppn=float(r[11]) if r[11] is not None else None,
        grand_total=float(r[12]) if r[12] is not None else None,
        status=r[13], tgl_bayar=r[14], no_faktur_pajak=r[15], paperless_doc_id=r[16],
        tahap_dok=r[17],
    )




@router.post("/preview", response_model=schemas.InvoicePreviewResult)
def preview_invoice(
    body: schemas.InvoiceGenerateRequest,
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Pratinjau HANYA-BACA sebelum admin klik Terbitkan (wizard "Terbit Invoice").
    TIDAK menulis file input, TIDAK menjalankan subprocess, TIDAK commit apa pun ke DB
    -- memakai fungsi PEMBACAAN (get_po_list/alokasi_po/next_inv_no) yang SAMA PERSIS
    dengan yang dipakai bap_to_invoice.py/_kks.py yang sesungguhnya, supaya angka
    preview konsisten dengan hasil generate nyata.

    PENTING (beri tahu di response.catatan): ini estimasi berdasarkan kondisi PO SAAT
    preview dipanggil. Kalau ada invoice lain yang generate di antara preview dan klik
    Terbitkan, PO bisa berubah -- generate yang sesungguhnya SELALU menghitung ulang
    fresh saat itu juga (satu-satunya sumber kebenaran), jadi angka final bisa berbeda
    tipis dari yang tampil di preview.
    """
    kode = body.badan_usaha_kode.upper()
    if kode not in GENERATE_INVOICE_SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Preview utk '{kode}' belum didukung dari web -- Fase 1 hanya DKP & KKS.",
        )

    _wajib_bap_sudah_ada(body)
    _tolak_bap_sudah_dipakai(body)

    qty_list = [it.qty for it in body.items]

    if kode == "DKP":
        import bap_to_invoice as _biv
        qf, uf, pf = "total_kg", "used_kg", "rp_kg"
    else:
        import bap_to_invoice_kks as _biv
        qf, uf, pf = "total_m3", "used_m3", "rp_m3"

    po_list = _biv.get_po_list(body.site)
    if not po_list:
        raise HTTPException(status_code=400, detail=f"Tidak ada PO aktif utk site '{body.site}'.")

    try:
        items, po_splits, order_ref = _biv.alokasi_po(qty_list, po_list, qf, uf, pf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inv_no, _next_no = _biv.next_inv_no(body.site, body.inv_date)

    sub_total = sum(it[2] * it[3] for it in items)
    if kode == "DKP":
        # code_pajak.py (ROUND_HALF_UP) cuma ada di lingkungan yang sudah dipatch
        # (produksi) -- fallback ke rumus mentah kalau belum ada (sandbox saat ini),
        # supaya preview TETAP konsisten dgn apa pun yang invoice_dkp.py di lingkungan
        # itu benar-benar lakukan (jangan sampai preview "lebih akurat" dari generate-nya).
        try:
            import code_pajak
            dpp = float(code_pajak.dpp_nilai_lain(sub_total))
            ppn = float(code_pajak.ppn(dpp))
        except ImportError:
            dpp = sub_total * 11 / 12
            ppn = dpp * 0.12
        grand = sub_total + ppn
    else:
        dpp = sub_total  # KKS non-PKP: konvensi seragam dpp = sub_total (5 Agu 2026)
        ppn = 0.0
        grand = sub_total

    by_po = {p["po_no"]: p for p in po_list}
    splits_out = []
    for po_no, qty_potong in po_splits:
        p = by_po.get(po_no, {})
        sisa_sebelum = float(p.get(qf, 0)) - float(p.get(uf, 0) or 0)
        splits_out.append(schemas.InvoicePreviewPOSplit(
            po_no=po_no,
            qty_dipotong=round(qty_potong, 4),
            sisa_sebelum=round(sisa_sebelum, 4),
            sisa_sesudah=round(sisa_sebelum - qty_potong, 4),
        ))

    items_out = [
        schemas.InvoicePreviewLine(
            urutan=it[0], deskripsi=it[1], qty=it[2], harga=it[3], jumlah=it[2] * it[3],
        )
        for it in items
    ]

    # Fase 1 -- cross-check pasif: sub_total di atas seharusnya SELALU sama dgn
    # jumlah tiap baris qty x harga (dihitung dari data yang sama), jadi kalau
    # sampai beda berarti ada bug logika di atas -- gagal cepat drpd terbitkan
    # angka yang salah ke owner.
    ok_calc, expected_calc, diff_calc, pesan_calc = validation.check_items_total_consistency(
        [(it[2], it[3]) for it in items], sub_total,
    )
    if not ok_calc:
        raise HTTPException(
            status_code=500,
            detail=f"Inkonsistensi internal saat preview invoice: {pesan_calc}",
        )

    return schemas.InvoicePreviewResult(
        inv_no_preview=inv_no,
        site=body.site,
        no_po=order_ref,
        items=items_out,
        po_splits=splits_out,
        sub_total=sub_total,
        dpp=dpp,
        ppn=ppn,
        grand_total=grand,
        catatan=(
            "Pratinjau berdasarkan kondisi PO saat ini. Nomor invoice & alokasi PO "
            "dihitung ULANG saat Anda klik Terbitkan -- kalau ada invoice lain generate "
            "di antara waktu ini, angka final bisa sedikit berbeda dari yang tampil di sini."
        ),
    )


@router.post("/generate", response_model=schemas.InvoiceGenerateResult)
def generate_invoice(
    body: schemas.InvoiceGenerateRequest,
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """TIDAK menghitung PDF/pajak sendiri. Menulis file input dengan kontrak yang
    SAMA PERSIS dengan yang sudah dipakai bot Telegram, lalu menjalankan
    bap_to_invoice.py / bap_to_invoice_kks.py apa adanya (skrip yang sudah lolos
    31 test, lihat 03_progress_log.md #2) via subprocess -- SATU-SATUNYA jalur
    penulisan invoice, supaya logika pajak/alokasi PO/transaksi atomik tidak
    pernah diduplikasi/diimplementasikan ulang di sini (DESIGN.md: invoice_dkp.py
    /_kks.py 'Jantung sistem', hanya diubah dgn alasan kuat + test hijau)."""
    kode = body.badan_usaha_kode.upper()
    if kode not in GENERATE_INVOICE_SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Generate invoice utk '{kode}' belum didukung dari web -- Fase 1 "
                f"hanya DKP & KKS (skrip PDF khusus utk SSM/TBS/GBU belum dibuat). "
                f"Lihat 05_web_platform_plan.md."
            ),
        )
    ent = _ENTITY[kode]

    _wajib_bap_sudah_ada(body)
    _tolak_bap_sudah_dipakai(body)

    total_qty = sum(it.qty for it in body.items)
    payload = {
        "site": body.site,
        "no_bap": body.no_bap,
        "inv_date": body.inv_date,
        ent["qty_key"]: total_qty,
        "items": [
            {ent["qty_key"]: it.qty, "no_bap": it.no_bap} for it in body.items
        ],
    }
    # customer/cust_addr TIDAK diterima dari web (baik DKP maupun KKS, 31 Jul 2026
    # -- lihat catatan di schemas.py InvoiceGenerateRequest). Kedua skrip mengambil
    # customer dari PO tracker itu sendiri (po1.get("customer")), diisi admin/owner
    # sekali saat PO didaftarkan, bukan diketik ulang tiap generate invoice.

    acquired = _generate_lock.acquire(timeout=30)
    if not acquired:
        raise HTTPException(status_code=503, detail="Sedang ada proses generate invoice lain, coba lagi sesaat")
    try:
        with open(ent["input_file"], "w") as f:
            json.dump(payload, f, ensure_ascii=False)

        env = {
            **os.environ,
            "INVOICE_ENV": "sandbox",
            "INVOICE_DATA": config.DATA,
            "INVOICE_OUT": config.OUTPUT_DIR_DKP,
            "INVOICE_OUT_KKS": config.OUTPUT_DIR_KKS,
            "INVOICE_DB": config.DB_NAME or "bisnis_sandbox",
            "INVOICE_SMB": "0",
        }
        result = subprocess.run(
            ["python3", ent["script"]], capture_output=True, text=True, env=env, cwd=config.BASE,
        )
    finally:
        _generate_lock.release()

    stdout = (result.stdout or "").strip()
    parsed = None
    for line in stdout.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except Exception:
                pass

    if result.returncode != 0 or parsed is None or parsed.get("status") != "success":
        message = (parsed or {}).get("message") if parsed else None
        if not message:
            message = (result.stderr or stdout or "Penyebab tidak diketahui")[:500]
        return schemas.InvoiceGenerateResult(status="error", message=message, raw_stdout=stdout)

    # Fase 1 -- cross-check PASIF (warning-only, tidak membatalkan apa pun):
    # invoice SUDAH commit di dalam subprocess di atas, jadi di sini kita hanya
    # mengecek ulang bhw sub_total/grand_total yang dikembalikan skrip taat pada
    # qty x harga per baris & rumus pajak code_pajak.py yang sama -- kalau ada
    # yang beda berarti ada penyimpangan (mis. code_pajak berubah tanpa
    # sinkron), dicatat ke log server supaya owner tahu, TANPA mengubah data
    # yang sudah terlanjur tersimpan (itu di luar cakupan Fase 1).
    try:
        items_parsed = parsed.get("items") or []
        sub_total_parsed = parsed.get("sub_total")
        grand_total_parsed = parsed.get("grand_total")
        if items_parsed and sub_total_parsed is not None:
            ok_sub, exp_sub, diff_sub, pesan_sub = validation.check_items_total_consistency(
                [(i.get("qty"), i.get("harga")) for i in items_parsed], sub_total_parsed,
            )
            if not ok_sub:
                print(f"  PERINGATAN Fase1 [{parsed.get('inv_no')}]: {pesan_sub}")
        if sub_total_parsed is not None and grand_total_parsed is not None:
            if kode == "DKP":
                try:
                    import code_pajak
                    dpp_exp = float(code_pajak.dpp_nilai_lain(sub_total_parsed))
                    ppn_exp = float(code_pajak.ppn(dpp_exp))
                    grand_exp = sub_total_parsed + ppn_exp
                except ImportError:
                    grand_exp = sub_total_parsed + (sub_total_parsed * 11 / 12) * 0.12
            else:
                grand_exp = sub_total_parsed
            ok_grand, _exp, diff_grand, pesan_grand = validation.check_calc_consistency(
                1.0, grand_exp, grand_total_parsed,
            )
            if not ok_grand:
                print(f"  PERINGATAN Fase1 [{parsed.get('inv_no')}]: grand_total tidak konsisten -- {pesan_grand}")
    except Exception as e:
        print(f"  PERINGATAN Fase1: gagal menjalankan cross-check pasca-generate: {e}")

    # Audit log dicatat di koneksi TERPISAH -- bap_to_invoice.py/invoice_dkp.py
    # sudah commit transaksinya sendiri di dalam subprocess sebelum baris ini
    # berjalan, jadi ini murni jejak "siapa memicu generate", bukan bagian dari
    # transaksi invoice itu sendiri.
    try:
        audit_conn = db_helper.get_conn()
        try:
            log_audit(audit_conn, user.id, "generate_invoice", "invoices", parsed.get("inv_no"),
                       {"badan_usaha_kode": kode, "site": body.site, "no_bap": body.no_bap})
            audit_conn.commit()
        finally:
            audit_conn.close()
    except Exception as e:
        print(f"  PERINGATAN: invoice {parsed.get('inv_no')} sukses tapi audit log gagal: {e}")

    # Tandai BAP terunggah (app_bap_nota) sbg SUDAH DIPAKAI utk invoice ini --
    # inilah pencegah dobel-tagih utk BAP TANPA nomor (yang tak bisa didedup lewat
    # tabel `bap`). Koneksi terpisah, setelah invoice sukses.
    if body.nota_ids:
        try:
            m_conn = db_helper.get_conn()
            try:
                mc = m_conn.cursor()
                mc.execute("UPDATE app_bap_nota SET dipakai_invoice = %s WHERE id = ANY(%s) AND dipakai_invoice IS NULL",
                           (parsed.get("inv_no"), list(body.nota_ids)))
                m_conn.commit()
            finally:
                m_conn.close()
        except Exception as e:
            print(f"  PERINGATAN: invoice {parsed.get('inv_no')} sukses tapi tandai BAP dipakai gagal: {e}")

    # ---- Arsip Paperless (fail-safe, decouple PC): Invoice PDF + BAP nota ----
    # TIDAK pernah menggagalkan generate; Paperless cermin, bukan sumber kebenaran.
    try:
        import paperless_push
        if paperless_push.pc.paperless_aktif():
            _inv_no = parsed.get("inv_no")
            _pl_conn = db_helper.get_conn()
            try:
                _doc_id, _st = paperless_push.arsip_path(
                    parsed.get("pdf_path"), "Invoice %s" % _inv_no, created=body.inv_date)
                if _doc_id:
                    paperless_push.set_doc_id(_pl_conn, "invoices", "no_invoice", _inv_no,
                                              "paperless_inv_id", _doc_id)
                if body.nota_ids:
                    import bap_arsip
                    _bc = _pl_conn.cursor()
                    _bc.execute("SELECT id, no_bap, nota_pdf_path FROM app_bap_nota WHERE id = ANY(%s)",
                                (list(body.nota_ids),))
                    for _nid, _no_bap, _npath in _bc.fetchall():
                        _real = bap_arsip.jalur(_npath) if _npath else None
                        _bdoc, _bst = paperless_push.arsip_path(_real, "BAP %s" % (_no_bap or _nid))
                        if _bdoc:
                            paperless_push.set_doc_id(_pl_conn, "app_bap_nota", "id", _nid,
                                                      "paperless_doc_id", _bdoc)
                _pl_conn.commit()
            finally:
                _pl_conn.close()
    except Exception as e:
        print(f"  PERINGATAN: invoice {parsed.get('inv_no')} sukses tapi arsip Paperless gagal: {e}")

    return schemas.InvoiceGenerateResult(
        status="success",
        inv_no=parsed.get("inv_no"),
        site=parsed.get("site"),
        no_po=parsed.get("no_po"),
        sub_total=parsed.get("sub_total"),
        grand_total=parsed.get("grand_total"),
        pdf_path=parsed.get("pdf_path"),
        raw_stdout=stdout,
    )


# ---------- Paket cetak (Invoice + PO + Faktur Pajak + BAP jadi 1 PDF) ----------

@router.get("/{no_invoice:path}/paket-cetak/info")
def info_paket_cetak(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Checklist isi paket SEBELUM dicetak -- dipakai halaman preview supaya owner
    tahu bagian mana yang belum lengkap (mis. scan PO belum diunggah)."""
    info = print_packet.kumpulkan_bagian(conn, no_invoice)
    if not info.get("ok"):
        raise HTTPException(status_code=404, detail=info.get("message"))
    bagian = []
    for key in print_packet.URUTAN_BAGIAN:
        b = info["bagian"][key]
        bagian.append({
            "kode": key,
            "judul": b["judul"],
            "jumlah_berkas": len(b["berkas"]),
            "berkas": [x["label"] for x in b["berkas"]],
            "masalah": b["hilang"],
            "lengkap": bool(b["berkas"]) and not b["hilang"],
        })
    return {
        "no_invoice": no_invoice,
        "invoice": info["invoice"],
        "po_list": [p["po_no"] for p in info["po_list"]],
        "bap_list": info["bap_list"],
        "bagian": bagian,
        "siap_cetak": all(x["lengkap"] for x in bagian),
    }


@router.get("/{no_invoice:path}/paket-cetak")
def unduh_paket_cetak(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """PDF gabungan siap review/cetak. Dibuat ulang setiap kali diminta supaya
    selalu mencerminkan berkas terbaru (mis. scan PO yang baru diunggah)."""
    try:
        data, _info = print_packet.bangun_pdf(conn, no_invoice)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyusun paket cetak: {e}")

    nama = f"paket_cetak_{no_invoice.replace('/', '_')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nama}"'},
    )


@router.patch("/{no_invoice:path}/tahap", response_model=schemas.InvoiceOut)
def update_tahap_dok(
    no_invoice: str,
    body: schemas.InvoiceTahapUpdateRequest,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Ubah tahap dokumen fisik invoice: terbit -> ke_konsultan -> faktur_ada ->
    terkirim. Ini OPERASIONAL (bukan pelunasan) -- staf boleh (Aturan Bisnis #11).
    UPDATE terarah WHERE no_invoice=..., assert rowcount==1 + audit log."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET tahap_dok = %s WHERE no_invoice = %s RETURNING id",
        (body.tahap, no_invoice),
    )
    row = cur.fetchone()
    if row is None:
        conn.rollback()
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    if cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=500, detail="rowcount != 1, dibatalkan demi keamanan data")
    log_audit(conn, user.id, "update_tahap_dok", "invoices", no_invoice, {"tahap": body.tahap})
    conn.commit()

    lihat_pelunasan = security.boleh_lihat_pelunasan(user)
    cur.execute(
        "SELECT i.id, bu.kode, i.no_invoice, i.tgl_invoice, i.no_po, i.site, i.customer, "
        "i.total_qty, i.satuan, i.sub_total, i.dpp, i.ppn, i.grand_total, i.status, "
        "i.tgl_bayar, i.no_faktur_pajak, i.paperless_doc_id, i.tahap_dok, i.seq_no "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    r = cur.fetchone()
    return schemas.InvoiceOut(
        id=r[0], badan_usaha_kode=r[1], no_invoice=r[2], seq_no=r[18], tgl_invoice=r[3],
        no_po=r[4], site=r[5], customer=r[6], total_qty=float(r[7]), satuan=r[8],
        sub_total=float(r[9]) if r[9] is not None else None,
        dpp=float(r[10]) if r[10] is not None else None,
        ppn=float(r[11]) if r[11] is not None else None,
        grand_total=float(r[12]) if r[12] is not None else None,
        status=r[13] if lihat_pelunasan else None,
        tgl_bayar=r[14] if lihat_pelunasan else None,
        no_faktur_pajak=r[15], paperless_doc_id=r[16], tahap_dok=r[17],
    )


# ---------- Bukti resi pengiriman (unggahan admin = penanda 'terkirim') ----------

@router.post("/{no_invoice:path}/resi", response_model=schemas.InvoiceOut)
async def upload_resi(
    no_invoice: str,
    file: UploadFile = File(...),
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Admin unggah bukti resi pengiriman. Unggahan = penanda tahap 'terkirim'
    (pola sama dgn faktur pajak, Vault #12/#19). Berkas diarsipkan lokal ke
    INVOICE_DATA/resi/ (path relatif disimpan di invoices.resi_path)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File terlalu besar (maks 15 MB)")

    folder = config.d("resi")
    os.makedirs(folder, exist_ok=True)
    ext = (file.filename.rsplit(".", 1)[-1].lower()
           if file.filename and "." in file.filename else "bin")
    rel = os.path.join("resi", f"resi_{uuid.uuid4().hex}.{ext}")
    with open(config.d(rel), "wb") as f:
        f.write(data)

    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET resi_path = %s, tahap_dok = 'terkirim' WHERE no_invoice = %s RETURNING id",
        (rel, no_invoice),
    )
    row = cur.fetchone()
    if row is None or cur.rowcount != 1:
        conn.rollback()
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    log_audit(conn, user.id, "upload_resi", "invoices", no_invoice, {"file": file.filename})
    conn.commit()

    lihat = security.boleh_lihat_pelunasan(user)
    cur.execute(
        "SELECT i.id, bu.kode, i.no_invoice, i.tgl_invoice, i.no_po, i.site, i.customer, "
        "i.total_qty, i.satuan, i.sub_total, i.dpp, i.ppn, i.grand_total, i.status, "
        "i.tgl_bayar, i.no_faktur_pajak, i.paperless_doc_id, i.tahap_dok, i.seq_no "
        "FROM invoices i JOIN badan_usaha bu ON bu.id = i.badan_usaha_id WHERE i.no_invoice = %s",
        (no_invoice,),
    )
    r = cur.fetchone()
    return schemas.InvoiceOut(
        id=r[0], badan_usaha_kode=r[1], no_invoice=r[2], seq_no=r[18], tgl_invoice=r[3],
        no_po=r[4], site=r[5], customer=r[6], total_qty=float(r[7]), satuan=r[8],
        sub_total=float(r[9]) if r[9] is not None else None,
        dpp=float(r[10]) if r[10] is not None else None,
        ppn=float(r[11]) if r[11] is not None else None,
        grand_total=float(r[12]) if r[12] is not None else None,
        status=r[13] if lihat else None,
        tgl_bayar=r[14] if lihat else None,
        no_faktur_pajak=r[15], paperless_doc_id=r[16], tahap_dok=r[17],
    )


@router.get("/{no_invoice:path}/pdf")
def download_invoice_pdf(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Unduh PDF INVOICE ASLI saja (belum digabung PO/Faktur Pajak/BAP) --
    utk invoice yang masih gantung (PO/FP/BAP belum tentu lengkap) tapi invoice-nya
    sendiri sudah harus bisa dikirim/dicetak duluan. Beda dari /paket-cetak yang
    menggabung semua dokumen jadi satu."""
    cur = conn.cursor()
    cur.execute("SELECT pdf_path FROM invoices WHERE no_invoice = %s", (no_invoice,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    path = print_packet._cari_berkas(row[0])
    if not path:
        raise HTTPException(
            status_code=404,
            detail="PDF invoice tidak ditemukan di server (tercatat: %s). Coba cek lewat menu "
                   "'Cek Dokumen (Paperless)' kalau sudah pernah terarsip." % (row[0] or '-'),
        )
    nama = f"Invoice_{no_invoice.replace('/', '_')}.pdf"
    return FileResponse(path, filename=nama, media_type="application/pdf")


@router.get("/{no_invoice:path}/resi/file")
def download_resi(
    no_invoice: str,
    conn=Depends(get_db),
    user: security.CurrentUser = Depends(security.get_current_user),
):
    """Unduh bukti resi yang sudah diunggah (utk dilihat admin)."""
    cur = conn.cursor()
    cur.execute("SELECT resi_path FROM invoices WHERE no_invoice = %s", (no_invoice,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Invoice {no_invoice} tidak ditemukan")
    rel = row[0]
    if not rel:
        raise HTTPException(status_code=404, detail="Bukti resi belum diunggah")
    path = rel if os.path.isabs(rel) else config.d(rel)
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="File resi tidak ada lagi di server")
    nama = f"resi_{no_invoice.replace('/', '_')}.{rel.rsplit('.', 1)[-1]}"
    return FileResponse(path, filename=nama)
