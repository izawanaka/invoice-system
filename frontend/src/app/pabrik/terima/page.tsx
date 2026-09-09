"use client";

// /pabrik/terima -- Terima Truk (B2). P3: kubik dihitung server dari p×l×t; klien hanya kirim ukuran.
import * as React from "react";
import { toast } from "sonner";
import { Truck } from "lucide-react";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { listLot, listPenerimaan, terimaTruk } from "@/lib/pabrik-api";
import { listPemasok } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function TerimaPage() {
  const { bolehTulis } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listPenerimaan(bulan), [bulan]);
  const lot = useLoad(() => listLot(true), []);
  const pemasok = useLoad(() => listPemasok(true), []);
  const [f, setF] = React.useState({ tanggal: today(), jam: new Date().toTimeString().slice(0, 5), nopol: "", pemasok_id: "", lot_id: "", p_m: "", l_m: "", t_m: "", catatan: "" });
  const [sibuk, setSibuk] = React.useState(false);
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const kubik = Number(f.p_m) * Number(f.l_m) * Number(f.t_m);
  const lotCurah = (lot.data ?? []).filter((l) => l.status === "curah");

  async function simpan() {
    if (!f.nopol || !f.pemasok_id || !f.lot_id || !f.p_m || !f.l_m || !f.t_m) return toast.error("Nopol, pemasok, lot, dan p×l×t wajib diisi");
    setSibuk(true);
    try {
      const r = await terimaTruk({ tanggal: f.tanggal, jam: f.jam, nopol: f.nopol, pemasok_id: Number(f.pemasok_id), lot_id: Number(f.lot_id), p_m: Number(f.p_m), l_m: Number(f.l_m), t_m: Number(f.t_m), catatan: f.catatan || undefined });
      toast.success(`Truk ${r.nopol} dicatat: ${fmtN(r.kubik_masuk, 2)} kubik ke lot ${r.nomor_lot}`);
      setF((s) => ({ ...s, nopol: "", p_m: "", l_m: "", t_m: "", catatan: "" }));
      daftar.reload(); lot.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }

  const rows = daftar.data ?? [];
  const totalKubik = rows.filter((r) => !r.dibatalkan).reduce((a, r) => a + r.kubik_masuk, 0);
  return (
    <Halaman judul="Terima Truk" desc="Sabut masuk dicatat per truk. Kubik dihitung sistem dari panjang × lebar × tinggi muatan." kembali="/pabrik/modul/bahan">
      {bolehTulis ? (
        <KartuInput judul="Catat truk masuk" desc="Hanya ke lot berstatus curah. Duplikat nopol + tanggal + jam ditolak.">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => set("tanggal")(e.target.value)} /></Field>
            <Field label="Jam"><Input type="time" value={f.jam} onChange={(e) => set("jam")(e.target.value)} /></Field>
            <Field label="Nopol"><Input placeholder="DC 1234 AB" value={f.nopol} onChange={(e) => set("nopol")(e.target.value)} /></Field>
            <Field label="Pemasok sabut">
              <Select value={f.pemasok_id} onValueChange={set("pemasok_id")}><SelectTrigger><SelectValue placeholder="Pilih" /></SelectTrigger>
                <SelectContent>{(pemasok.data ?? []).filter((p) => p.jenis !== "sak").map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.nama}</SelectItem>)}</SelectContent></Select>
            </Field>
            <Field label="Lot tujuan (curah)" hint={lotCurah.length === 0 ? "Tidak ada lot curah — buka lot dulu di Lot & Tahap" : undefined}>
              <Select value={f.lot_id} onValueChange={set("lot_id")}><SelectTrigger><SelectValue placeholder="Pilih lot" /></SelectTrigger>
                <SelectContent>{lotCurah.map((l) => <SelectItem key={l.lot_id} value={String(l.lot_id)}>{l.petak} · {l.nomor_lot}</SelectItem>)}</SelectContent></Select>
            </Field>
            <Field label="Panjang (m)"><Input type="number" step="0.01" inputMode="decimal" value={f.p_m} onChange={(e) => set("p_m")(e.target.value)} /></Field>
            <Field label="Lebar (m)"><Input type="number" step="0.01" inputMode="decimal" value={f.l_m} onChange={(e) => set("l_m")(e.target.value)} /></Field>
            <Field label="Tinggi (m)"><Input type="number" step="0.01" inputMode="decimal" value={f.t_m} onChange={(e) => set("t_m")(e.target.value)} /></Field>
            <Field label="Catatan"><Input value={f.catatan} onChange={(e) => set("catatan")(e.target.value)} /></Field>
            <div className="flex items-end gap-3 sm:col-span-2 lg:col-span-3">
              <p className="text-sm">Kubik: <b>{kubik > 0 ? fmtN(kubik, 2) : "—"}</b></p>
              <Button onClick={simpan} disabled={sibuk} className="gap-1"><Truck className="h-4 w-4" /> Simpan truk</Button>
            </div>
          </div>
        </KartuInput>
      ) : null}
      <KartuRekap judul="Rekap truk masuk" desc={`Total ${fmtN(totalKubik, 2)} kubik dari ${rows.filter((r) => !r.dibatalkan).length} truk`} aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>No</TableHead><TableHead>Tanggal</TableHead><TableHead>Nopol</TableHead><TableHead>Pemasok</TableHead><TableHead>Lot</TableHead><TableHead>P×L×T</TableHead><TableHead className="text-right">Kubik</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{r.tahun}-{String(r.no_urut).padStart(3, "0")}</TableCell><TableCell>{fmtTgl(r.tanggal)} {r.jam.slice(0, 5)}</TableCell><TableCell className="font-medium">{r.nopol}</TableCell><TableCell>{r.pemasok}</TableCell><TableCell>{r.nomor_lot}</TableCell>
                <TableCell className="text-xs">{r.p_m}×{r.l_m}×{r.t_m}</TableCell><TableCell className="text-right">{fmtN(r.kubik_masuk, 2)}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right"><TombolBatal path="/ops/penerimaan" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); lot.reload(); }} /></TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
