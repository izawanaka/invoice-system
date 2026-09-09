"""patch_fe_b1.py -- patch anchor-assert frontend workspace PABRIK (B1, 9 Sep 2026).
Setiap anchor wajib muncul tepat N kali; gagal = tidak ada file yang ditulis (dicek dulu semua)."""
ROOT = "/home/izawa/invoice-system/frontend/src/"
TANDA = "PABRIK_B1_9SEP2026"

EDITS = {
    # ---------------- types.ts
    "lib/types.ts": [
        ('export type Role = "owner" | "staff" | "viewer";\n',
         '// PABRIK_B1_9SEP2026: admin & kepala = peran workspace Pabrik (DESIGN-PABRIK K2),\n'
         '// setara penuh untuk input, tidak pernah melihat DKP/KKS (server 403).\n'
         'export type Role = "owner" | "staff" | "viewer" | "admin" | "kepala";\n', 1),
    ],
    # ---------------- badan-usaha-context.tsx
    "lib/badan-usaha-context.tsx": [
        ('const DASHBOARD_BU = ["DKP", "KKS"];\n',
         'const DASHBOARD_BU = ["DKP", "KKS"];\n'
         '// PABRIK_B1_9SEP2026: workspace ketiga "PABRIK" (bukan badan usaha; tidak ada di tabel\n'
         '// badan_usaha). Boleh dipilih owner/viewer; admin & kepala OTOMATIS masuk ke sini.\n'
         'export const WORKSPACE_PABRIK = "PABRIK";\n'
         'const WORKSPACE_VALID = [...DASHBOARD_BU, WORKSPACE_PABRIK];\n'
         'export const PERAN_PABRIK = ["admin", "kepala"];\n', 1),
        ('      if (saved && DASHBOARD_BU.includes(saved)) setSelectedState(saved);\n',
         '      if (saved && WORKSPACE_VALID.includes(saved)) setSelectedState(saved);\n', 1),
        ('  const resetWorkspace = React.useCallback(() => {\n',
         '  // PABRIK_B1_9SEP2026: admin/kepala tidak punya pilihan workspace lain.\n'
         '  React.useEffect(() => {\n'
         '    if (!hydrated || !user) return;\n'
         '    if (PERAN_PABRIK.includes(user.role) && (!chosen || selected !== WORKSPACE_PABRIK)) {\n'
         '      setSelected(WORKSPACE_PABRIK);\n'
         '    }\n'
         '  }, [hydrated, user, chosen, selected, setSelected]);\n\n'
         '  const resetWorkspace = React.useCallback(() => {\n', 1),
    ],
    # ---------------- pilih/page.tsx
    "app/pilih/page.tsx": [
        ('import { useBadanUsaha } from "@/lib/badan-usaha-context";\n',
         'import { PERAN_PABRIK, WORKSPACE_PABRIK, useBadanUsaha } from "@/lib/badan-usaha-context";\n', 1),
        ('  { kode: "KKS", nama: "Cocopeat KKS", satuan: "m3", desc: "Terbit invoice cocopeat satuan meter kubik." },\n];\n',
         '  { kode: "KKS", nama: "Cocopeat KKS", satuan: "m3", desc: "Terbit invoice cocopeat satuan meter kubik." },\n'
         '  // PABRIK_B1_9SEP2026: workspace hulu (DESIGN-PABRIK K1).\n'
         '  { kode: WORKSPACE_PABRIK, nama: "Pabrik Cocopeat", satuan: "sak", desc: "Operasional pabrik: terima truk, lot, produksi, sak, kas kecil, bonus kepala." },\n'
         '];\n', 1),
        ('  function pilih(kode: string) {\n    setSelected(kode);\n    router.replace("/dashboard");\n  }\n',
         '  // Staf invoice tidak punya akses Pabrik (server 403); admin/kepala hanya Pabrik.\n'
         '  const role = user?.role ?? "";\n'
         '  const daftar = PERAN_PABRIK.includes(role)\n'
         '    ? WORKSPACES.filter((w) => w.kode === WORKSPACE_PABRIK)\n'
         '    : role === "staff" ? WORKSPACES.filter((w) => w.kode !== WORKSPACE_PABRIK) : WORKSPACES;\n\n'
         '  function pilih(kode: string) {\n    setSelected(kode);\n    router.replace(kode === WORKSPACE_PABRIK ? "/pabrik" : "/dashboard");\n  }\n', 1),
        ('<h1 className="text-2xl font-semibold">Pilih Masuk DKP atau KKS</h1>',
         '<h1 className="text-2xl font-semibold">Pilih Workspace</h1>', 1),
        ('      <div className="grid w-full max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">\n        {WORKSPACES.map((w) => (',
         '      <div className="grid w-full max-w-4xl grid-cols-1 gap-4 sm:grid-cols-3">\n        {daftar.map((w) => (', 1),
    ],
    # ---------------- app-shell.tsx
    "components/app-shell.tsx": [
        ('  Send,\n} from "lucide-react";\n',
         '  Send,\n  Factory,\n  Settings2,\n} from "lucide-react";\n', 1),
        ('import { useBadanUsaha } from "@/lib/badan-usaha-context";\n',
         'import { PERAN_PABRIK, WORKSPACE_PABRIK, useBadanUsaha } from "@/lib/badan-usaha-context";\n', 1),
        ('  const isViewer = user?.role === "viewer";\n',
         '  const isViewer = user?.role === "viewer";\n'
         '  // PABRIK_B1_9SEP2026: workspace Pabrik (DESIGN-PABRIK K1-K3). admin/kepala dikunci di /pabrik/*.\n'
         '  const isPabrikRole = PERAN_PABRIK.includes(user?.role ?? "");\n'
         '  const isPabrikWs = selected === WORKSPACE_PABRIK || (pathname?.startsWith("/pabrik") ?? false);\n'
         '  const wsLabel = isPabrikWs ? "PABRIK" : selectedBu?.kode;\n', 1),
        ('  const navItems: NavEntry[] = [\n    { href: "/mitra", label: "Mitra", icon: Users },\n    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },\n  ];\n  if (chosen) {',
         '  const navItems: NavEntry[] = isPabrikWs\n'
         '    ? [{ href: "/pabrik", label: "Pabrik", icon: Factory }]\n'
         '    : [\n        { href: "/mitra", label: "Mitra", icon: Users },\n        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },\n      ];\n'
         '  if (isPabrikWs && isOwner) {\n    navItems.push({ href: "/pabrik/parameter", label: "Parameter", icon: Settings2 });\n  }\n'
         '  if (chosen && !isPabrikWs) {', 1),
        ('  React.useEffect(() => {\n    if (!hydrated) return;\n    if (!chosen) router.replace("/pilih");\n  }, [hydrated, chosen, router]);\n',
         '  React.useEffect(() => {\n    if (!hydrated) return;\n    if (!chosen) router.replace("/pilih");\n  }, [hydrated, chosen, router]);\n\n'
         '  // PABRIK_B1_9SEP2026: admin/kepala tidak boleh keluar dari /pabrik/* (server pun 403);\n'
         '  // siapa pun yang memilih workspace Pabrik diarahkan dari /dashboard ke /pabrik.\n'
         '  React.useEffect(() => {\n'
         '    if (!hydrated || !pathname) return;\n'
         '    if (isPabrikRole && !pathname.startsWith("/pabrik")) router.replace("/pabrik");\n'
         '    else if (isPabrikWs && pathname === "/dashboard") router.replace("/pabrik");\n'
         '  }, [hydrated, pathname, isPabrikRole, isPabrikWs, router]);\n', 1),
        ('          <p className="text-sm font-semibold leading-tight">Invoice System</p>\n          <p className="text-xs text-muted-foreground">PO · BAP · Invoice</p>\n',
         '          <p className="text-sm font-semibold leading-tight">{isPabrikWs ? "Pabrik Cocopeat" : "Invoice System"}</p>\n'
         '          <p className="text-xs text-muted-foreground">{isPabrikWs ? "Hulu · Produksi" : "PO · BAP · Invoice"}</p>\n', 1),
        ('            {chosen && selectedBu ? (\n              <>\n                <span className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">\n                  Workspace: {selectedBu.kode}\n                </span>\n                <Link\n                  href="/pilih"\n                  className="text-xs font-medium text-primary underline-offset-2 hover:underline"\n                >\n                  Ganti Workspace\n                </Link>\n              </>\n            ) : null}',
         '            {chosen && wsLabel ? (\n              <>\n                <span className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">\n                  Workspace: {wsLabel}\n                </span>\n                {isPabrikRole ? null : (\n                <Link\n                  href="/pilih"\n                  className="text-xs font-medium text-primary underline-offset-2 hover:underline"\n                >\n                  Ganti Workspace\n                </Link>\n                )}\n              </>\n            ) : null}', 1),
        ('                    {isViewer ? "Pengamat — hanya melihat" : <span className="capitalize">{user?.role}</span>}\n',
         '                    {isViewer ? "Pengamat — hanya melihat" : user?.role === "kepala" ? "Kepala pabrik" : user?.role === "admin" ? "Admin pabrik" : <span className="capitalize">{user?.role}</span>}\n', 1),
        ('                  {chosen && selectedBu ? (\n                    <p className="mt-1 text-xs font-medium text-primary">Workspace: {selectedBu.kode}</p>\n                  ) : null}',
         '                  {chosen && wsLabel ? (\n                    <p className="mt-1 text-xs font-medium text-primary">Workspace: {wsLabel}</p>\n                  ) : null}', 1),
        ('                {chosen ? (\n                  <DropdownMenuItem onClick={() => router.push("/pilih")} className="gap-2">\n                    <ArrowLeftRight className="h-4 w-4" />\n                    Pindah Workspace (DKP/KKS)\n',
         '                {chosen && !isPabrikRole ? (\n                  <DropdownMenuItem onClick={() => router.push("/pilih")} className="gap-2">\n                    <ArrowLeftRight className="h-4 w-4" />\n                    Pindah Workspace\n', 1),
    ],
    # ---------------- pengaturan/page.tsx
    "app/pengaturan/page.tsx": [
        ('                <SelectItem value="owner">Owner — akses penuh termasuk pelunasan & akun</SelectItem>\n',
         '                <SelectItem value="admin">Admin pabrik — input operasional Pabrik saja, tidak melihat penjualan</SelectItem>\n'
         '                <SelectItem value="kepala">Kepala pabrik — input operasional Pabrik + lihat BAP versi pabrik & bonusnya</SelectItem>\n'
         '                <SelectItem value="owner">Owner — akses penuh termasuk pelunasan & akun</SelectItem>\n', 1),
        ('                <SelectItem value="owner">Owner</SelectItem>\n',
         '                <SelectItem value="admin">Admin pabrik</SelectItem>\n'
         '                <SelectItem value="kepala">Kepala pabrik</SelectItem>\n'
         '                <SelectItem value="owner">Owner</SelectItem>\n', 1),
        ('                        ) : u.role === "viewer" ? (\n                          <Badge variant="outline">Pengamat</Badge>\n                        ) : (',
         '                        ) : u.role === "viewer" ? (\n                          <Badge variant="outline">Pengamat</Badge>\n'
         '                        ) : u.role === "admin" ? (\n                          <Badge variant="secondary">Admin pabrik</Badge>\n'
         '                        ) : u.role === "kepala" ? (\n                          <Badge variant="secondary">Kepala pabrik</Badge>\n'
         '                        ) : (', 1),
    ],
}

