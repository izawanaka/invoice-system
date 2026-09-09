"use client";

// /pabrik/produksi -- Produksi Sak (B3). P4: satu transaksi atomik (sak kosong −N, stok jadi +N). QC 5 sampel berat.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { getSaldo, listLot, listProduksi, produksiBaru } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const QC: Record<string, "success" | "destructive" | "outline"> = { lolos: "success", gagal: "destructive", belum: "outline" };

export default function ProduksiPage() {
  const { bolehTulis } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listProduksi(bulan), [bulan]);
  const lot = useLoad(() => listLot(true), []);
  const saldo = useLoad(getSaldo, []);
  const [f, setF] = React.useState({ tanggal: today(), lot_id: "", jumlah_sak: "", sampel: ["", "", "", "", ""], catatan: "" });
  const [sibuk, setSibuk] = React.useState(false);
  const lotSiap = (lot.data ?? []).filter((l) => l.status === "siap_karung");
  async function simpan() {
    if (!f.lot_id || !f.jumlah_sak) return toast.error("Lot dan jumlah sak wajib diisi");
    const sampel = f.sampel.filter((x) => x !== "").map(Number);
    if (sampel.length !== 0 && sampel.length !== 5) return toast.error("Sampel berat harus 5 angka atau kosong semua");
    setSibuk(true);
    try {
      const r = await produksiBaru({ tanggal: f.tanggal, lot_id: Number(f.lot_id), jumlah_sak: Number(f.jumlah_sak), berat_sampel: sampel.length ? sampel : undefined, catatan: f.catatan || undefined });
      toast.success(`${r.jumlah_sak} sak dari lot ${r.nomor_lot} dicatat. QC: ${r.status_qc}`);
      setF((s) => ({ ...s, jumlah_sak: "", sampel: ["", "", "", "", ""], catatan: "" }));
      daftar.reload(); saldo.reload(); lot.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = daftar.data ?? [];
  const total = rows.filter((r) => !r.dibatalkan).reduce((a, r) => a + r.jumlah_sak, 0);
  return (
    <Halaman judul="Produksi Sak" desc="Sak jadi dari lot berstatus siap karung. Sistem mengurangi sak kosong dan menambah stok jadi sekaligus." kembali="/pabrik/modul/produksi">
      {bolehTulis ? (
        <KartuInput judul="Catat produksi" desc={`Sak kosong tersedia: ${saldo.data ? fmtN(saldo.data.sak_kosong) : "…"}. Timbang 5 sak acak untuk QC (lolos bila ≥4 memenuhi berat minimum).`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
            <Field label="Lot (siap karung)" hint={lotSiap.length ? undefined : "Belum ada lot siap karung"}>
              <Select value={f.lot_id} onValueChange={(v) => setF({ ...f, lot_id: v })}><SelectTrigger><SelectValue placeholder="Pilih lot" /></SelectTrigger>
                <SelectContent>{lotSiap.map((l) => <SelectItem key={l.lot_id} value={String(l.lot_id)}>{l.petak} · {l.nomor_lot} ({fmtN(l.kubik_masuk, 1)} kubik)</SelectItem>)}</SelectContent></Select></Field>
            <Field label="Jumlah sak"><Input type="number" inputMode="numeric" value={f.jumlah_sak} onChange={(e) => setF({ ...f, jumlah_sak: e.target.value })} /></Field>
            <Field label="Catatan"><Input value={f.catatan} onChange={(e) => setF({ ...f, catatan: e.target.value })} /></Field>
            <div className="sm:col-span-2 lg:col-span-4"><Field label="Berat 5 sampel (kg)">
              <div className="grid grid-cols-5 gap-2">{f.sampel.map((v, i) => <Input key={i} type="number" step="0.1" inputMode="decimal" placeholder={`#${i + 1}`} value={v} onChange={(e) => { const s = [...f.sampel]; s[i] = e.target.value; setF({ ...f, sampel: s }); }} />)}</div></Field></div>
            <div className="sm:col-span-2 lg:col-span-4"><Button onClick={simpan} disabled={sibuk}>Simpan produksi</Button></div>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul="Rekap produksi" desc={`Total ${fmtN(total)} sak bulan ini`} aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Lot</TableHead><TableHead className="text-right">Sak</TableHead><TableHead>Sampel (kg)</TableHead><TableHead>QC</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell>{r.nomor_lot}</TableCell><TableCell className="text-right font-medium">{r.jumlah_sak}</TableCell>
                <TableCell className="text-xs">{r.berat_sampel?.join(" · ") ?? "—"}</TableCell><TableCell><Badge variant={QC[r.status_qc] ?? "outline"}>{r.status_qc}</Badge></TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right"><TombolBatal path="/ops/produksi" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} /></TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
