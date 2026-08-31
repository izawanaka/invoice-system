import type {
  KontrakOut,
  BadanUsahaOut,
  BAPNotaOut,
  BAPOut,
  FakturPajakOcrOut,
  FakturPajakOut,
  MitraGroup,
  MitraPTDetail,
  MitraPTLite,
  InvoiceGenerateRequest,
  InvoiceGenerateResult,
  InvoiceOut,
  InvoicePreviewResult,
  LoginResponse,
  MeResponse,
  PaketCetakInfo,
  PaperlessUploadResult,
  POCreateRequest,
  PODocOut,
  POInvoiceCutOut,
  POOcrOut,
  POSisaOut,
  UserCreateRequest,
  UserCreateResult,
  UserOut,
  UserUpdateRequest,
  ResiDetail,
  ResiListItem,
  CekDokumenResult,
  PembayaranRingkas,
} from "./types";

// Base URL backend FastAPI. Di sandbox/produksi nanti ini akan diarahkan ke
// hostname internal docker-network (mis. http://webapp:8000) via env saat
// build container (langkah 8 di 05_web_platform_plan.md). Default kosong
// berarti pakai path relatif "/api" (asumsi reverse-proxy Next.js/Cloudflare
// meneruskan /api/* ke backend).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const TOKEN_KEY = "invoice_app_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function extractDetailMessage(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return null;
}

async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  if (!isFormData && rest.body && !finalHeaders.has("Content-Type")) {
    finalHeaders.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let json: unknown = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = text;
    }
  }

  if (!res.ok) {
    const detail =
      json && typeof json === "object" && "detail" in json
        ? (json as { detail: unknown }).detail
        : json;
    const message = extractDetailMessage(detail) ?? `Permintaan gagal (HTTP ${res.status})`;
    throw new ApiError(res.status, message, detail);
  }

  return json as T;
}

// ---------- Auth ----------
export function login(email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    auth: false,
  });
}

export function me() {
  return request<MeResponse>("/auth/me");
}

export function changePassword(password_lama: string, password_baru: string) {
  return request<{ ok: boolean } | void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ password_lama, password_baru }),
  });
}

// ---------- Kelola akun (owner saja; staf akan dapat HTTP 403) ----------
export function listUsers() {
  return request<UserOut[]>("/users");
}