API_TAIL = '''
// ---------------------------------------------------------------- PABRIK_B1_9SEP2026
// Workspace PABRIK (webapp/routers/ops.py). Semua lewat prefix /ops.
export function opsPing() {
  return request<{ workspace: string; role: string; nama: string }>("/ops/ping");
}
export function listParameter(tanggal?: string) {
  return request<OpsParameterOut[]>(`/ops/parameter${tanggal ? `?tanggal=${tanggal}` : ""}`);
}
export function listParameterRiwayat(kode?: string) {
  return request<OpsParameterOut[]>(`/ops/parameter/riwayat${kode ? `?kode=${encodeURIComponent(kode)}` : ""}`);
}
export function createParameter(body: OpsParameterCreate) {
  return request<OpsParameterOut>("/ops/parameter", { method: "POST", body: JSON.stringify(body) });
}
export function listTarifBonus() {
  return request<OpsTarifBonusOut[]>("/ops/tarif-bonus");
}
export function listPemasok(hanyaAktif = false) {
  return request<OpsPemasokOut[]>(`/ops/pemasok${hanyaAktif ? "?hanya_aktif=true" : ""}`);
}
export function createPemasok(body: { nama: string; jenis: string; kontak?: string }) {
  return request<OpsPemasokOut>("/ops/pemasok", { method: "POST", body: JSON.stringify(body) });
}
export function updatePemasok(id: number, body: { nama?: string; kontak?: string; aktif?: boolean }) {
  return request<OpsPemasokOut>(`/ops/pemasok/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}
export function listPetak() {
  return request<OpsPetakOut[]>("/ops/petak");
}
export function createPetak(body: { nomor: string; panjang_m?: number; lebar_m?: number; tinggi_maks_m?: number }) {
  return request<OpsPetakOut>("/ops/petak", { method: "POST", body: JSON.stringify(body) });
}
'''

