// Tipe-tipe ini mengikuti persis model Pydantic di backend (webapp/schemas.py)
// supaya tidak ada lapisan terjemahan yang bisa jadi sumber salah baca data
// finansial. Lihat 02_db_schema.md / 05_web_platform_plan.md di Project.

export type Role = "owner" | "staff";

export interface MeResponse {
  id: number;
  email: string;
  nama: string;
  role: Role;
}

// Kelola akun (halaman Pengaturan). Mengikuti webapp/schemas.py.
export interface UserOut {
  id: number;
  email: string;
  nama: string;
  role: Role;
  aktif: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
}

export interface UserCreateRequest {
  email: string;
  nama: string;
  role: Role;
}

export interface UserUpdateRequest {
  nama?: string;
  role?: Role;
  aktif?: boolean;
}

// password_sementara hanya ada di respons pembuatan/reset akun -- tidak bisa
// dibaca ulang lewat endpoint mana pun.
export interface UserCreateResult {
  user: UserOut;
  password_sementara: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: MeResponse;
}

export interface BadanUsahaOut {
  id: number;
  kode: string;
  nama: string;
  jenis: string | null;
  sektor: string | null;
  is_pkp: boolean;
  tarif_ppn: number | null;
  aktif: boolean;
}

export interface POSisaOut {
  kode: string;
  po_no: string;
  site: string | null;
  customer: string | null;
  satuan: string | null;
  total_qty: number;
  used_qty: number;
  sisa_qty: number;
  harga_satuan: number | null;
  pct_used: number;
  status: string;
  warning_threshold_pct: number | null;
  is_warning: boolean;
}

export interface POCreateRequest {
  badan_usaha_kode: string;
  po_no: string;
  site: string;
  customer: string;
  total_qty: number;
  satuan: string;
  harga_satuan: number;
  cust_addr?: string[] | null;
  payment_terms?: string | null;
  tgl_masuk?: string | null;
  catatan?: string | null;
  warning_threshold_pct?: number | null;
}

export interface BAPOut {
  id: number;
  badan_usaha_kode: string;
  no_bap: string | null;
  site: string | null;
  tgl_bap: string | null;
  total_qty: number;
  satuan: string | null;
  status: string | null;
  created_at: string | null;
}

export interface InvoiceOut {
  id: number;
  badan_usaha_kode: string;
  no_invoice: string;
  seq_no?: number | null;
  tgl_invoice: string | null;
  no_po: string | null;
  site: string | null;
  customer: string | null;
  total_qty: number;
  satuan: string | null;
  sub_total: number | null;
  dpp: number | null;
  ppn: number | null;
  grand_total: number | null;
  // null utk akun staf -- backend tidak mengirim informasi pelunasan ke staf
  // (keputusan owner 28 Jul 2026), jadi ketiganya nullable.
  status: string | null; // "generated" | "paid"
  tgl_bayar: string | null;
  hari_outstanding: number | null;
  no_faktur_pajak: string | null;
  paperless_doc_id: string | null;
  tahap_dok?: string | null; // terbit/ke_konsultan/faktur_ada/terkirim (operasional, bukan pelunasan)
}

export interface BAPItemIn {
  no_bap: string;
  qty: number;
}

export interface InvoiceGenerateRequest {
  badan_usaha_kode: string;
  site: string;
  no_bap: string;
  inv_date: string;
  items: BAPItemIn[];
  customer?: string | null;
  cust_addr?: string[] | null;
}

export interface InvoiceGenerateResult {
  status: string; // "success" | "error"
  inv_no?: string | null;
  message?: string | null;
  site?: string | null;
  no_po?: string | null;
  sub_total?: number | null;
  grand_total?: number | null;
  pdf_path?: string | null;
  raw_stdout?: string | null;
}

export interface PaperlessUploadResult {
  ok: boolean;
  task_id?: string | null;
  status?: string | null;
  document_id?: string | null;
  message?: string | null;
}

export interface POInvoiceCutOut {
  no_invoice: string;
  tgl_invoice?: string | null;
  status?: string | null; // null utk akun staf, lihat InvoiceOut.status
  no_bap?: string | null;
  qty: number;
  satuan?: string | null;
  subtotal?: number | null;
}

export interface BAPNotaOut {
  id: number;
  badan_usaha_kode?: string | null;
  jenis?: string | null;
  no_bap?: string | null;
  site?: string | null;
  tanggal?: string | null;
  qty_kg?: number | null;
  qty_m3?: number | null;
  confidence?: string | null;
  original_filename?: string | null;
  downloaded_at?: string | null;
  created_at?: string | null;
  sumber?: string | null; // "web" | "telegram"
  mitra_pt_id?: number | null;
  mitra_pt_nama?: string | null;
  deteksi_status?: string | null; // "auto" | "perlu_konfirmasi" | "manual"
}

export interface PODocOut {
  id: number;
  po_no: string;
  original_filename?: string | null;
  created_at?: string | null;
}

export interface PaketCetakBagian {
  kode: string;
  judul: string;
  jumlah_berkas: number;
  berkas: string[];
  masalah: string[];
  lengkap: boolean;
}

export interface PaketCetakInfo {
  no_invoice: string;
  invoice: {
    no_invoice: string;
    badan_usaha_kode: string;
    tgl_invoice?: string | null;
    customer?: string | null;
    site?: string | null;
    total_qty?: number | null;
    satuan?: string | null;
    grand_total?: number | null;
    no_faktur_pajak?: string | null;
  };
  po_list: string[];
  bap_list: string[];
  bagian: PaketCetakBagian[];
  siap_cetak: boolean;
}

export const GENERATE_INVOICE_SUPPORTED = ["DKP", "KKS"];

// ---------- Mitra (Group -> PT -> PO aktif -> Invoice) ----------
export interface MitraPTLite {
  id: number;
  group_id: number;
  nama: string;
  aktif: boolean;
  site: string | null;
  jml_po_aktif: number;
}
export interface MitraGroup {
  id: number;
  nama: string;
  pt: MitraPTLite[];
}
export interface MitraPOInvoice {
  no_invoice: string;
  tgl_invoice: string | null;
  grand_total: number | null;
  status: string | null;
  tahap_dok: string | null;
  satuan: string | null;
  total_qty: number | null;
}
export interface MitraPOLinked {
  po_id: number;
  po_no: string;
  badan_usaha_kode: string;
  site: string | null;
  customer: string | null;
  status: string;
  satuan: string | null;
  total_qty: number | null;
  used_qty: number | null;
  sisa_qty: number | null;
  pct_used: number | null;
  invoices: MitraPOInvoice[];
}
export interface MitraPTDetail {
  pt: { id: number; nama: string; aktif: boolean; group_id: number; group_nama: string | null; site: string | null };
  po_terhubung: MitraPOLinked[];
}
