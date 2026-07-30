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
    email: EmailStr
    password: str


class LoginPinStart(BaseModel):
    email: EmailStr
    pin: str = Field(min_length=1)


class LoginOtpVerify(BaseModel):
    email: EmailStr
    kode: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "MeResponse"


class MeResponse(BaseModel):
    id: int
    email: str
    nama: str
    role: str


class ChangePasswordRequest(BaseModel):
    password_lama: str
    password_baru: str = Field(min_length=8)


# ---------- Kelola akun (owner saja) ----------
class UserOut(BaseModel):
    id: int
    email: str
    nama: str
    role: str
    aktif: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    nama: str = Field(min_length=1)
    role: str = Field(default="staff", pattern="^(owner|staff)$")


class UserCreateResult(BaseModel):
    """password_sementara HANYA dikirim di respons ini (saat akun dibuat atau
    di-reset) supaya owner bisa menyalinnya sekali. Tidak pernah bisa dibaca
    ulang lewat endpoint mana pun -- DB hanya menyimpan hash."""
    user: UserOut
    password_sementara: str


class UserUpdateRequest(BaseModel):
    nama: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(owner|staff)$")
    aktif: Optional[bool] = None


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
    no_faktur_pajak: Optional[str] = None
    paperless_doc_id: Optional[str] = None
    # tahap dokumen fisik: terbit/ke_konsultan/faktur_ada/terkirim -- BUKAN pelunasan
    tahap_dok: Optional[str] = None


class InvoicePaymentUpdateRequest(BaseModel):
    status: str = Field(pattern="^(generated|paid)$")
    tgl_bayar: Optional[date] = None


class InvoiceTahapUpdateRequest(BaseModel):
    # tahap dokumen fisik (operasional), TERPISAH dari pelunasan (status).
    tahap: str = Field(pattern="^(terbit|ke_konsultan|faktur_ada|terkirim)$")


class BAPItemIn(BaseModel):
    no_bap: str
    qty: float = Field(gt=0)


class InvoiceGenerateRequest(BaseModel):
    """Body mengikuti KONTRAK INPUT yang sudah ada di bap_to_invoice.py /
    bap_to_invoice_kks.py -- endpoint ini TIDAK menghitung ulang PDF/pajak
    sendiri, hanya menulis file input lalu menjalankan skrip yang sudah teruji
    (31 test PASS, lihat 03_progress_log.md #2) via subprocess."""
    badan_usaha_kode: str = Field(description="DKP atau KKS -- lihat GENERATE_INVOICE_SUPPORTED")
    site: str
    no_bap: str
    inv_date: str = Field(description='Format "DD Bulan YYYY" atau "YYYY-MM-DD"')
    items: List[BAPItemIn] = Field(min_length=1)
    # Hanya dipakai DKP -- KKS mengambil customer dari PO tracker itu sendiri
    # (lihat bap_to_invoice_kks.py: po1.get("customer")).
    customer: Optional[str] = None
    cust_addr: Optional[List[str]] = None

    @model_validator(mode="after")
    def _wajib_customer_utk_dkp(self):
        # bap_to_invoice.py diam-diam JATUH KE DEFAULT ("PT.Itci Hutani Manunggal")
        # kalau customer tidak dikirim -- itu benar utk skrip lama yang dipakai
        # manual, tapi FATAL kalau lolos begitu saja dari web utk site/PO customer
        # lain (invoice PDF resmi bisa salah cetak nama/alamat customer). Jadi
        # DIWAJIBKAN eksplisit di sini utk DKP, supaya gagal cepat, bukan gagal
        # diam-diam di PDF yang sudah terbit.
        if self.badan_usaha_kode.upper() == "DKP" and not (self.customer and self.customer.strip()):
            raise ValueError(
                "customer wajib diisi utk DKP (skrip akan diam-diam memakai default "
                "'PT.Itci Hutani Manunggal' kalau tidak diisi -- berbahaya utk site/PO lain)"
            )
        return self


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