TYPES_TAIL = '''
// ---------------------------------------------------------------- PABRIK_B1_9SEP2026
// Mengikuti webapp/routers/ops.py (workspace Pabrik).
export interface OpsParameterOut {
  id: number;
  kode: string;
  nilai: number | null;
  berlaku_mulai: string;
  berlaku_sampai: string | null;
  catatan: string | null;
  created_by: number;
  dibatalkan_pada?: string | null;
}
export interface OpsParameterCreate {
  kode: string;
  nilai: number | null;
  berlaku_mulai: string;
  catatan?: string;
}
export interface OpsTarifBonusOut {
  id: number;
  jenjang: number;
  sak_dari: number;
  sak_sampai: number | null;
  tarif_per_sak: number;
  berlaku_mulai: string;
  berlaku_sampai: string | null;
}
export interface OpsPemasokOut {
  id: number;
  nama: string;
  jenis: string;
  kontak: string | null;
  aktif: boolean;
}
export interface OpsPetakOut {
  id: number;
  nomor: string;
  panjang_m: number | null;
  lebar_m: number | null;
  tinggi_maks_m: number | null;
  aktif: boolean;
}
'''

# 1. cek semua anchor dulu (tanpa menulis)
contents = {}
for path, edits in EDITS.items():
    s = open(ROOT + path, encoding="utf-8").read()
    if TANDA in s:
        print(f"skip {path}: sudah dipatch")
        continue
    for anchor, _new, count in edits:
        n = s.count(anchor)
        assert n == count, f"{path}: anchor {n}x (harap {count}x) -> {anchor[:70]!r}"
    contents[path] = s
api = open(ROOT + "lib/api.ts", encoding="utf-8").read()
imp_anchor = '  PembayaranRingkas,\n} from "./types";\n'
if TANDA not in api:
    assert api.count(imp_anchor) == 1, "api.ts: anchor import types"
types_s = contents.get("lib/types.ts")

# 2. tulis
for path, s in contents.items():
    for anchor, new, _c in EDITS[path]:
        s = s.replace(anchor, new)
    if path == "lib/types.ts":
        s = s.rstrip("\n") + "\n" + TYPES_TAIL
    open(ROOT + path, "w", encoding="utf-8").write(s)
    print(f"ok   {path}")
if TANDA not in api:
    api = api.replace(imp_anchor, '  PembayaranRingkas,\n  OpsParameterOut,\n  OpsParameterCreate,\n  OpsTarifBonusOut,\n  OpsPemasokOut,\n  OpsPetakOut,\n} from "./types";\n')
    api = api.rstrip("\n") + "\n" + API_TAIL
    open(ROOT + "lib/api.ts", "w", encoding="utf-8").write(api)
    print("ok   lib/api.ts")
print("PATCH_FE_B1_OK")
