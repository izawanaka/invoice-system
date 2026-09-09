"use client";

// /pabrik -- dashboard workspace PABRIK (tahap B1, 9 Sep 2026).
// Kontrak: Business/Cocopeat/DESIGN-PABRIK.md. B1 = parameter, pemasok, petak.
// Saldo sak kosong / stok jadi / kas kecil menyusul B3-B4.
import * as React from "react";
import Link from "next/link";
import { Factory, Plus, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/lib/auth-context";
import { createPemasok, createPetak, listParameter, listPemasok, listPetak, updatePemasok } from "@/lib/api";
import type { OpsParameterOut, OpsPemasokOut, OpsPetakOut } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const LABEL_PARAM: Record<string, string> = {
  kg_per_sak: "Berat 1 sak (kg)",
  sak_per_m3_kks: "Sak per m³ (KKS)",
  rendemen_sak_per_kubik: "Rendemen (sak/kubik)",
  rendemen_min: "Rendemen wajar min",
  rendemen_max: "Rendemen wajar maks",
  bonus_cap_bulan: "Cap bonus/bulan (Rp)",
  berat_sak_min_kg: "Berat bersih sak min (kg)",
  kadar_air_max_pct: "Kadar air maks (%)",
  ec_max: "EC maks (mS/cm)",
  toleransi_susut_pct: "Toleransi susut (%)",
  batas_hari_karung: "Batas hari wajib karung",
  upah_buruh: "Upah buruh (Rp/hari)",
  upah_langsir: "Upah langsir (Rp)",
  upah_supir: "Upah supir jemput (Rp)",
};

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Terjadi kesalahan";
}

