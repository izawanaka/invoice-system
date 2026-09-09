"use client";

// /pabrik/kas -- Kas Kecil (B4). Keluar: admin/kepala/owner. Isi ulang: owner. P5: saldo tidak boleh negatif (server 409).
// A5: kas keluar tanpa foto nota dikecualikan dari HPP -- ditandai di daftar.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, FilterBulan, StatusBatal, TombolBatal, Kosong, errMsg, fmtRp, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { getSaldo, kasBaru, listKas } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function KasPage() {
  const { bolehTulis, isOwner } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const daftar = useLoad(() => listKas(bulan), [bulan]);
  const saldo = useLoad(getSaldo, []);
  const [f, setF] = React.useState({ tanggal: today(), jenis: "keluar", kategori: "bbm", nominal: "", ket: "", nota: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpan() {
    if (!f.nominal) return toast.error("Nominal wajib diisi");
    setSibuk(true);
    try {
      await kasBaru({ tanggal: f.tanggal, jenis: f.jenis, kategori: f.jenis === "keluar" ? f.kategori : undefined, nominal: Number(f.nominal), keterangan: f.ket || undefined, foto_nota: f.nota || undefined });
      toast.success(`${f.jenis === "keluar" ? "Kas keluar" : "Isi ulang"} ${fmtRp(Number(f.nominal))} dicatat`);
      setF((s) => ({ ...s, nominal: "", ket: "", nota: "" })); daftar.reload(); saldo.reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = daftar.data ?? [];
  const aktif = rows.filter((r) => !r.dibatalkan);
  const keluar = aktif.filter((r) => r.jenis === "keluar").reduce((a, r) => a + r.nominal, 0);
  const masuk = aktif.filter((r) => r.jenis === "isi_ulang").reduce((a, r) => a + r.nominal, 0);
  return (
    <Halaman judul="Kas Kecil" desc="Setiap kas keluar sebaiknya ada foto nota; tanpa nota tetap boleh tapi dikecualikan dari HPP dan ditandai audit (A5)." kembali="/pabrik/modul/kas">
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Saldo kas</p><p className="text-xl font-semibold">{saldo.data ? fmtRp(saldo.data.kas) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Keluar bulan ini</p><p className="text-xl font-semibold text-destructive">{fmtRp(keluar)}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Isi ulang bulan ini</p><p className="text-xl font-semibold text-success">{fmtRp(masuk)}</p></div>
      </div>
      {bolehTulis ? (
        <KartuInput judul="Catat kas">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
            <Field label="Jenis"><Select value={f.jenis} onValueChange={(v) => setF({ ...f, jenis: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="keluar">Kas keluar</SelectItem>{isOwner ? <SelectItem value="isi_ulang">Isi ulang (owner)</SelectItem> : null}</SelectContent></Select></Field>
            {f.jenis === "keluar" ? <Field label="Kategori"><Select value={f.kategori} onValueChange={(v) => setF({ ...f, kategori: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="bbm">BBM</SelectItem><SelectItem value="perbaikan">Perbaikan</SelectItem><SelectItem value="konsumsi">Konsumsi</SelectItem><SelectItem value="lain">Lain-lain</SelectItem></SelectContent></Select>
              </Field> : null}
            <Field label="Nominal (Rp)"><Input type="number" inputMode="numeric" value={f.nominal} onChange={(e) => setF({ ...f, nominal: e.target.value })} /></Field>
            <Field label="Keterangan"><Input value={f.ket} onChange={(e) => setF({ ...f, ket: e.target.value })} /></Field>
            {f.jenis === "keluar" ? <Field label="Foto nota (ref)" hint="Kosong = ditandai tanpa nota"><Input value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} /></Field> : null}
            <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan</Button></div>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul="Mutasi kas" desc="Upah harian dan beli sak membuat baris kas otomatis (dibatalkan lewat sumbernya)." aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Jenis</TableHead><TableHead>Kategori</TableHead><TableHead className="text-right">Nominal</TableHead><TableHead>Keterangan</TableHead><TableHead>Nota</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={r.dibatalkan ? "opacity-50" : ""}>
                <TableCell>{fmtTgl(r.tanggal)}</TableCell><TableCell>{r.jenis === "keluar" ? <Badge variant="destructive">keluar</Badge> : <Badge variant="success">isi ulang</Badge>}</TableCell><TableCell className="capitalize">{r.kategori}</TableCell>
                <TableCell className="text-right font-medium">{fmtRp(r.nominal)}</TableCell><TableCell className="max-w-[260px] truncate text-xs">{r.keterangan ?? "—"}</TableCell>
                <TableCell>{r.jenis !== "keluar" || ["upah", "sak"].includes(r.kategori) ? "—" : r.foto_nota ? <Badge variant="outline">ada</Badge> : <Badge variant="warning">tanpa nota</Badge>}</TableCell><TableCell><StatusBatal dibatalkan={r.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right">{["upah", "sak"].includes(r.kategori) || (r.jenis === "isi_ulang" && !isOwner) ? null : <TombolBatal path="/ops/kas" id={r.id} dibatalkan={r.dibatalkan} onDone={() => { daftar.reload(); saldo.reload(); }} />}</TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
