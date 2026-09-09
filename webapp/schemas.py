"""
schemas.py -- model Pydantic request/response. Nama field mengikuti nama kolom
Postgres asli (lihat 02_db_schema.md) supaya tidak ada lapisan terjemahan yang
bisa jadi sumber salah baca data finansial.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


# ---------- Auth ----------
class LoginRequest(BaseModel):
    """Login pakai USERNAME (keputusan owner 5 Sep 2026: "input-nya cuma username,
    di belakangnya tetap email", gaya Cantabile). Email TIDAK diterima di sini.
    Jalur PIN+OTP (LoginPinStart/LoginOtpVerify) dihapus -- endpointnya 410."""
    username: str = Field(min_length=1, max_length=64)
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "MeResponse"


class MeResponse(BaseModel):
    id: int
    email: str
    nama: str
    role: str
    username: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    password_lama: str
    password_baru: str = Field(min_length=8)


# ---------- Kelola akun (owner saja) ----------
class UserOut(BaseModel):
    id: int
    email: str
    username: str
    nama: str
    role: str
    aktif: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    # 5 Sep 2026: izin Google (diatur owner) & bukti Google (diisi sistem saat sukses)
    login_via_google: bool = False
    google_terbukti_pada: Optional[datetime] = None
    # Tiket sandi sekali pakai: true = sandi awal masih bisa dipakai sekali.
    password_aktif: bool = False


# PABRIK_B1_9SEP2026: peran admin & kepala (workspace Pabrik) boleh dibuat/diubah owner.
class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30)
    nama: str = Field(min_length=1)
    role: str = Field(default="staff", pattern="^(owner|staff|viewer|admin|kepala)$")
    # Password awal boleh diinput owner (5 Sep 2026); kosong -> sistem buat acak.
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    login_via_google: bool = False


class UserCreateResult(BaseModel):
    """password_sementara HANYA dikirim di respons ini (saat akun dibuat atau
    di-reset) supaya owner bisa menyalinnya sekali. Tidak pernah bisa dibaca
    ulang lewat endpoint mana pun -- DB hanya menyimpan hash."""
    user: UserOut
    password_sementara: str


class UserUpdateRequest(BaseModel):
    nama: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(owner|staff|viewer|admin|kepala)$")
    aktif: Optional[bool] = None
    username: Optional[str] = Field(default=None, min_length=3, max_length=30)
    login_via_google: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    """Body opsional utk POST /users/{id}/reset-password. password kosong ->
    sistem membuat acak (perilaku lama)."""
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


# ---------- Badan usaha ----------
class BadanUsahaOut(BaseModel):
    id: int
    kode: str
    nama: str
    jenis: Optional[str] = None
    sektor: Optional[str] = None
    is_pkp: bool
    tarif_ppn: Optional[float] = None
    aktif: bool


# ---------- PO ----------
class POSisaOut(BaseModel):
    """Mencerminkan view v_po_sisa -- JANGAN hitung ulang pct_used/sisa_qty di
    Python, view sudah menghitungnya dari Postgres (sumber kebenaran, I5)."""
    kode: str
    po_no: str
    site: Optional[str] = None
    customer: Optional[str] = None
    satuan: Optional[str] = None
    total_qty: float
    used_qty: float
    sisa_qty: float
    harga_satuan: Optional[float] = None
    pct_used: float
    status: str
    warning_threshold_pct: Optional[float] = None
    is_warning: bool = False


class POCreateRequest(BaseModel):
    badan_usaha_kode: str
    po_no: str
    site: str
    customer: str
    total_qty: float = Field(gt=0)
    satuan: str
    harga_satuan: float = Field(ge=0)
    cust_addr: Optional[List[str]] = None
    payment_terms: Optional[str] = None
    tgl_masuk: Optional[date] = None
    catatan: Optional[str] = None
    warning_threshold_pct: Optional[float] = None


class POOcrItemOut(BaseModel):
    nama_item: Optional[str] = None
    kuantitas: Optional[float] = None
    harga_satuan: Optional[float] = None
    subtotal: Optional[float] = None


class POOcrOut(BaseModel):
    """Hasil ekstraksi OCR PO (POST /po/ocr) -- PRATINJAU SAJA, belum tersimpan
    ke DB. Field yang tidak yakin dibaca model dikembalikan null (lihat
    webapp/po_ocr.py) supaya UI memaksa user mengisi/mengonfirmasi manual
    (aturan owner: "selalu tanya ke user sebelum lanjut")."""
    po_no: Optional[str] = None
    customer: Optional[str] = None
    tanggal: Optional[str] = None
    items: List[POOcrItemOut] = []
    total_qty: Optional[float] = None
    satuan: Optional[str] = None
    harga_satuan: Optional[float] = None
    total_nilai: Optional[float] = None
    site_saran: Optional[str] = None
    site_status: str = "ask"
    catatan_keraguan: Optional[str] = None
    po_no_sudah_ada: Optional[bool] = None


class POOut(BaseModel):
    id: int
    badan_usaha_kode: str
    po_no: str
    site: Optional[str] = None
    customer: Optional[str] = None
    total_qty: float
    used_qty: float
    satuan: Optional[str] = None
    harga_satuan: Optional[float] = None
    status: str
    tgl_masuk: Optional[date] = None
    catatan: Optional[str] = None
    warning_threshold_pct: Optional[float] = None
    created_at: Optional[datetime] = None


# ---------- BAP ----------
class BAPOut(BaseModel):
    id: int
    badan_usaha_kode: str
    no_bap: Optional[str] = None
    site: Optional[str] = None
    tgl_bap: Optional[date] = None
    total_qty: float
    satuan: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------- PO detail: invoice yang memotong PO ----------
class POInvoiceCutOut(BaseModel):
    """Satu baris pemotongan PO oleh sebuah invoice (dari invoice_items.po_id).
    Satu invoice bisa muncul >1 baris kalau memotong PO ini lewat beberapa BAP."""
    no_invoice: str
    tgl_invoice: Optional[date] = None
    status: Optional[str] = None  # null utk staf -- lihat InvoiceOut.status
    no_bap: Optional[str] = None
    qty: float
    satuan: Optional[str] = None
    subtotal: Optional[float] = None


class PODocOut(BaseModel):
    """Scan PO asli dari customer (diunggah owner) -- dipakai paket cetak."""
    id: int
    po_no: str
    original_filename: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------- BAP nota cetak (unggahan web) ----------
class BAPNotaOut(BaseModel):
    id: int
    badan_usaha_kode: Optional[str] = None
    jenis: Optional[str] = None
    no_bap: Optional[str] = None
    site: Optional[str] = None
    tanggal: Optional[str] = None
    qty_kg: Optional[float] = None
    qty_m3: Optional[float] = None
    confidence: Optional[str] = None
    original_filename: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    sumber: Optional[str] = None   # "web" atau "telegram"
    mitra_pt_id: Optional[int] = None
    mitra_pt_nama: Optional[str] = None
    deteksi_status: Optional[str] = None
    dipakai_invoice: Optional[str] = None


# ---------- Invoice ----------
class InvoiceOut(BaseModel):
    id: int
    badan_usaha_kode: str
    no_invoice: str
    seq_no: Optional[int] = None
    tgl_invoice: Optional[date] = None
    no_po: Optional[str] = None
    site: Optional[str] = None
    customer: Optional[str] = None
    total_qty: float
    satuan: Optional[str] = None
    sub_total: Optional[float] = None
    dpp: Optional[float] = None
    ppn: Optional[float] = None
    grand_total: Optional[float] = None
    # status/tgl_bayar/hari_outstanding = informasi PELUNASAN. Untuk akun staf
    # ketiganya dikirim null (keputusan owner 28 Jul 2026: staf boleh apa saja
    # KECUALI melihat pelunasan invoice) -- lihat routers/invoices.py.
    # Karena itu tipenya Optional, bukan str wajib.
    status: Optional[str] = None
    tgl_bayar: Optional[date] = None
    hari_outstanding: Optional[int] = None
    # total cicilan terbayar (SUM app_invoice_bayar) -- pelunasan, owner-only; None utk staf
    total_dibayar: Optional[float] = None
    no_faktur_pajak: Optional[str] = None
    paperless_doc_id: Optional[str] = None
    # tahap dokumen fisik: terbit/ke_konsultan/faktur_ada/terkirim -- BUKAN pelunasan
    tahap_dok: Optional[str] = None
    # invoice batal (Vault baru) -- NULL = aktif, terisi = dibatalkan (qty PO &
    # BAP terkait sudah dikembalikan otomatis, lihat routers/invoices.py batalkan_invoice)
    dibatalkan_at: Optional[datetime] = None


class InvoicePaymentUpdateRequest(BaseModel):
    status: str = Field(pattern="^(generated|paid)$")
    tgl_bayar: Optional[date] = None


class InvoiceTahapUpdateRequest(BaseModel):
    # tahap dokumen fisik (operasional), TERPISAH dari pelunasan (status).
    tahap: str = Field(pattern="^(terbit|ke_konsultan|faktur_ada|terkirim)$")


class BAPItemIn(BaseModel):
    no_bap: str
    qty: float = Field(gt=0)


MAKS_BAP_PER_INVOICE = 4


class InvoiceGenerateRequest(BaseModel):
    """Body mengikuti KONTRAK INPUT yang sudah ada di bap_to_invoice.py /
    bap_to_invoice_kks.py -- endpoint ini TIDAK menghitung ulang PDF/pajak
    sendiri, hanya menulis file input lalu menjalankan skrip yang sudah teruji
    (31 test PASS, lihat 03_progress_log.md #2) via subprocess."""
    badan_usaha_kode: str = Field(description="DKP atau KKS -- lihat GENERATE_INVOICE_SUPPORTED")
    site: str
    no_bap: str
    inv_date: str = Field(description='Format "DD Bulan YYYY" atau "YYYY-MM-DD"')
    items: List[BAPItemIn] = Field(min_length=1, max_length=MAKS_BAP_PER_INVOICE)
    # customer/cust_addr TIDAK lagi diterima dari web utk DKP MAUPUN KKS (31 Jul
    # 2026 -- owner: "desain DKP dan KKS itu 1 dan baku, yang berbeda hanya isinya
    # saja, itupun admin dan owner yang isi"). Kedua skrip (bap_to_invoice.py /
    # _kks.py) sekarang SAMA-SAMA ambil customer dari PO tracker (po1.get("customer")),
    # diisi admin/owner sekali saat PO didaftarkan (Tambah PO / OCR PO), bukan
    # diketik ulang tiap generate invoice. Field dihapus dari kontrak request.
    # BAP boleh TANPA nomor (nomor BAP tidak dicetak di invoice). Identifikasi &
    # anti-dobel-tagih utk BAP tanpa nomor lewat id baris unggahan app_bap_nota.
    nota_ids: Optional[List[int]] = None


class InvoicePreviewLine(BaseModel):
    urutan: int
    deskripsi: str
    qty: float
    harga: float
    jumlah: float


class InvoicePreviewPOSplit(BaseModel):
    po_no: str
    qty_dipotong: float
    sisa_sebelum: float
    sisa_sesudah: float


class InvoicePreviewResult(BaseModel):
    """Pratinjau HANYA-BACA (tidak menulis apa pun) sebelum owner/admin klik
    Terbitkan -- lihat routers/invoices.py:preview_invoice utk penjelasan
    kenapa ini bisa berbeda tipis dari hasil generate yang sebenarnya kalau
    ada invoice lain generate di antara preview dan klik Terbitkan."""
    inv_no_preview: str
    site: str
    no_po: str
    items: List[InvoicePreviewLine]
    po_splits: List[InvoicePreviewPOSplit]
    sub_total: float
    dpp: float
    ppn: float
    grand_total: float
    catatan: str


class InvoiceGenerateResult(BaseModel):
    status: str
    inv_no: Optional[str] = None
    message: Optional[str] = None
    site: Optional[str] = None
    no_po: Optional[str] = None
    sub_total: Optional[float] = None
    grand_total: Optional[float] = None
    pdf_path: Optional[str] = None
    raw_stdout: Optional[str] = None


# ---------- Paperless ----------
class PaperlessUploadResult(BaseModel):
    ok: bool
    task_id: Optional[str] = None
    status: Optional[str] = None
    document_id: Optional[str] = None
    message: Optional[str] = None


LoginResponse.model_rebuild()


# ---------- Faktur Pajak (Fase 3, 30 Jul 2026) ----------
class FakturPajakCandidateInvoice(BaseModel):
    """Kandidat Invoice utk dipilih user di dropdown -- TIDAK PERNAH auto-link,
    pilihan invoice_id selalu aksi eksplisit user (lihat routers/faktur_pajak.py)."""
    invoice_id: int
    no_invoice: str
    customer: Optional[str] = None
    grand_total: Optional[float] = None
    tgl_invoice: Optional[date] = None
    dpp: Optional[float] = None
    ppn: Optional[float] = None


class FakturPajakOcrOut(BaseModel):
    """Hasil ekstraksi OCR Faktur Pajak (POST /faktur-pajak/ocr) -- PRATINJAU
    SAJA, belum tersimpan ke DB. Field yang tidak yakin dibaca model
    dikembalikan null (lihat webapp/faktur_ocr.py) supaya UI memaksa user
    mengisi/mengonfirmasi manual (aturan owner: "selalu tanya ke user sebelum
    lanjut")."""
    nomor_faktur: Optional[str] = None
    tanggal_faktur: Optional[str] = None
    nama_pembeli: Optional[str] = None
    referensi_invoice: Optional[str] = None
    dpp: Optional[float] = None
    ppn: Optional[float] = None
    total: Optional[float] = None
    catatan_keraguan: Optional[str] = None
    kandidat_invoice: List[FakturPajakCandidateInvoice] = []


class FakturPajakOut(BaseModel):
    id: int
    badan_usaha_kode: str
    invoice_id: int
    no_invoice: str
    nomor_faktur: Optional[str] = None
    tanggal_faktur: Optional[str] = None
    dpp: Optional[float] = None
    ppn: Optional[float] = None
    total: Optional[float] = None
    original_filename: Optional[str] = None
    catatan_keraguan: Optional[str] = None
    # 'matched' | 'mismatch' | 'pending' -- lihat routers/faktur_pajak.py utk
    # logika cross-check (validation.py pattern, toleransi Rp 25).
    status_cocok: str = "pending"
    catatan_selisih: Optional[str] = None
    created_at: Optional[datetime] = None
