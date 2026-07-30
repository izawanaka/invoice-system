import type {
  BadanUsahaOut,
  BAPNotaOut,
  BAPOut,
  MitraGroup,
  MitraPTDetail,
  MitraPTLite,
  InvoiceGenerateRequest,
  InvoiceGenerateResult,
  InvoiceOut,
  LoginResponse,
  MeResponse,
  PaketCetakInfo,
  PaperlessUploadResult,
  POCreateRequest,
  PODocOut,
  POInvoiceCutOut,
  POSisaOut,
  UserCreateRequest,
  UserCreateResult,
  UserOut,
  UserUpdateRequest,
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

export function createPO(body: POCreateRequest) {
  return request<POSisaOut>("/po", {
    method: "POST",
    body: JSON.stringify(body),
  });
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

export function listBAPNota(params: { include_downloaded?: boolean; badan_usaha_kode?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.include_downloaded) qs.set("include_downloaded", "true");
  if (params.badan_usaha_kode) qs.set("badan_usaha_kode", params.badan_usaha_kode);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<BAPNotaOut[]>(`/bap/nota${suffix}`);
}

// Unduh nota cetak sbg blob (perlu header Authorization, jadi tidak bisa <a href> polos).
// Begitu respons sukses, backend menandai downloaded_at -> item hilang dari daftar default.
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
export function createMitraGroup(nama: string) {
  return request<MitraGroup>("/mitra/groups", { method: "POST", body: JSON.stringify({ nama }) });
}
export function createMitraPT(group_id: number, nama: string, site: string) {
  return request<MitraPTLite>("/mitra/pt", { method: "POST", body: JSON.stringify({ group_id, nama, site }) });
}
export function mitraPTDetail(ptId: number) {
  return request<MitraPTDetail>(`/mitra/pt/${ptId}`);
}
export function renameMitraGroup(id: number, nama: string) {
  return request<{ id: number; nama: string }>(`/mitra/groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ nama }),
  });
}
export function renameMitraPT(id: number, nama: string, site: string) {
  return request<{ id: number; nama: string; site: string }>(`/mitra/pt/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ nama, site }),
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
