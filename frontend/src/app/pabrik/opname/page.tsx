"use client";

// /pabrik/opname -- Stock Opname (B7, owner). Selisih != 0 -> ledger 'opname' dibuat sistem; audit A3/A4 mengusulkan potongan.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtTgl, today, useLoad, usePeran } from "@/components/pabrik/ui";
import { getSaldo, listLot, listOpname, opnameBaru } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function OpnamePage() {
  const { isOwner } = usePeran();
  const daftar = useLoad(() => listOpname(), []);
  const saldo = useLoad(getSaldo, []);
  const lot = useLoad(() => listLot(true), []);
  const [f, setF] = React.useState({ tanggal: today(), jenis: "sak_kosong", lot_id: "", nilai: "", saksi: "", foto: "", cat: "" });
  const [sibuk, setSibuk] = React.useState(false);
  const sistem = f.jenis === "sak_kosong" ? saldo.data?.sak_kosong : f.jenis === "stok_jadi" ? saldo.data?.stok_jadi : (lot.data ?? []).find((l) => String(l.lot_id) === f.lot_id)?.sisa_wip_estimasi_kubik;
  async function simpan() {
    if (f.nilai === "") return toast.error("Isi nilai terukur");
    if (f.jenis === "petak" && !f.lot_id) return toast.error("Pilih lot");
    setSibuk(true);
    try {
      const r = await opnameBaru({ tanggal: f.tanggal, jenis: f.jenis, objek_id: f.jenis === "petak" ? Number(f.lot_id) : undefined, nilai_terukur: Number(f.nilai), disaksikan_oleh: f.saksi || undefined, berita_acara_foto: f.foto || undefined, catatan: f.cat || undefined });
      toast.success(`Opname ${r.jenis}: selisih ${r.selisih > 0 ? "+" : ""}${fmtN(r.selisih, 2)}${r.ref_mutasi_id ? " (saldo disesuaikan)" : ""}`);
      setF((s) => ({ ...s, nilai: "", cat: "" })); daftar.reload(); saldo.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  if (!isOwner) return <Halaman judul="Stock Opname" kembali="/pabrik/modul/produksi"><p className="text-sm text-muted-foreground">Stock opname hanya dilakukan owner (DESIGN-PABRIK §1).</p></Halaman>;
  const rows = daftar.data ?? [];
  return (
    <Halaman judul="Stock Opname" desc="Hitung fisik, sistem mencatat selisih. Sak kosong / stok jadi: selisih langsung menjadi baris ledger. Petak: hanya dicatat (WIP tidak diukur, K9)." kembali="/pabrik/modul/produksi">
      <KartuInput judul="Catat hasil hitung fisik">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
          <Field label="Objek"><Select value={f.jenis} onValueChange={(v) => setF({ ...f, jenis: v })}><SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="sak_kosong">Sak kosong</SelectItem><SelectItem value="stok_jadi">Stok jadi</SelectItem><SelectItem value="petak">Petak / WIP lot (kubik)</SelectItem></SelectContent></Select></Field>
          {f.jenis === "petak" ? <Field label="Lot aktif"><Select value={f.lot_id} onValueChange={(v) => setF({ ...f, lot_id: v })}><SelectTrigger><SelectValue placeholder="Pilih" /></SelectTrigger>
            <SelectContent>{(lot.data ?? []).map((l) => <SelectItem key={l.lot_id} value={String(l.lot_id)}>{l.petak} · {l.nomor_lot} ({l.status})</SelectItem>)}</SelectContent></Select></Field> : null}
          <Field label={f.jenis === "petak" ? "Terukur (kubik)" : "Terhitung fisik (sak)"} hint={`Sistem: ${sistem === undefined || sistem === null ? "—" : fmtN(sistem, 2)}`}><Input type="number" step={f.jenis === "petak" ? "0.01" : "1"} inputMode="decimal" value={f.nilai} onChange={(e) => setF({ ...f, nilai: e.target.value })} /></Field>
          <Field label="Disaksikan oleh"><Input value={f.saksi} onChange={(e) => setF({ ...f, saksi: e.target.value })} /></Field>
          <Field label="Foto berita acara (ref)"><Input value={f.foto} onChange={(e) => setF({ ...f, foto: e.target.value })} /></Field>
          <Field label="Catatan"><Input value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} /></Field>
          <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan opname{f.nilai !== "" && sistem !== undefined && sistem !== null ? ` (selisih ${fmtN(Number(f.nilai) - sistem, 2)})` : ""}</Button></div>
        </div>
      </KartuInput>
      <KartuRekap judul="Riwayat opname">
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Objek</TableHead><TableHead className="text-right">Fisik</TableHead><TableHead className="text-right">Sistem</TableHead><TableHead className="text-right">Selisih</TableHead><TableHead>Saksi</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell><Badge variant="outline">{r.jenis}</Badge> {r.objek ?? ""}</TableCell><TableCell className="text-right">{fmtN(r.nilai_terukur, 2)}</TableCell><TableCell className="text-right">{fmtN(r.nilai_sistem, 2)}</TableCell>
                <TableCell className={"text-right font-medium " + (r.selisih < 0 ? "text-destructive" : r.selisih > 0 ? "text-success" : "")}>{r.selisih > 0 ? "+" : ""}{fmtN(r.selisih, 2)}</TableCell><TableCell className="text-xs">{r.disaksikan_oleh ?? "—"}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                <TableCell className="text-right"><TombolBatal path="/ops/opname" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} /></TableCell>
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
