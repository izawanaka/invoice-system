// Tipe-tipe ini mengikuti persis model Pydantic di backend (webapp/schemas.py)
// supaya tidak ada lapisan terjemahan yang bisa jadi sumber salah baca data
// finansial. Lihat 02_db_schema.md / 05_web_platform_plan.md di Project.

// "viewer" (Pengamat) ditambahkan 4 Sep 2026 -- pengamat murni: boleh MEMBACA
// semua termasuk pelunasan, tapi tidak menulis & tidak mengunduh. Penegakannya
// di server (webapp/security.py + middleware main.py); di sini hanya tampilan.
export type Role = "owner" | "staff" | "viewer";

export interface MeResponse {
  id: number;
  email: string;
  nama: string;
  role: Role;
  username?: string | null;
}

// Kelola akun (halaman Pengaturan). Mengikuti webapp/schemas.py.
export interface UserOut {
  id: number;
  email: string;
  username: string;
  nama: string;
  role: Role;
  aktif: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
  // 5 Sep 2026: izin Google (diatur owner) & bukti Google (diisi sistem)
  login_via_google: boolean;
  google_terbukti_pada?: string | null;
}

export interface UserCreateRequest {
  email: string;
  username: string;
  nama: string;
  role: Role;
  password?: string; // opsional: password awal diinput owner (min 8)
  login_via_google?: boolean;
}

export interface UserUpdateRequest {
  nama?: string;
  role?: Role;
  aktif?: boolean;
  username?: string;
  login_via_google?: boolean;
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

export interface POOcrItemOut {
  nama_item?: string | null;
  kuantitas?: number | null;
  harga_satuan?: number | null;
  subtotal?: number | null;
}

export interface POOcrOut {
  po_no?: string | null;
  customer?: string | null;
  tanggal?: string | null;
  items: POOcrItemOut[];
  total_qty?: number | null;
  satuan?: string | null;
  harga_satuan?: number | null;
  total_nilai?: number | null;
  site_saran?: string | null;
  site_status: string;
  catatan_keraguan?: string | null;
  po_no_sudah_ada?: boolean | null;
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
  // owner-only: total cicilan yang sudah dibayar (utk centang & jumlah di Rekap Invoice)
  total_dibayar?: number | null;
  no_faktur_pajak: string | null;
  paperless_doc_id: string | null;
  tahap_dok?: string | null; // terbit/ke_konsultan/faktur_ada/terkirim (operasional, bukan pelunasan)
  dibatalkan_at?: string | null; // terisi = invoice sudah dibatalkan (qty PO & BAP sudah dikembalikan)
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
  // BAP tanpa nomor: id baris unggahan app_bap_nota (identifikasi + anti-dobel-tagih).
  nota_ids?: number[];
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

// Pratinjau HANYA-BACA sebelum klik Terbitkan -- wizard "Terbit Invoice" (menu /bap).
export interface InvoicePreviewLine {
  urutan: number;
  deskripsi: string;
  qty: number;
  harga: number;
  jumlah: number;
}

export interface InvoicePreviewPOSplit {
  po_no: string;
  qty_dipotong: number;
  sisa_sebelum: number;
  sisa_sesudah: number;
}

export interface InvoicePreviewResult {
  inv_no_preview: string;
  site: string;
  no_po: string;
  items: InvoicePreviewLine[];
  po_splits: InvoicePreviewPOSplit[];
  sub_total: number;
  dpp: number;
  ppn: number;
  grand_total: number;
  catatan: string;
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
  dipakai_invoice?: string | null; // no. invoice kalau BAP ini sudah dipakai, null kalau belum
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
  jml_po_aktif: number;
}
export interface MitraGroup {
  id: number;
  nama: string;
  alamat: string | null;
  npwp: string | null;
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
  pt: { id: number; nama: string; aktif: boolean; group_id: number; group_nama: string | null };
  po_terhubung: MitraPOLinked[];
}


// ---------- Faktur Pajak (Fase 3, 30 Jul 2026) ----------
export interface FakturPajakCandidateInvoice {
  invoice_id: number;
  no_invoice: string;
  customer?: string | null;
  grand_total?: number | null;
  tgl_invoice?: string | null;
  dpp?: number | null;
  ppn?: number | null;
}

export interface FakturPajakOcrOut {
  nomor_faktur?: string | null;
  tanggal_faktur?: string | null;
  nama_pembeli?: string | null;
  referensi_invoice?: string | null;
  dpp?: number | null;
  ppn?: number | null;
  total?: number | null;
  catatan_keraguan?: string | null;
  kandidat_invoice: FakturPajakCandidateInvoice[];
}

export interface FakturPajakOut {
  id: number;
  badan_usaha_kode: string;
  invoice_id: number;
  no_invoice: string;
  nomor_faktur?: string | null;
  tanggal_faktur?: string | null;
  dpp?: number | null;
  ppn?: number | null;
  total?: number | null;
  original_filename?: string | null;
  catatan_keraguan?: string | null;
  status_cocok: "matched" | "mismatch" | "pending";
  catatan_selisih?: string | null;
  created_at?: string | null;
}


// ---------- Resi Pengiriman (entitas bersama app_resi, 31 Jul 2026) ----------
export interface ResiInvoiceLite {
  no_invoice: string;
  tgl_invoice: string | null;
  site: string | null;
  customer: string | null;
  grand_total: number | null;
  badan_usaha_kode: string | null;
}
export interface ResiListItem {
  id: number;
  no_resi: string | null;
  kurir: string | null;
  tgl_kirim: string | null;
  created_at: string | null;
  badan_usaha_kode: string | null;
  jml_invoice: number;
  daftar_invoice: string;
}
export interface ResiDetail {
  id: number;
  no_resi: string | null;
  kurir: string | null;
  tgl_kirim: string | null;
  created_at: string | null;
  badan_usaha_kode: string | null;
  ada_berkas: boolean;
  paperless_doc_id: string | null;
  invoices: ResiInvoiceLite[];
}


// ---------- Cek Dokumen (Paperless) ----------
export interface DokumenItem {
  jenis: string;
  judul: string;
  doc_id: number;
}
export interface PembayaranItem {
  id: number;
  nominal: number;
  tgl_bayar: string | null;
  catatan: string | null;
  created_at: string | null;
}
export interface PembayaranRingkas {
  no_invoice: string;
  grand_total: number;
  total_dibayar: number;
  sisa: number;
  status: string;
  daftar: PembayaranItem[];
}
export interface CekDokumenResult {
  no_invoice: string;
  paperless_aktif: boolean;
  dokumen: DokumenItem[];
}

// ---------- Kontrak (dokumen payung per Group, 3 Agu 2026) ----------
export interface KontrakOut {
  id: number;
  group_id: number;
  badan_usaha_kode: string | null;
  nomor_kontrak: string | null;
  judul: string | null;
  tanggal: string | null;
  masa_berlaku: string | null;
  nilai: number | null;
  catatan: string | null;
  original_filename: string | null;
  punya_file: boolean;
  paperless_doc_id: string | null;
  ringkasan: string | null;
  ringkasan_at: string | null;
  created_at: string | null;
}
