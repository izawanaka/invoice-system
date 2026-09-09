"use client";

// /pabrik/karyawan -- Karyawan (owner): kepala & gaji effective-dated (P9). Kenaikan gaji = baris baru.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, Kosong, errMsg, fmtRp, fmtTgl, today, useLoad, usePeran } from "@/components/pabrik/ui";
import { karyawanBaru, listKaryawan } from "@/lib/pabrik-api";
import { listUsers } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function KaryawanPage() {
  const { isOwner } = usePeran();
  const kar = useLoad(() => (isOwner ? listKaryawan() : Promise.resolve([])), [isOwner]);
  const users = useLoad(() => (isOwner ? listUsers() : Promise.resolve([])), [isOwner]);
  const [f, setF] = React.useState({ nama: "", peran: "kepala", gaji: "", makan: "", user_id: "", mulai: today(), cat: "" });
  const [sibuk, setSibuk] = React.useState(false);
  async function simpan() {
    if (f.nama.trim().length < 2) return toast.error("Nama minimal 2 huruf");
    setSibuk(true);
    try { await karyawanBaru({ nama: f.nama.trim(), peran: f.peran, gaji_pokok: f.gaji ? Number(f.gaji) : 0, uang_makan: f.makan ? Number(f.makan) : 0, user_id: f.user_id ? Number(f.user_id) : undefined, berlaku_mulai: f.mulai, catatan: f.cat || undefined }); toast.success("Karyawan disimpan"); setF((s) => ({ ...s, nama: "", gaji: "", makan: "", cat: "" })); kar.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  if (!isOwner) return <Halaman judul="Karyawan" kembali="/pabrik/modul/harian"><p className="text-sm text-muted-foreground">Halaman ini hanya untuk Owner.</p></Halaman>;
  const akunKepala = (users.data ?? []).filter((u) => u.role === "kepala");
  return (
    <Halaman judul="Karyawan" desc="Kepala pabrik ditautkan ke akun login supaya bisa melihat rekap bonus miliknya. Perubahan gaji = baris baru mulai tanggal tertentu." kembali="/pabrik/modul/harian">
      <KartuInput judul="Tambah / perbarui">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Nama"><Input value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} /></Field>
          <Field label="Peran"><Select value={f.peran} onValueChange={(v) => setF({ ...f, peran: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="kepala">Kepala</SelectItem><SelectItem value="buruh">Buruh</SelectItem><SelectItem value="langsir">Langsir</SelectItem><SelectItem value="supir">Supir</SelectItem></SelectContent></Select></Field>
          <Field label="Gaji pokok (Rp)"><Input type="number" inputMode="numeric" value={f.gaji} onChange={(e) => setF({ ...f, gaji: e.target.value })} /></Field>
          <Field label="Uang makan (Rp)"><Input type="number" inputMode="numeric" value={f.makan} onChange={(e) => setF({ ...f, makan: e.target.value })} /></Field>
          {f.peran === "kepala" ? <Field label="Akun login kepala"><Select value={f.user_id} onValueChange={(v) => setF({ ...f, user_id: v })}><SelectTrigger><SelectValue placeholder="(opsional)" /></SelectTrigger><SelectContent>{akunKepala.map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.nama} ({u.username ?? u.email})</SelectItem>)}</SelectContent></Select></Field> : null}
          <Field label="Berlaku mulai"><Input type="date" value={f.mulai} onChange={(e) => setF({ ...f, mulai: e.target.value })} /></Field>
          <Field label="Catatan"><Input value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} /></Field>
          <div className="flex items-end"><Button onClick={simpan} disabled={sibuk}>Simpan</Button></div>
        </div>
      </KartuInput>
      <KartuRekap judul="Daftar karyawan">
        {(kar.data ?? []).length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Nama</TableHead><TableHead>Peran</TableHead><TableHead className="text-right">Gaji pokok</TableHead><TableHead className="text-right">Uang makan</TableHead><TableHead>Berlaku</TableHead><TableHead>Akun</TableHead></TableRow></TableHeader>
            <TableBody>{(kar.data ?? []).map((k) => <TableRow key={k.id}><TableCell className="font-medium">{k.nama}</TableCell><TableCell><Badge variant="outline">{k.peran}</Badge></TableCell><TableCell className="text-right">{fmtRp(k.gaji_pokok)}</TableCell><TableCell className="text-right">{fmtRp(k.uang_makan)}</TableCell><TableCell className="text-xs">{fmtTgl(k.berlaku_mulai)} – {k.berlaku_sampai ? fmtTgl(k.berlaku_sampai) : "…"}</TableCell><TableCell className="text-xs">{k.user_id ? (users.data ?? []).find((u) => u.id === k.user_id)?.nama ?? `#${k.user_id}` : "—"}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
