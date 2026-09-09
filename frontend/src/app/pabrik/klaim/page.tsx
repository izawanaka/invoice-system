"use client";

// /pabrik/klaim -- Klaim & Potongan (B6, owner). Klaim mutu 2x / angkut 1x -> potongan otomatis di bulan BAP.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { klaimBaru, listKlaim, listPengiriman, listPotongan, potonganBaru } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function KlaimPage() {
  const { isOwner } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const klaim = useLoad(() => listKlaim(bulan), [bulan]);
  const potongan = useLoad(() => listPotongan(bulan), [bulan]);
  const sj = useLoad(() => listPengiriman(), []);
  const [k, setK] = React.useState({ tanggal: today(), sj: "", sak: "", jenis: "mutu", bukti: "", ket: "" });
  const [p, setP] = React.useState({ bulan: bulanIni(), sebab: "manual", sak: "", ket: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpanKlaim() {
    if (!k.sj || !k.sak) return toast.error("Surat jalan dan jumlah sak wajib");
    setSibuk(true);
    try { const r = await klaimBaru({ tanggal_terima: k.tanggal, pengiriman_id: Number(k.sj), jumlah_sak_diklaim: Number(k.sak), jenis: k.jenis, bukti: k.bukti || undefined, keterangan: k.ket || undefined });
      toast.success(`Klaim dicatat → potongan ${r.potongan_sak} sak di ${r.bulan_potongan}`); setK((s) => ({ ...s, sak: "", bukti: "", ket: "" })); klaim.reload(); potongan.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  async function simpanPotongan() {
    if (!p.sak || p.ket.length < 3) return toast.error("Sak dan keterangan (≥3 huruf) wajib");
    setSibuk(true);
    try { await potonganBaru({ bulan: p.bulan, sebab: p.sebab, sak: Number(p.sak), keterangan: p.ket }); toast.success("Potongan dicatat"); setP((s) => ({ ...s, sak: "", ket: "" })); potongan.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  if (!isOwner) return <Halaman judul="Klaim & Potongan" kembali="/pabrik/modul/kirim"><p className="text-sm text-muted-foreground">Halaman ini hanya untuk Owner. Kepala melihat efeknya di Rekap Bonus.</p></Halaman>;
  const sjTertaut = (sj.data ?? []).filter((s) => s.bap_tertaut && !s.dibatalkan);
  return (
    <Halaman judul="Klaim & Potongan" desc="Klaim dari pembeli (mutu = potongan 2×, angkut = 1×) dan potongan lain (susut, opname, lot rusak). Ditolak bila rekap bulan itu sudah dibekukan (P8)." kembali="/pabrik/modul/kirim">
      <div className="grid gap-4 lg:grid-cols-2">
        <KartuInput judul="Catat klaim">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Tanggal terima klaim"><Input type="date" value={k.tanggal} onChange={(e) => setK({ ...k, tanggal: e.target.value })} /></Field>
            <Field label="Surat jalan (tertaut BAP)"><Select value={k.sj} onValueChange={(v) => setK({ ...k, sj: v })}><SelectTrigger><SelectValue placeholder="Pilih SJ" /></SelectTrigger>
              <SelectContent>{sjTertaut.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.no_surat_jalan} · {fmtTgl(s.tanggal)} · {s.jumlah_sak} sak · BAP {s.no_bap}</SelectItem>)}</SelectContent></Select></Field>
            <Field label="Sak diklaim"><Input type="number" inputMode="numeric" value={k.sak} onChange={(e) => setK({ ...k, sak: e.target.value })} /></Field>
            <Field label="Jenis"><Select value={k.jenis} onValueChange={(v) => setK({ ...k, jenis: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="mutu">Mutu (potongan 2×)</SelectItem><SelectItem value="angkut">Angkut (potongan 1×)</SelectItem></SelectContent></Select></Field>
            <Field label="Bukti (ref)"><Input value={k.bukti} onChange={(e) => setK({ ...k, bukti: e.target.value })} /></Field>
            <Field label="Keterangan"><Input value={k.ket} onChange={(e) => setK({ ...k, ket: e.target.value })} /></Field>
            <div className="sm:col-span-2"><Button onClick={simpanKlaim} disabled={sibuk}>Simpan klaim</Button></div>
          </div>
        </KartuInput>
        <KartuInput judul="Potongan lain">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Bulan"><Input type="month" value={p.bulan} onChange={(e) => setP({ ...p, bulan: e.target.value })} /></Field>
            <Field label="Sebab"><Select value={p.sebab} onValueChange={(v) => setP({ ...p, sebab: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="susut">Susut</SelectItem><SelectItem value="opname_sak">Opname sak</SelectItem><SelectItem value="lot_rusak">Lot rusak</SelectItem><SelectItem value="manual">Manual</SelectItem></SelectContent></Select></Field>
            <Field label="Sak"><Input type="number" inputMode="numeric" value={p.sak} onChange={(e) => setP({ ...p, sak: e.target.value })} /></Field>
            <Field label="Keterangan"><Input value={p.ket} onChange={(e) => setP({ ...p, ket: e.target.value })} /></Field>
            <div className="sm:col-span-2"><Button onClick={simpanPotongan} disabled={sibuk} variant="secondary">Simpan potongan</Button></div>
          </div>
        </KartuInput>
      </div>
      <KartuRekap judul="Klaim" aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {(klaim.data ?? []).length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>SJ</TableHead><TableHead>Jenis</TableHead><TableHead className="text-right">Sak klaim</TableHead><TableHead className="text-right">Potongan</TableHead><TableHead>Ket</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{(klaim.data ?? []).map((r) => <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}><TableCell>{fmtTgl(r.tanggal_terima)}</TableCell><TableCell>{r.no_surat_jalan}</TableCell><TableCell><Badge variant={r.jenis === "mutu" ? "destructive" : "warning"}>{r.jenis}</Badge></TableCell><TableCell className="text-right">{r.jumlah_sak_diklaim}</TableCell><TableCell className="text-right font-medium">{r.potongan_sak}</TableCell><TableCell className="text-xs">{r.keterangan ?? "—"}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell><TableCell className="text-right"><TombolBatal path="/ops/klaim" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { klaim.reload(); potongan.reload(); }} /></TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
      <KartuRekap judul="Potongan bulan terpilih" desc="Potongan klaim & carry-over dibatalkan lewat sumbernya.">
        {(potongan.data ?? []).length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Bulan</TableHead><TableHead>Sebab</TableHead><TableHead className="text-right">Sak</TableHead><TableHead>Rujukan</TableHead><TableHead>Ket</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{(potongan.data ?? []).map((r) => <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}><TableCell>{r.bulan}</TableCell><TableCell><Badge variant="outline">{r.sebab}</Badge></TableCell><TableCell className="text-right font-medium">{r.sak}</TableCell><TableCell className="text-xs">{r.ref_tabel ? `${r.ref_tabel}#${r.ref_id}` : "—"}</TableCell><TableCell className="text-xs">{r.keterangan ?? "—"}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell><TableCell className="text-right">{["klaim_mutu", "klaim_angkut", "carry_over"].includes(r.sebab) ? null : <TombolBatal path="/ops/potongan" id={r.id} dibatalkan={r.dibatalkan} onDone={potongan.reload} />}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