function PabrikContent() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const bolehTulis = user?.role === "owner" || user?.role === "admin" || user?.role === "kepala";

  const [param, setParam] = React.useState<OpsParameterOut[]>([]);
  const [pemasok, setPemasok] = React.useState<OpsPemasokOut[]>([]);
  const [petak, setPetak] = React.useState<OpsPetakOut[]>([]);
  const [loading, setLoading] = React.useState(true);

  const [namaPemasok, setNamaPemasok] = React.useState("");
  const [jenisPemasok, setJenisPemasok] = React.useState("sabut");
  const [kontakPemasok, setKontakPemasok] = React.useState("");
  const [nomorPetak, setNomorPetak] = React.useState("");
  const [pPetak, setPPetak] = React.useState("");
  const [lPetak, setLPetak] = React.useState("");
  const [tPetak, setTPetak] = React.useState("");
  const [sibuk, setSibuk] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    Promise.all([listParameter(), listPemasok(), listPetak()])
      .then(([pa, pe, pt]) => {
        setParam(pa);
        setPemasok(pe);
        setPetak(pt);
      })
      .catch((e) => toast.error(errMsg(e)))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const belumDiisi = param.filter((p) => p.nilai === null || p.nilai === undefined);
  const nilai = (kode: string) => param.find((p) => p.kode === kode)?.nilai ?? null;

  async function tambahPemasok() {
    if (namaPemasok.trim().length < 2) return toast.error("Nama pemasok minimal 2 huruf");
    setSibuk(true);
    try {
      await createPemasok({ nama: namaPemasok.trim(), jenis: jenisPemasok, kontak: kontakPemasok || undefined });
      toast.success("Pemasok ditambahkan");
      setNamaPemasok("");
      setKontakPemasok("");
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSibuk(false);
    }
  }

  async function toggleAktif(p: OpsPemasokOut) {
    try {
      await updatePemasok(p.id, { aktif: !p.aktif });
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  }

  async function tambahPetak() {
    if (!nomorPetak.trim()) return toast.error("Nomor petak wajib diisi");
    setSibuk(true);
    try {
      await createPetak({
        nomor: nomorPetak.trim(),
        panjang_m: pPetak ? Number(pPetak) : undefined,
        lebar_m: lPetak ? Number(lPetak) : undefined,
        tinggi_maks_m: tPetak ? Number(tPetak) : undefined,
      });
      toast.success("Petak ditambahkan");
      setNomorPetak("");
      setPPetak("");
      setLPetak("");
      setTPetak("");
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSibuk(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Factory className="h-6 w-6" /> Pabrik Cocopeat
          </h1>
          <p className="text-sm text-muted-foreground">
            {user?.nama ? `Halo, ${user.nama}. ` : ""}Modul operasional (terima truk, lot, produksi, sak, kas kecil) menyusul tahap berikutnya.
          </p>
        </div>
        {isOwner ? (
          <Button asChild variant="outline" size="sm">
            <Link href="/pabrik/parameter" className="gap-2">
              <Settings2 className="h-4 w-4" /> Parameter
            </Link>
          </Button>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Berat 1 sak</CardDescription>
            <CardTitle className="text-2xl">{nilai("kg_per_sak") ?? "—"} kg</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">Konversi BAP DKP (kg) → sak</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Rendemen standar</CardDescription>
            <CardTitle className="text-2xl">{nilai("rendemen_sak_per_kubik") ?? "—"} sak/kubik</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Kisaran wajar {nilai("rendemen_min") ?? "—"} – {nilai("rendemen_max") ?? "—"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Parameter belum diisi owner</CardDescription>
            <CardTitle className="text-2xl">{loading ? "…" : belumDiisi.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {belumDiisi.map((p) => LABEL_PARAM[p.kode] ?? p.kode).join(", ") || "Semua terisi"}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pemasok</CardTitle>
          <CardDescription>Pemasok sabut dan pemasok sak bekas. Dipakai saat terima truk & beli sak.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {bolehTulis ? (
            <div className="grid gap-2 sm:grid-cols-[1fr_140px_1fr_auto] sm:items-end">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="nama-pemasok">Nama</Label>
                <Input id="nama-pemasok" value={namaPemasok} onChange={(e) => setNamaPemasok(e.target.value)} placeholder="Nama pemasok" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Jenis</Label>
                <Select value={jenisPemasok} onValueChange={setJenisPemasok}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sabut">Sabut</SelectItem>
                    <SelectItem value="sak">Sak bekas</SelectItem>
                    <SelectItem value="lainnya">Lainnya</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="kontak-pemasok">Kontak</Label>
                <Input id="kontak-pemasok" value={kontakPemasok} onChange={(e) => setKontakPemasok(e.target.value)} placeholder="No. HP (opsional)" />
              </div>
              <Button onClick={tambahPemasok} disabled={sibuk} className="gap-1"><Plus className="h-4 w-4" /> Tambah</Button>
            </div>
          ) : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nama</TableHead>
                <TableHead>Jenis</TableHead>
                <TableHead>Kontak</TableHead>
                <TableHead>Status</TableHead>
                {bolehTulis ? <TableHead /> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {pemasok.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground">Belum ada pemasok</TableCell></TableRow>
              ) : pemasok.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.nama}</TableCell>
                  <TableCell className="capitalize">{p.jenis}</TableCell>
                  <TableCell className="text-xs">{p.kontak ?? "—"}</TableCell>
                  <TableCell>{p.aktif ? <Badge variant="success">Aktif</Badge> : <Badge variant="outline">Nonaktif</Badge>}</TableCell>
                  {bolehTulis ? (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => toggleAktif(p)}>{p.aktif ? "Nonaktifkan" : "Aktifkan"}</Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Petak lapangan</CardTitle>
          <CardDescription>1 petak = 1 lot, tidak boleh dicampur (SOP §4). Hanya owner yang menambah petak.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {isOwner ? (
            <div className="grid gap-2 sm:grid-cols-[120px_1fr_1fr_1fr_auto] sm:items-end">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="nomor-petak">Nomor</Label>
                <Input id="nomor-petak" value={nomorPetak} onChange={(e) => setNomorPetak(e.target.value)} placeholder="P1" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="p-petak">Panjang (m)</Label>
                <Input id="p-petak" type="number" step="0.1" value={pPetak} onChange={(e) => setPPetak(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="l-petak">Lebar (m)</Label>
                <Input id="l-petak" type="number" step="0.1" value={lPetak} onChange={(e) => setLPetak(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="t-petak">Tinggi maks (m)</Label>
                <Input id="t-petak" type="number" step="0.1" value={tPetak} onChange={(e) => setTPetak(e.target.value)} />
              </div>
              <Button onClick={tambahPetak} disabled={sibuk} className="gap-1"><Plus className="h-4 w-4" /> Tambah</Button>
            </div>
          ) : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nomor</TableHead>
                <TableHead>P × L × T maks (m)</TableHead>
                <TableHead>Volume penuh (kubik)</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {petak.length === 0 ? (
                <TableRow><TableCell colSpan={4} className="text-center text-sm text-muted-foreground">Belum ada petak</TableCell></TableRow>
              ) : petak.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.nomor}</TableCell>
                  <TableCell>{p.panjang_m ?? "—"} × {p.lebar_m ?? "—"} × {p.tinggi_maks_m ?? "—"}</TableCell>
                  <TableCell>
                    {p.panjang_m && p.lebar_m && p.tinggi_maks_m ? (p.panjang_m * p.lebar_m * p.tinggi_maks_m).toFixed(1) : "—"}
                  </TableCell>
                  <TableCell>{p.aktif ? <Badge variant="success">Aktif</Badge> : <Badge variant="outline">Nonaktif</Badge>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function PabrikPage() {
  return (
    <RequireAuth>
      <AppShell>
        <PabrikContent />
      </AppShell>
    </RequireAuth>
  );
}
