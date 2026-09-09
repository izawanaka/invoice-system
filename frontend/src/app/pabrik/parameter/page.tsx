"use client";

// /pabrik/parameter -- owner menetapkan parameter effective-dated (DESIGN-PABRIK P9).
// Nilai baru = baris baru mulai tanggal tertentu; baris lama ditutup otomatis di server.
import * as React from "react";
import Link from "next/link";
import { ArrowLeft, History } from "lucide-react";
import { toast } from "sonner";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/lib/auth-context";
import { createParameter, listParameter, listParameterRiwayat } from "@/lib/api";
import type { OpsParameterOut } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const LABEL: Record<string, { label: string; satuan: string; ket: string }> = {
  kg_per_sak: { label: "Berat 1 sak", satuan: "kg", ket: "K6: 33–35 kg berat penuh. Dipakai konversi BAP DKP (kg) → sak untuk bonus." },
  sak_per_m3_kks: { label: "Sak per m³ (KKS)", satuan: "sak", ket: "Belum diputuskan. Sistem akan menampilkan rasio teramati dari pengiriman vs BAP KKS." },
  rendemen_sak_per_kubik: { label: "Rendemen standar", satuan: "sak/kubik", ket: "1 kubik curah = 2,5 sak." },
  rendemen_min: { label: "Rendemen wajar minimum", satuan: "sak/kubik", ket: "Di bawah ini = indikasi bocor bahan baku (SOP §4)." },
  rendemen_max: { label: "Rendemen wajar maksimum", satuan: "sak/kubik", ket: "Di atas ini = indikasi sak kurang isi, timbang ulang." },
  bonus_cap_bulan: { label: "Cap bonus per bulan", satuan: "Rp", ket: "KSP-CP-001: maksimum Rp6.000.000." },
  berat_sak_min_kg: { label: "Berat bersih sak minimum", satuan: "kg", ket: "Standar Sak SOP §4. Kosong = QC otomatis belum aktif." },
  kadar_air_max_pct: { label: "Kadar air maksimum", satuan: "%", ket: "Gerbang tahap siap karung." },
  ec_max: { label: "EC maksimum", satuan: "mS/cm", ket: "Gerbang tahap siap karung." },
  toleransi_susut_pct: { label: "Toleransi susut curah", satuan: "%", ket: "Lebih dari ini = potongan (SOP §5)." },
  batas_hari_karung: { label: "Batas hari wajib karung", satuan: "hari", ket: "Lot lewat batas = susut tidak diakui." },
  upah_buruh: { label: "Upah buruh", satuan: "Rp/hari", ket: "K7: dibayar dari kas kecil." },
  upah_langsir: { label: "Upah langsir", satuan: "Rp", ket: "K7: per hari atau per rit — dicatat saat input upah." },
  upah_supir: { label: "Upah supir jemput sabut", satuan: "Rp", ket: "K7: per hari atau per rit." },
};

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Terjadi kesalahan";
}

