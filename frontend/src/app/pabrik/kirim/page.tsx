"use client";

// /pabrik/kirim -- Surat Jalan (B5). K3: tujuan berupa KODE (T1, T2..), bukan nama PT. Owner menautkan SJ ke BAP di sini juga.
import * as React from "react";
import { toast } from "sonner";
import { Link2, Unlink } from "lucide-react";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { bapPilihan, getSaldo, lepasBap, listPengiriman, pengirimanBaru, tautkanBap, type Pengiriman } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

function DialogTaut({ sj, onDone }: { sj: Pengiriman; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [bulan, setBulan] = React.useState(sj.tanggal.slice(0, 7));
  const bap = useLoad(() => (open ? bapPilihan(bulan) : Promise.resolve([])), [open, bulan]);
  const [bapId, setBapId] = React.useState("");
  const [sibuk, setSibuk] = React.useState(false);
  async function taut() {
    if (!bapId) return toast.error("Pilih BAP");
    setSibuk(true);
    try { await tautkanBap(sj.id, Number(bapId)); toast.success(`SJ ${sj.no_surat_jalan} tertaut BAP`); setOpen(false); onDone(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  return (<>
    <Button size="sm" variant="outline" className="gap-1" onClick={() => setOpen(true)}><Link2 className="h-3.5 w-3.5" /> Tautkan BAP</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent>
      <DialogHeader><DialogTitle>Tautkan SJ {sj.no_surat_jalan} ({sj.jumlah_sak} sak, {sj.tujuan_kode})</DialogTitle><DialogDescription>Hanya owner yang melihat badan usaha di daftar ini. Setelah tertaut, kepala melihat BAP versi pabrik dan rekap bonus menghitungnya.</DialogDescription></DialogHeader>
      <div className="grid gap-3">
        <Field label="Bulan BAP"><Input type="month" value={bulan} onChange={(e) => setBulan(e.target.value)} /></Field>
        <Field label="BAP"><Select value={bapId} onValueChange={setBapId}><SelectTrigger><SelectValue placeholder={bap.loading ? "Memuat…" : "Pilih BAP"} /></SelectTrigger>
          <SelectContent>{(bap.data ?? []).map((b) => <SelectItem key={b.bap_id} value={String(b.bap_id)}>{b.no_bap} · {fmtTgl(b.tgl_bap)} · {fmtN(b.qty)} {b.satuan} · {b.badan_usaha}</SelectItem>)}</SelectContent></Select></Field>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Batal</Button><Button onClick={taut} disabled={sibuk}>Tautkan</Button></DialogFooter>
    </DialogContent></Dialog>
  </>);
}

export default function KirimPage() {
  const { bolehTulis, isOwner } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listPengiriman(bulan), [bulan]);
  const saldo = useLoad(getSaldo, []);
  const [f, setF] = React.useState({ tanggal: today(), sj: "", sak: "", nopol: "", tujuan: "T1", cat: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpan() {
    if (!f.sj || !f.sak || !f.tujuan) return toast.error("No SJ, jumlah sak, dan kode tujuan wajib");
    setSibuk(true);
    try {
      const r = await pengirimanBaru({ tanggal: f.tanggal, no_surat_jalan: f.sj.trim(), jumlah_sak: Number(f.sak), nopol: f.nopol || undefined, tujuan_kode: f.tujuan.trim(), catatan: f.cat || undefined });
      toast.success(`SJ ${r.no_surat_jalan}: ${r.jumlah_sak} sak → ${r.tujuan_kode}`);
      setF((s) => ({ ...s, sj: "", sak: "", nopol: "", cat: "" })); daftar.reload(); saldo.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  async function lepas(sj: Pengiriman) {
    try { await lepasBap(sj.id); toast.success("Tautan BAP dilepas"); daftar.reload(); } catch (e) { toast.error(errMsg(e)); }
  }
  const rows = daftar.data ?? [];
  const total = rows.filter((r) => !r.dibatalkan).reduce((a, r) => a + r.jumlah_sak, 0);
  return (
    <Halaman judul="Surat Jalan" desc="Pengiriman sak keluar pabrik. Tujuan ditulis sebagai kode (T1, T2, …); artinya hanya diketahui owner (K3)." kembali="/pabrik/modul/kirim">
      {bolehTulis ? (
        <KartuInput judul="Catat surat jalan" desc={`Stok jadi tersedia: ${saldo.data ? fmtN(saldo.data.stok_jadi) : "…"} sak`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
            <Field label="No. surat jalan"><Input value={f.sj} onChange={(e) => setF({ ...f, sj: e.target.value })} /></Field>
            <Field label="Jumlah sak"><Input type="number" inputMode="numeric" value={f.sak} onChange={(e) => setF({ ...f, sak: e.target.value })} /></Field>
            <Field label="Kode tujuan" hint="T1, T2, … (bukan nama PT)"><Input value={f.tujuan} onChange={(e) => setF({ ...f, tujuan: e.target.value.toUpperCase() })} /></Field>
            <Field label="Nopol"><Input value={f.nopol} onChange={(e) => setF({ ...f, nopol: e.target.value })} /></Field>
            <Field label="Catatan"><Input value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} /></Field>
            <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan surat jalan</Button></div>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul="Rekap pengiriman" desc={`${fmtN(total)} sak bulan ini`} aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>No SJ</TableHead><TableHead className="text-right">Sak</TableHead><TableHead>Tujuan</TableHead><TableHead>Nopol</TableHead><TableHead>BAP</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell className="font-medium">{r.no_surat_jalan}</TableCell><TableCell className="text-right">{r.jumlah_sak}</TableCell><TableCell><Badge variant="secondary">{r.tujuan_kode}</Badge></TableCell><TableCell className="text-xs">{r.nopol ?? "—"}</TableCell>
                <TableCell>{r.bap_tertaut ? <Badge variant="success">{r.no_bap}</Badge> : <Badge variant="outline">belum tertaut</Badge>}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right"><div className="flex justify-end gap-1">
                  {isOwner && !r.dibatalkan ? (r.bap_tertaut ? <Button size="sm" variant="ghost" className="gap-1" onClick={() => lepas(r)}><Unlink className="h-3.5 w-3.5" /> Lepas</Button> : <DialogTaut sj={r} onDone={daftar.reload} />) : null}
                  {r.bap_tertaut ? null : <TombolBatal path="/ops/pengiriman" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} />}
                </div></TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
