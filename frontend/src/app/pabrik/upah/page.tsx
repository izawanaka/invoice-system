"use client";

// /pabrik/upah -- Upah Harian (B4, K7): buruh/langsir/supir, tarif snapshot, otomatis kas keluar kategori upah.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtRp, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { getSaldo, listUpah, upahBaru } from "@/lib/pabrik-api";
import { listParameter } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function UpahPage() {
  const { bolehTulis } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listUpah(bulan), [bulan]);
  const saldo = useLoad(getSaldo, []);
  const param = useLoad(() => listParameter(), []);
  const [f, setF] = React.useState({ tanggal: today(), nama: "", peran: "buruh", satuan: "hari", jumlah: "1", tarif: "", cat: "" });
  const [sibuk, setSibuk] = React.useState(false);
  const tarifParam = param.data?.find((p) => p.kode === `upah_${f.peran}`)?.nilai ?? null;
  const tarifPakai = f.tarif ? Number(f.tarif) : tarifParam;
  async function simpan() {
    if (!f.nama || !f.jumlah) return toast.error("Nama dan jumlah wajib");
    if (!tarifPakai) return toast.error("Tarif belum ada di parameter — isi tarif manual");
    setSibuk(true);
    try {
      const r = await upahBaru({ tanggal: f.tanggal, nama: f.nama.trim(), peran: f.peran, satuan: f.satuan, jumlah: Number(f.jumlah), tarif: f.tarif ? Number(f.tarif) : undefined, catatan: f.cat || undefined });
      toast.success(`Upah ${r.nama} ${fmtRp(r.total)} dicatat, kas keluar otomatis`);
      setF((s) => ({ ...s, nama: "", jumlah: "1", cat: "" })); daftar.reload(); saldo.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = daftar.data ?? [];
  const total = rows.filter((r) => !r.dibatalkan).reduce((a, r) => a + r.total, 0);
  return (
    <Halaman judul="Upah Harian" desc="Buruh, langsir, dan supir jemput sabut dibayar dari kas kecil (K7). Tarif diambil dari parameter, boleh ditimpa manual." kembali="/pabrik/modul/kas">
      {bolehTulis ? (
        <KartuInput judul="Catat upah" desc={`Kas kecil: ${saldo.data ? fmtRp(saldo.data.kas) : "…"}`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
            <Field label="Nama"><Input value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} /></Field>
            <Field label="Peran"><Select value={f.peran} onValueChange={(v) => setF({ ...f, peran: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="buruh">Buruh</SelectItem><SelectItem value="langsir">Langsir</SelectItem><SelectItem value="supir">Supir jemput</SelectItem></SelectContent></Select></Field>
            <Field label="Satuan"><Select value={f.satuan} onValueChange={(v) => setF({ ...f, satuan: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="hari">Per hari</SelectItem><SelectItem value="rit">Per rit</SelectItem></SelectContent></Select></Field>
            <Field label={`Jumlah ${f.satuan}`}><Input type="number" step="0.5" inputMode="decimal" value={f.jumlah} onChange={(e) => setF({ ...f, jumlah: e.target.value })} /></Field>
            <Field label="Tarif (Rp)" hint={tarifParam ? `Parameter: ${fmtRp(tarifParam)}` : "Parameter belum diisi owner"}><Input type="number" inputMode="numeric" placeholder={tarifParam ? String(tarifParam) : ""} value={f.tarif} onChange={(e) => setF({ ...f, tarif: e.target.value })} /></Field>
            <Field label="Catatan"><Input value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} /></Field>
            <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan{tarifPakai && f.jumlah ? ` — ${fmtRp(tarifPakai * Number(f.jumlah))}` : ""}</Button></div>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul="Rekap upah" desc={`Total ${fmtRp(total)}`} aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Nama</TableHead><TableHead>Peran</TableHead><TableHead className="text-right">Jumlah</TableHead><TableHead className="text-right">Tarif</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell className="font-medium">{r.nama}</TableCell><TableCell className="capitalize">{r.peran}</TableCell><TableCell className="text-right">{fmtN(r.jumlah, 1)} {r.satuan}</TableCell><TableCell className="text-right">{fmtRp(r.tarif)}</TableCell><TableCell className="text-right font-medium">{fmtRp(r.total)}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right"><TombolBatal path="/ops/upah" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} /></TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