function fmt(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 }).format(v);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function ParameterContent() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const [efektif, setEfektif] = React.useState<OpsParameterOut[]>([]);
  const [riwayat, setRiwayat] = React.useState<OpsParameterOut[] | null>(null);
  const [kode, setKode] = React.useState("kg_per_sak");
  const [nilai, setNilai] = React.useState("");
  const [mulai, setMulai] = React.useState(today());
  const [catatan, setCatatan] = React.useState("");
  const [sibuk, setSibuk] = React.useState(false);

  const load = React.useCallback(() => {
    listParameter().then(setEfektif).catch((e) => toast.error(errMsg(e)));
  }, []);
  React.useEffect(() => {
    load();
  }, [load]);

  async function simpan() {
    if (nilai !== "" && Number.isNaN(Number(nilai))) return toast.error("Nilai harus angka");
    setSibuk(true);
    try {
      await createParameter({
        kode,
        nilai: nilai === "" ? null : Number(nilai),
        berlaku_mulai: mulai,
        catatan: catatan || undefined,
      });
      toast.success(`${LABEL[kode]?.label ?? kode} ditetapkan mulai ${mulai}`);
      setNilai("");
      setCatatan("");
      load();
      if (riwayat) listParameterRiwayat().then(setRiwayat);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSibuk(false);
    }
  }

  async function bukaRiwayat() {
    if (riwayat) return setRiwayat(null);
    try {
      setRiwayat(await listParameterRiwayat());
    } catch (e) {
      toast.error(errMsg(e));
    }
  }

  if (!isOwner) {
    return <p className="text-sm text-muted-foreground">Halaman ini hanya untuk Owner.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link href="/pabrik" className="gap-1"><ArrowLeft className="h-4 w-4" /> Pabrik</Link>
        </Button>
        <div>
          <h1 className="text-2xl font-semibold">Parameter Pabrik</h1>
          <p className="text-sm text-muted-foreground">
            Setiap perubahan = baris baru berlaku mulai tanggal tertentu. Riwayat tidak pernah ditimpa.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tetapkan nilai</CardTitle>
          <CardDescription>Kosongkan nilai untuk menandai &quot;belum diputuskan&quot;. Tanggal mulai tidak boleh mendahului baris yang sedang berlaku.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-[1fr_140px_160px_1fr_auto] sm:items-end">
          <div className="flex flex-col gap-1.5">
            <Label>Parameter</Label>
            <Select value={kode} onValueChange={setKode}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(LABEL).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{LABEL[kode]?.ket}</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nilai">Nilai ({LABEL[kode]?.satuan})</Label>
            <Input id="nilai" type="number" step="any" value={nilai} onChange={(e) => setNilai(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mulai">Berlaku mulai</Label>
            <Input id="mulai" type="date" value={mulai} onChange={(e) => setMulai(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="catatan">Catatan</Label>
            <Input id="catatan" value={catatan} onChange={(e) => setCatatan(e.target.value)} placeholder="Alasan / sumber angka" />
          </div>
          <Button onClick={simpan} disabled={sibuk}>Simpan</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Berlaku hari ini</CardTitle>
            <CardDescription>Satu baris per parameter.</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={bukaRiwayat} className="gap-1">
            <History className="h-4 w-4" /> {riwayat ? "Tutup riwayat" : "Riwayat"}
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Parameter</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
                <TableHead>Satuan</TableHead>
                <TableHead>Berlaku mulai</TableHead>
                <TableHead>Catatan</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {efektif.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{LABEL[p.kode]?.label ?? p.kode}</TableCell>
                  <TableCell className="text-right font-mono">
                    {p.nilai === null || p.nilai === undefined ? <Badge variant="destructive">belum diisi</Badge> : fmt(p.nilai)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{LABEL[p.kode]?.satuan}</TableCell>
                  <TableCell className="font-mono text-xs">{p.berlaku_mulai}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.catatan ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {riwayat ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Riwayat lengkap</CardTitle>
            <CardDescription>Termasuk baris yang sudah ditutup atau dibatalkan (append-only, P1).</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Parameter</TableHead>
                  <TableHead className="text-right">Nilai</TableHead>
                  <TableHead>Mulai</TableHead>
                  <TableHead>Sampai</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Catatan</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {riwayat.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>{LABEL[p.kode]?.label ?? p.kode}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(p.nilai)}</TableCell>
                    <TableCell className="font-mono text-xs">{p.berlaku_mulai}</TableCell>
                    <TableCell className="font-mono text-xs">{p.berlaku_sampai ?? "—"}</TableCell>
                    <TableCell>
                      {p.dibatalkan_pada ? <Badge variant="outline">dibatalkan</Badge>
                        : p.berlaku_sampai ? <Badge variant="secondary">ditutup</Badge>
                        : <Badge variant="success">aktif</Badge>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{p.catatan ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function ParameterPage() {
  return (
    <RequireAuth>
      <AppShell>
        <ParameterContent />
      </AppShell>
    </RequireAuth>
  );
}
