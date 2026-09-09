"use client";

// /pabrik/cuaca -- K10: otomatis Open-Meteo Pasangkayu 2x sehari; admin/kepala boleh menambah catatan manual per tanggal.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, Kosong, errMsg, fmtN, fmtTgl, today, useLoad, usePeran } from "@/components/pabrik/ui";
import { cuacaManual, listCuaca } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function CuacaPage() {
  const { bolehTulis } = usePeran();
  const [hari, setHari] = React.useState(14);
  const cuaca = useLoad(() => listCuaca(hari), [hari]);
  const [f, setF] = React.useState({ tanggal: today(), hujan: "", teks: "", cat: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpan() {
    setSibuk(true);
    try { await cuacaManual({ tanggal: f.tanggal, hujan_mm: f.hujan ? Number(f.hujan) : undefined, cuaca_teks: f.teks || undefined, catatan: f.cat || undefined }); toast.success("Catatan cuaca disimpan"); setF((s) => ({ ...s, hujan: "", teks: "", cat: "" })); cuaca.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  return (
    <Halaman judul="Cuaca Pasangkayu" desc="Data otomatis dari Open-Meteo (pagi & sore). Catatan manual dipakai sebagai alasan jemur terganggu (SOP §4)." kembali="/pabrik/modul/harian"
      aksi={<Button variant="outline" size="sm" onClick={() => setHari((h) => (h === 14 ? 60 : 14))}>{hari === 14 ? "60 hari" : "14 hari"}</Button>}>
      {bolehTulis ? (<KartuInput judul="Catatan cuaca manual">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Tanggal"><Input type="date" value={f.tanggal} onChange={(e) => setF({ ...f, tanggal: e.target.value })} /></Field>
          <Field label="Hujan (mm)"><Input type="number" step="0.1" inputMode="decimal" value={f.hujan} onChange={(e) => setF({ ...f, hujan: e.target.value })} /></Field>
          <Field label="Cuaca"><Input placeholder="hujan sore / cerah" value={f.teks} onChange={(e) => setF({ ...f, teks: e.target.value })} /></Field>
          <Field label="Catatan"><Input value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} /></Field>
          <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan</Button></div>
        </div></KartuInput>) : null}
      <KartuRekap judul="Riwayat">
        {(cuaca.data ?? []).length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Sumber</TableHead><TableHead>Cuaca</TableHead><TableHead className="text-right">Hujan (mm)</TableHead><TableHead className="text-right">Suhu maks</TableHead><TableHead>Catatan</TableHead></TableRow></TableHeader>
            <TableBody>{(cuaca.data ?? []).map((c, i) => <TableRow key={i}><TableCell>{fmtTgl(c.tanggal)}</TableCell><TableCell><Badge variant={c.sumber === "api" ? "outline" : "secondary"}>{c.sumber}</Badge></TableCell><TableCell>{c.cuaca_teks ?? "—"}</TableCell><TableCell className="text-right">{fmtN(c.hujan_mm, 1)}</TableCell><TableCell className="text-right">{c.suhu_max_c === null ? "—" : `${fmtN(c.suhu_max_c, 1)} °C`}</TableCell><TableCell className="text-xs">{c.catatan ?? "—"}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
