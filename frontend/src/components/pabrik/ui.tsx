"use client";

// Komponen bersama workspace PABRIK (PABRIK_FE_B2B7_9SEP2026).
// Pola halaman fungsi: judul + form input di atas (kartu hijau) + rekap/daftar di bawah.
import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Ban } from "lucide-react";
import { toast } from "sonner";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
import { batal } from "@/lib/pabrik-api";
import type { Fungsi, Warna } from "@/lib/pabrik-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Terjadi kesalahan";
}
export const today = () => new Date().toISOString().slice(0, 10);
export const bulanIni = () => today().slice(0, 7);
export const fmtN = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("id-ID", { maximumFractionDigits: d }).format(v);
export const fmtRp = (v: number | null | undefined) => (v === null || v === undefined ? "—" : "Rp" + fmtN(v));
export const fmtTgl = (s: string | null | undefined) => (s ? s.slice(0, 10).split("-").reverse().join("-") : "—");

/** Peran yang boleh menulis modul operasional (K2: admin & kepala setara). */
export function usePeran() {
  const { user } = useAuth();
  const role = user?.role ?? "";
  return { user, role, isOwner: role === "owner", bolehTulis: ["owner", "admin", "kepala"].includes(role) };
}

/** Muat data; ulang saat deps berubah. */
export function useLoad<T>(fn: () => Promise<T>, deps: React.DependencyList) {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(true);
  const reload = React.useCallback(() => {
    setLoading(true);
    fn().then(setData).catch((e) => toast.error(errMsg(e))).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  React.useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload, setData };
}

const WARNA: Record<Warna, string> = {
  hijau: "border-green-300 bg-green-50 text-green-900 hover:bg-green-100 dark:border-green-800 dark:bg-green-950/40 dark:text-green-100",
  biru: "border-sky-300 bg-sky-50 text-sky-900 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100",
  ungu: "border-violet-300 bg-violet-50 text-violet-900 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-100",
};

/** Grid kartu fungsi ala Accurate. Fungsi khusus owner disembunyikan dari admin/kepala/viewer. */
export function Launcher({ fungsi, kecil = false }: { fungsi: Fungsi[]; kecil?: boolean }) {
  const { isOwner } = usePeran();
  const items = fungsi.filter((f) => !f.owner || isOwner);
  return (
    <div className={cn("grid gap-3", kecil ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4")}>
      {items.map((f) => {
        const Icon = f.icon;
        return (
          <Link key={f.href} href={f.href} className={cn("flex flex-col items-center gap-2 rounded-xl border p-4 text-center shadow-sm transition-colors", WARNA[f.warna])}>
            <Icon className={kecil ? "h-7 w-7" : "h-9 w-9"} strokeWidth={1.5} />
            <span className="text-sm font-semibold leading-tight">{f.label}</span>
            {!kecil ? <span className="text-[11px] leading-snug opacity-80">{f.desc}</span> : null}
          </Link>
        );
      })}
    </div>
  );
}

export function Legenda() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1"><i className="h-3 w-3 rounded-sm border border-green-300 bg-green-50" /> Input / transaksi</span>
      <span className="flex items-center gap-1"><i className="h-3 w-3 rounded-sm border border-sky-300 bg-sky-50" /> Master</span>
      <span className="flex items-center gap-1"><i className="h-3 w-3 rounded-sm border border-violet-300 bg-violet-50" /> Rekap / laporan</span>
    </div>
  );
}

/** Bungkus halaman fungsi: auth + shell + judul + tombol kembali ke modul. */
export function Halaman({ judul, desc, kembali = "/pabrik", aksi, children }: { judul: string; desc?: string; kembali?: string; aksi?: React.ReactNode; children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Button asChild variant="ghost" size="sm"><Link href={kembali} className="gap-1"><ArrowLeft className="h-4 w-4" /> Kembali</Link></Button>
              <div>
                <h1 className="text-xl font-semibold leading-tight md:text-2xl">{judul}</h1>
                {desc ? <p className="text-xs text-muted-foreground md:text-sm">{desc}</p> : null}
              </div>
            </div>
            {aksi}
          </div>
          {children}
        </div>
      </AppShell>
    </RequireAuth>
  );
}

/** Kartu form input (hijau). */
export function KartuInput({ judul, desc, children }: { judul: string; desc?: string; children: React.ReactNode }) {
  return (
    <Card className="border-green-200 bg-green-50/40 dark:border-green-900 dark:bg-green-950/20">
      <CardHeader className="pb-3"><CardTitle className="text-base">{judul}</CardTitle>{desc ? <CardDescription>{desc}</CardDescription> : null}</CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function KartuRekap({ judul, desc, aksi, children }: { judul: string; desc?: string; aksi?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-3">
        <div><CardTitle className="text-base">{judul}</CardTitle>{desc ? <CardDescription>{desc}</CardDescription> : null}</div>
        {aksi}
      </CardHeader>
      <CardContent className="overflow-x-auto">{children}</CardContent>
    </Card>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function FilterBulan({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Label className="text-xs">Bulan</Label>
      <Input type="month" value={value} onChange={(e) => onChange(e.target.value)} className="h-8 w-[150px]" />
    </div>
  );
}

export function StatusBatal({ dibatalkan }: { dibatalkan: boolean }) {
  return dibatalkan ? <Badge variant="outline" className="line-through opacity-70">batal</Badge> : <Badge variant="success">aktif</Badge>;
}

/** Tombol batal (P1: menandai, bukan menghapus) dengan alasan wajib. */
export function TombolBatal({ path, id, dibatalkan, onDone, label = "Batalkan" }: { path: string; id: number; dibatalkan: boolean; onDone: () => void; label?: string }) {
  const [open, setOpen] = React.useState(false);
  const [alasan, setAlasan] = React.useState("");
  const [sibuk, setSibuk] = React.useState(false);
  if (dibatalkan) return null;
  async function kirim() {
    if (alasan.trim().length < 3) return toast.error("Alasan minimal 3 huruf");
    setSibuk(true);
    try {
      await batal(path, id, alasan.trim());
      toast.success("Dibatalkan (baris tetap tersimpan sebagai jejak)");
      setOpen(false); setAlasan(""); onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  return (
    <>
      <Button variant="ghost" size="sm" className="gap-1 text-destructive" onClick={() => setOpen(true)}><Ban className="h-3.5 w-3.5" /> {label}</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Batalkan baris ini?</DialogTitle><DialogDescription>Baris tidak dihapus, hanya ditandai batal beserta alasannya. Saldo turunan ikut dibalik.</DialogDescription></DialogHeader>
          <Input placeholder="Alasan pembatalan" value={alasan} onChange={(e) => setAlasan(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Tidak</Button>
            <Button variant="destructive" onClick={kirim} disabled={sibuk}>Ya, batalkan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function Kosong({ teks = "Belum ada data" }: { teks?: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{teks}</p>;
}
