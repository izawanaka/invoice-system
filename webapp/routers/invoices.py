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
    if not nomor:
        raise HTTPException(status_code=400, detail="Nomor BAP wajib diisi")

    conn = db_helper.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT no_bap FROM app_bap_nota WHERE no_bap = ANY(%s) "
            "UNION SELECT DISTINCT no_bap FROM bap WHERE no_bap = ANY(%s)",
            (nomor, nomor),
        )
        ada = {r[0] for r in cur.fetchall()}
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
        "i.tgl_bayar, i.no_faktur_pajak, i.paperless_doc_id, v.hari_outstanding, i.seq_no, i.tahap_dok "
        "FROM invoices i "
        "JOIN badan_usaha bu ON bu.id = i.badan_usaha_id "
        "LEFT JOIN v_invoice_outstanding v ON v.no_invoice = i.no_invoice "
        "WHERE 1=1"
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
         hari_outstanding, seq_no, tahap_dok) = r
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
            no_faktur_pajak=no_faktur_pajak, paperless_doc_id=paperless_doc_id,
            tahap_dok=tahap_dok,
        ))
    return out


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
    if kode == "DKP":
        if body.customer:
            payload["customer"] = body.customer
        if body.cust_addr:
            payload["cust_addr"] = body.cust_addr
    # KKS TIDAK menerima customer/cust_addr lewat input -- diambil dari PO tracker
    # itu sendiri (lihat bap_to_invoice_kks.py). Kirim field itu utk KKS tidak
    # berpengaruh (skrip tidak membacanya), jadi sengaja tidak disertakan supaya
    # tidak menyesatkan pemanggil.

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