export function createUser(body: UserCreateRequest) {
  return request<UserCreateResult>("/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateUser(userId: number, body: UserUpdateRequest) {
  return request<UserOut>(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function resetUserPassword(userId: number) {
  return request<UserCreateResult>(`/users/${userId}/reset-password`, {
    method: "POST",
  });
}

// ---------- Badan usaha ----------
export function listBadanUsaha() {
  return request<BadanUsahaOut[]>("/badan-usaha");
}

// ---------- PO ----------
export interface ListPOParams {
  badan_usaha_kode?: string;
  status?: string;
  warning_only?: boolean;
}

export function listPO(params: ListPOParams = {}) {
  const qs = new URLSearchParams();
  if (params.badan_usaha_kode) qs.set("badan_usaha_kode", params.badan_usaha_kode);
  if (params.status) qs.set("status", params.status);
  if (params.warning_only) qs.set("warning_only", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<POSisaOut[]>(`/po${suffix}`);
}

export function listPOInvoices(poNo: string, badanUsahaKode: string) {
  const qs = new URLSearchParams({ badan_usaha_kode: badanUsahaKode });
  return request<POInvoiceCutOut[]>(
    `/po/${encodeURIComponent(poNo)}/invoices?${qs.toString()}`,
  );
}

export function deletePODokumen(docId: number) {
  return request<{ deleted: number }>(`/po/dokumen/${docId}`, { method: "DELETE" });
}

export function uploadPODokumen(poNo: string, badanUsahaKode: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  form.append("badan_usaha_kode", badanUsahaKode);
  return request<PODocOut>(`/po/${encodeURIComponent(poNo)}/dokumen`, {
    method: "POST",
    body: form,
  });
}

export function listPODokumen(poNo: string, badanUsahaKode: string) {
  const qs = new URLSearchParams({ badan_usaha_kode: badanUsahaKode });
  return request<PODocOut[]>(`/po/${encodeURIComponent(poNo)}/dokumen?${qs.toString()}`);
}

export async function downloadPODokumen(docId: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/po/dokumen/${docId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh dokumen PO (HTTP ${res.status})`);
  return res.blob();
}

export function setPOStatus(poNo: string, badanUsahaKode: string, status: string) {
  const qs = new URLSearchParams({ badan_usaha_kode: badanUsahaKode, status });
  return request<{ status: string }>(`/po/${encodeURIComponent(poNo)}/status?${qs.toString()}`, {
    method: "POST",
  });
}

export function deletePO(poNo: string, badanUsahaKode: string) {
  const qs = new URLSearchParams({ badan_usaha_kode: badanUsahaKode });
  return request<{ deleted: string }>(`/po/${encodeURIComponent(poNo)}?${qs.toString()}`, {
    method: "DELETE",
  });
}

export function createPO(body: POCreateRequest) {
  return request<POSisaOut>("/po", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Ekstraksi OCR dari foto/scan PO (Fase 2, 30 Jul 2026) -- HANYA pratinjau,
// belum tersimpan ke DB. badanUsahaKode opsional: kalau diisi, backend ikut
// mengecek apakah po_no hasil ekstraksi sudah ada (field po_no_sudah_ada).
export function ocrExtractPO(file: File, badanUsahaKode?: string) {
  const form = new FormData();
  form.append("file", file);
  if (badanUsahaKode) form.append("badan_usaha_kode", badanUsahaKode);
  return request<POOcrOut>("/po/ocr", { method: "POST", body: form });
}

// ---------- BAP ----------
export interface ListBAPParams {
  badan_usaha_kode?: string;
}

export function listBAP(params: ListBAPParams = {}) {
  const qs = new URLSearchParams();
  if (params.badan_usaha_kode) qs.set("badan_usaha_kode", params.badan_usaha_kode);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<BAPOut[]>(`/bap${suffix}`);
}

export function uploadBAPNota(file: File, badanUsahaKode?: string) {
  const form = new FormData();
  form.append("file", file);
  if (badanUsahaKode) form.append("badan_usaha_kode", badanUsahaKode);
  return request<BAPNotaOut>("/bap/nota", { method: "POST", body: form });
}

export function listBAPNota(params: { include_downloaded?: boolean; badan_usaha_kode?: string; belum_invoice?: boolean } = {}) {
  const qs = new URLSearchParams();
  if (params.include_downloaded) qs.set("include_downloaded", "true");
  if (params.belum_invoice) qs.set("belum_invoice", "true");
  if (params.badan_usaha_kode) qs.set("badan_usaha_kode", params.badan_usaha_kode);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<BAPNotaOut[]>(`/bap/nota${suffix}`);
}

// Unduh nota cetak sbg blob (perlu header Authorization, jadi tidak bisa <a href> polos).
// Begitu respons sukses, backend menandai downloaded_at -> item hilang dari daftar default.
export function deleteBAPNota(notaId: number) {
  return request<{ deleted: number }>(`/bap/nota/${notaId}`, { method: "DELETE" });
}

export async function downloadBAPNota(notaId: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/bap/nota/${notaId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Gagal mengunduh nota (HTTP ${res.status})`);
  }
  return res.blob();
}

// ---------- Invoices ----------
export interface ListInvoicesParams {
  badan_usaha_kode?: string;
  status?: string;
}

export function listInvoices(params: ListInvoicesParams = {}) {
  const qs = new URLSearchParams();
  if (params.badan_usaha_kode) qs.set("badan_usaha_kode", params.badan_usaha_kode);
  if (params.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<InvoiceOut[]>(`/invoices${suffix}`);
}

export function updatePaymentStatus(
  noInvoice: string,
  body: { status: "generated" | "paid"; tgl_bayar?: string | null },
) {
  return request<InvoiceOut>(`/invoices/${encodeURIComponent(noInvoice)}/payment`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// Tahap dokumen fisik (operasional, TERPISAH dari pelunasan). Staf boleh.
export function updateTahapDok(
  noInvoice: string,
  tahap: "terbit" | "ke_konsultan" | "faktur_ada" | "terkirim",
) {
  return request<InvoiceOut>(`/invoices/${encodeURIComponent(noInvoice)}/tahap`, {
    method: "PATCH",
    body: JSON.stringify({ tahap }),
  });
}

export function generateInvoice(body: InvoiceGenerateRequest) {
  return request<InvoiceGenerateResult>("/invoices/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Pratinjau HANYA-BACA (tidak menulis apa pun) sebelum admin klik Terbitkan --
// dipakai wizard "Terbit Invoice" di menu /bap.
export function previewInvoice(body: InvoiceGenerateRequest) {
  return request<InvoicePreviewResult>("/invoices/preview", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function uploadFakturPajak(
  noInvoice: string,
  file: File,
  noFakturPajak?: string,
) {
  const form = new FormData();
  form.append("file", file);
  if (noFakturPajak) form.append("no_faktur_pajak", noFakturPajak);
  return request<PaperlessUploadResult>(
    `/invoices/${encodeURIComponent(noInvoice)}/faktur-pajak`,
    { method: "POST", body: form },
  );
}

// ---------- Paket cetak (Invoice + PO + Faktur Pajak + BAP jadi 1 PDF) ----------
export function paketCetakInfo(noInvoice: string) {
  return request<PaketCetakInfo>(
    `/invoices/${encodeURIComponent(noInvoice)}/paket-cetak/info`,
  );
}

export async function paketCetakPdf(noInvoice: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/invoices/${encodeURIComponent(noInvoice)}/paket-cetak`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal menyiapkan paket cetak (HTTP ${res.status})`);
  return res.blob();
}

export function checkFakturPajakStatus(noInvoice: string, taskId: string) {
  const qs = new URLSearchParams({ task_id: taskId });
  return request<PaperlessUploadResult>(
    `/invoices/${encodeURIComponent(noInvoice)}/faktur-pajak/status?${qs.toString()}`,
  );
}

// ---------- Mitra (Group -> PT -> PO -> Invoice) ----------
export function mitraTree() {
  return request<MitraGroup[]>("/mitra/tree");
}
export function createMitraGroup(nama: string, alamat?: string, npwp?: string) {
  return request<MitraGroup>("/mitra/groups", {
    method: "POST",
    body: JSON.stringify({ nama, alamat: alamat || undefined, npwp: npwp || undefined }),
  });
}
export function createMitraPT(group_id: number, nama: string) {
  return request<MitraPTLite>("/mitra/pt", { method: "POST", body: JSON.stringify({ group_id, nama }) });
}
export function mitraPTDetail(ptId: number) {
  return request<MitraPTDetail>(`/mitra/pt/${ptId}`);
}
export function renameMitraGroup(id: number, nama: string, alamat?: string, npwp?: string) {
  return request<{ id: number; nama: string; alamat: string | null; npwp: string | null }>(`/mitra/groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ nama, alamat: alamat || undefined, npwp: npwp || undefined }),
  });
}
export function renameMitraPT(id: number, nama: string) {
  return request<{ id: number; nama: string }>(`/mitra/pt/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ nama }),
  });
}

// ---------- BAP: konfirmasi untuk PT mana (saat deteksi ragu) ----------
export function konfirmasiBapMitra(notaId: number, ptId: number) {
  return request<BAPNotaOut>(`/bap/nota/${notaId}/mitra`, {
    method: "POST",
    body: JSON.stringify({ pt_id: ptId }),
  });
}

// ---------- Bukti resi pengiriman (unggah = tanda 'terkirim') ----------
export function uploadResi(noInvoice: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<InvoiceOut>(`/invoices/${encodeURIComponent(noInvoice)}/resi`, {
    method: "POST",
    body: form,
  });
}
export async function downloadResi(noInvoice: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/invoices/${encodeURIComponent(noInvoice)}/resi/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh bukti resi (HTTP ${res.status})`);
  return res.blob();
}

// ---------- Auth: Login Email + PIN + OTP (Fase A) ----------
export interface LoginStartResponse {
  ok: boolean;
  otp_terkirim: boolean;
  email: string;
  ttl_menit: number;
  pesan: string;
}

export function loginStart(email: string, pin: string) {
  return request<LoginStartResponse>("/auth/login/start", {
    method: "POST",
    body: JSON.stringify({ email, pin }),
    auth: false,
  });
}

export function loginVerify(email: string, kode: string) {
  return request<LoginResponse>("/auth/login/verify", {
    method: "POST",
    body: JSON.stringify({ email, kode }),
    auth: false,
  });
}


// ---------- Faktur Pajak (Fase 3, 30 Jul 2026) ----------
export function ocrExtractFaktur(file: File, badanUsahaKode: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("badan_usaha_kode", badanUsahaKode);
  return request<FakturPajakOcrOut>("/faktur-pajak/ocr", { method: "POST", body: form });
}

export interface CreateFakturPajakBody {
  invoice_id: number;
  badan_usaha_kode: string;
  file: File;
  nomor_faktur?: string | null;
  tanggal_faktur?: string | null;
  dpp?: number | null;
  ppn?: number | null;
  total?: number | null;
  catatan_keraguan?: string | null;
}

export function createFakturPajak(body: CreateFakturPajakBody) {
  const form = new FormData();
  form.append("invoice_id", String(body.invoice_id));
  form.append("badan_usaha_kode", body.badan_usaha_kode);
  form.append("file", body.file);
  if (body.nomor_faktur) form.append("nomor_faktur", body.nomor_faktur);
  if (body.tanggal_faktur) form.append("tanggal_faktur", body.tanggal_faktur);
  if (body.dpp !== undefined && body.dpp !== null) form.append("dpp", String(body.dpp));
  if (body.ppn !== undefined && body.ppn !== null) form.append("ppn", String(body.ppn));
  if (body.total !== undefined && body.total !== null) form.append("total", String(body.total));
  if (body.catatan_keraguan) form.append("catatan_keraguan", body.catatan_keraguan);
  return request<FakturPajakOut>("/faktur-pajak", { method: "POST", body: form });
}

export function getFakturPajakList(badanUsahaKode?: string) {
  const qs = new URLSearchParams();
  if (badanUsahaKode) qs.set("badan_usaha_kode", badanUsahaKode);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<FakturPajakOut[]>(`/faktur-pajak${suffix}`);
}

export function deleteFakturPajak(id: number) {
  return request<{ deleted: number }>(`/faktur-pajak/${id}`, { method: "DELETE" });
}

export async function downloadFakturPajak(id: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/faktur-pajak/${id}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh Faktur Pajak (HTTP ${res.status})`);
  return res.blob();
}


// ---------- Resi Pengiriman (entitas bersama /resi, 31 Jul 2026) ----------
// Satu resi bisa mengirim banyak invoice. Invoice yang dipasang -> tahap_dok
// 'terkirim' (keluar Invoice Gantung, masuk Rekap); dilepas/dihapus -> balik gantung.
export function listResi() {
  return request<ResiListItem[]>("/resi");
}
export function resiDetail(id: number) {
  return request<ResiDetail>(`/resi/${id}`);
}
export function createResi(params: {
  file: File;
  no_invoices: string[];
  kurir?: string;
  no_resi?: string;
  tgl_kirim?: string;
}) {
  const form = new FormData();
  form.append("file", params.file);
  form.append("no_invoices", params.no_invoices.join(","));
  if (params.kurir) form.append("kurir", params.kurir);
  if (params.no_resi) form.append("no_resi", params.no_resi);
  if (params.tgl_kirim) form.append("tgl_kirim", params.tgl_kirim);
  return request<ResiDetail>("/resi", { method: "POST", body: form });
}
export function editResi(
  id: number,
  params: {
    file?: File;
    kurir?: string;
    no_resi?: string;
    tgl_kirim?: string;
    tambah?: string[];
    lepas?: string[];
  },
) {
  const form = new FormData();
  if (params.file) form.append("file", params.file);
  if (params.kurir !== undefined) form.append("kurir", params.kurir);
  if (params.no_resi !== undefined) form.append("no_resi", params.no_resi);
  if (params.tgl_kirim !== undefined) form.append("tgl_kirim", params.tgl_kirim);
  if (params.tambah && params.tambah.length) form.append("tambah", params.tambah.join(","));
  if (params.lepas && params.lepas.length) form.append("lepas", params.lepas.join(","));
  return request<ResiDetail>(`/resi/${id}`, { method: "PATCH", body: form });
}
export function deleteResi(id: number) {
  return request<{ ok: boolean; invoice_balik_gantung: string[] }>(`/resi/${id}`, {
    method: "DELETE",
  });
}
export async function downloadResiFile(id: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/resi/${id}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh berkas resi (HTTP ${res.status})`);
  return res.blob();
}
export async function downloadInvoicePdf(noInvoice: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/invoices/${encodeURIComponent(noInvoice)}/pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh PDF invoice (HTTP ${res.status})`);
  return res.blob();
}
export function batalkanInvoice(noInvoice: string) {
  return request<{ status: string; no_invoice: string; po_dikembalikan: { po_id: number; qty: number }[]; bap_nota_dilepas: number; bap_ledger_dihapus: string[] }>(
    `/invoices/${encodeURIComponent(noInvoice)}/batal`,
    { method: "POST" },
  );
}


// ---------- Cek Dokumen (Paperless) ----------
export function lihatPembayaran(noInvoice: string) {
  return request<PembayaranRingkas>(`/pembayaran/${encodeURIComponent(noInvoice)}`);
}
export function catatPembayaran(noInvoice: string, body: { nominal?: number; tgl_bayar?: string; catatan?: string; lunaskan?: boolean }) {
  return request<PembayaranRingkas>(`/pembayaran/${encodeURIComponent(noInvoice)}`, { method: "POST", body: JSON.stringify(body) });
}
export function hapusPembayaran(bayarId: number) {
  return request<PembayaranRingkas>(`/pembayaran/hapus/${bayarId}`, { method: "DELETE" });
}
export function cekDokumenInvoice(noInvoice: string) {
  return request<CekDokumenResult>(`/dokumen/invoice/${encodeURIComponent(noInvoice)}`);
}
export async function downloadDokumen(docId: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/dokumen/${docId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, `Gagal mengunduh dokumen (HTTP ${res.status})`);
  return res.blob();
}

// ---------- Kontrak (Mitra Group) ----------
export function listKontrak(groupId: number, badanUsahaKode?: string) {
  const qs = new URLSearchParams();
  if (badanUsahaKode) qs.set("badan_usaha_kode", badanUsahaKode);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<KontrakOut[]>(`/mitra/groups/${groupId}/kontrak${suffix}`);
}

export function uploadKontrak(
  groupId: number,
  file: File,
  meta: {
    badan_usaha_kode?: string;
    nomor_kontrak?: string;
    judul?: string;
    tanggal?: string;
    masa_berlaku?: string;
    nilai?: string;
    catatan?: string;
  } = {},
) {
  const form = new FormData();
  form.append("file", file);
  for (const [k, v] of Object.entries(meta)) {
    if (v) form.append(k, v);
  }
  return request<KontrakOut>(`/mitra/groups/${groupId}/kontrak`, { method: "POST", body: form });
}

export function setRingkasanKontrak(kontrakId: number, ringkasan: string) {
  return request<KontrakOut>(`/mitra/kontrak/${kontrakId}/ringkasan`, {
    method: "PATCH",
    body: JSON.stringify({ ringkasan }),
  });
}

export function deleteKontrak(kontrakId: number) {
  return request<{ ok: boolean }>(`/mitra/kontrak/${kontrakId}`, { method: "DELETE" });
}

export async function downloadKontrak(kontrakId: number): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/mitra/kontrak/${kontrakId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Gagal mengunduh kontrak (HTTP ${res.status})`);
  }
  return res.blob();
}
