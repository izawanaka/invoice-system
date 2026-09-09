"use client";

// /pabrik/sak -- Sak Kosong (B3): beli (otomatis kas keluar), rusak (menunggu retur), retur. Opname ada di /pabrik/opname (owner).
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtRp, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { getSaldo, listSak, mutasiSak } from "@/lib/pabrik-api";
import { listPemasok } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function SakPage() {
  const { bolehTulis } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listSak(bulan), [bulan]);
  const saldo = useLoad(getSaldo, []);
  const pemasok = useLoad(() => listPemasok(true), []);
  const [f, setF] = React.useState({ tanggal: today(), jenis: "beli", jumlah: "", pemasok_id: "", harga: "", nota: "", ket: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpan() {
    if (!f.jumlah) return toast.error("Jumlah wajib diisi");
    if (f.jenis === "beli" && (!f.pemasok_id || !f.harga)) return toast.error("Beli sak butuh pemasok & harga per sak");
    setSibuk(true);
    try {
      await mutasiSak({ tanggal: f.tanggal, jenis: f.jenis, jumlah: Number(f.jumlah), pemasok_id: f.pemasok_id ? Number(f.pemasok_id) : undefined, harga_per_sak: f.harga ? Number(f.harga) : undefined, foto_nota: f.nota || undefined, keterangan: f.ket || undefined });
      toast.success(`${f.jenis} ${f.jumlah} sak dicatat`);
      setF((s) => ({ ...s, jumlah: "", nota: "", ket: "" })); daftar.reload(); saldo.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = daftar.data ?? [];
  const s = saldo.data;
  return (
    <Halaman judul="Sak Kosong" desc="Beli sak bekas otomatis membuat kas keluar kategori sak. Sak rusak menunggu retur ke pemasok." kembali="/pabrik/modul/produksi">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Saldo sak kosong</p><p className="text-2xl font-semibold">{s ? fmtN(s.sak_kosong) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Rusak menunggu retur</p><p className="text-2xl font-semibold">{s ? fmtN(s.sak_rusak_belum_retur) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Kas kecil</p><p className="text-2xl font-semibold">{s ? fmtRp(s.kas) : "…"}</p></div>
      </div>
      {bolehTulis ? (
        <KartuInput judul="Catat mutasi sak">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
            <Field label="Jenis"><Select value={f.jenis} onValueChange={(v) => setF({ ...f, jenis: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="beli">Beli sak bekas</SelectItem><SelectItem value="rusak">Rusak (tunggu retur)</SelectItem><SelectItem value="retur">Retur ke pemasok</SelectItem></SelectContent></Select></Field>
            <Field label="Jumlah sak"><Input type="number" inputMode="numeric" value={f.jumlah} onChange={(e) => setF({ ...f, jumlah: e.target.value })} /></Field>
            {f.jenis === "beli" ? (<>
              <Field label="Pemasok sak"><Select value={f.pemasok_id} onValueChange={(v) => setF({ ...f, pemasok_id: v })}><SelectTrigger><SelectValue placeholder="Pilih" /></SelectTrigger>
                <SelectContent>{(pemasok.data ?? []).filter((p) => p.jenis === "sak").map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.nama}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Harga per sak (Rp)"><Input type="number" inputMode="numeric" value={f.harga} onChange={(e) => setF({ ...f, harga: e.target.value })} /></Field>
              <Field label="Foto nota (ref)"><Input placeholder="nama file / link" value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} /></Field>
            </>) : null}
            <Field label="Keterangan"><Input value={f.ket} onChange={(e) => setF({ ...f, ket: e.target.value })} /></Field>
            <div className="flex items-end sm:col-span-2 lg:col-span-4"><Button onClick={simpan} disabled={sibuk}>Simpan {f.jenis}{f.jenis === "beli" && f.jumlah && f.harga ? ` — ${fmtRp(Number(f.jumlah) * Number(f.harga))}` : ""}</Button></div>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul="Mutasi sak kosong" aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Jenis</TableHead><TableHead className="text-right">Jumlah</TableHead><TableHead className="text-right">Δ saldo</TableHead><TableHead className="text-right">Harga/sak</TableHead><TableHead>Keterangan</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell><Badge variant="outline">{r.jenis}</Badge></TableCell><TableCell className="text-right">{r.jumlah}</TableCell>
                <TableCell className={"text-right font-medium " + (r.delta < 0 ? "text-destructive" : "")}>{r.delta > 0 ? "+" : ""}{r.delta}</TableCell><TableCell className="text-right">{r.harga_per_sak ? fmtRp(r.harga_per_sak) : "—"}</TableCell>
                <TableCell className="max-w-[240px] truncate text-xs">{r.keterangan ?? "—"}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right">{r.jenis === "dipakai" || r.jenis === "opname" ? null : <TombolBatal path="/ops/sak" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} />}</TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
