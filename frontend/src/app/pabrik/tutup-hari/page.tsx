"use client";

// /pabrik/tutup-hari -- Tutup Hari (B7): penanda disiplin, tidak mengunci input. Satu per tanggal.
import * as React from "react";
import { toast } from "sonner";
import { CalendarCheck } from "lucide-react";

import { Halaman, KartuInput, KartuRekap, Field, StatusBatal, TombolBatal, Kosong, errMsg, fmtN, fmtRp, fmtTgl, today, useLoad, usePeran } from "@/components/pabrik/ui";
import { listTutupHari, ringkasanHari, tutupHari } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type R = Record<string, unknown>;
const n = (r: R | undefined, k: string) => (typeof r?.[k] === "number" ? (r[k] as number) : 0);

export default function TutupHariPage() {
  const { bolehTulis } = usePeran();
  const [tgl, setTgl] = React.useState(today());
  const [cat, setCat] = React.useState("");
  const pra = useLoad(() => ringkasanHari(tgl), [tgl]);
  const daftar = useLoad(() => listTutupHari(31), []);
  const [sibuk, setSibuk] = React.useState(false);
  const r = pra.data?.ringkasan as R | undefined;
  async function tutup() {
    setSibuk(true);
    try { await tutupHari({ tanggal: tgl, catatan: cat || undefined }); toast.success(`Hari ${fmtTgl(tgl)} ditutup`); setCat(""); pra.reload(); daftar.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const cuaca = r?.cuaca as { teks: string | null; hujan_mm: number | null } | null | undefined;
  return (
    <Halaman judul="Tutup Hari" desc="Menandai hari sudah selesai diinput. Tidak mengunci apa pun — input susulan tetap boleh. Audit pagi memeriksa hari kerja yang tidak ditutup." kembali="/pabrik/modul/harian">
      <KartuInput judul="Ringkasan hari">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr_auto] sm:items-end">
          <Field label="Tanggal"><Input type="date" value={tgl} onChange={(e) => setTgl(e.target.value)} /></Field>
          <Field label="Catatan"><Input value={cat} onChange={(e) => setCat(e.target.value)} placeholder="mis. hujan sore, jemur terhenti" /></Field>
          {bolehTulis ? <Button onClick={tutup} disabled={sibuk || pra.data?.sudah_ditutup} className="gap-1"><CalendarCheck className="h-4 w-4" /> {pra.data?.sudah_ditutup ? "Sudah ditutup" : "Tutup hari"}</Button> : null}
        </div>
        {r ? (
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:grid-cols-6">
            {[["Truk masuk", `${n(r, "truk_masuk")} (${fmtN(n(r, "kubik_masuk"), 1)} kubik)`], ["Produksi", `${n(r, "sak_diproduksi")} sak`], ["Pengiriman", `${n(r, "sak_dikirim")} sak`], ["Kas", `${n(r, "kas")} baris`], ["Upah", `${n(r, "upah")} baris`], ["Tahap lot", `${n(r, "tahap_lot")}`], ["Saldo sak kosong", fmtN(n(r, "saldo_sak_kosong"))], ["Saldo stok jadi", fmtN(n(r, "saldo_stok_jadi"))], ["Saldo kas", fmtRp(n(r, "saldo_kas"))], ["Cuaca", cuaca ? `${cuaca.teks ?? "—"} ${cuaca.hujan_mm ?? 0} mm` : "—"]].map(([l, v]) => (
              <div key={l} className="rounded-md border bg-background p-2"><p className="text-[11px] text-muted-foreground">{l}</p><p className="font-medium">{v}</p></div>))}
          </div>) : null}
        {r && r.ada_input === false ? <p className="mt-2 text-xs text-warning-foreground">Belum ada input sama sekali di tanggal ini.</p> : null}
      </KartuInput>
      <KartuRekap judul="31 hari terakhir">
        {(daftar.data ?? []).length === 0 ? <Kosong teks="Belum pernah tutup hari" /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Truk</TableHead><TableHead>Produksi</TableHead><TableHead>Kirim</TableHead><TableHead>Catatan</TableHead><TableHead>Status</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{(daftar.data ?? []).map((t) => { const rr = t.ringkasan as R; return (
              <TableRow key={t.id} className={t.dibatalkan ? "opacity-50" : ""}><TableCell>{fmtTgl(t.tanggal)}</TableCell><TableCell>{n(rr, "truk_masuk")}</TableCell><TableCell>{n(rr, "sak_diproduksi")} sak</TableCell><TableCell>{n(rr, "sak_dikirim")} sak</TableCell><TableCell className="text-xs">{t.catatan ?? "—"}</TableCell><TableCell><StatusBatal dibatalkan={t.dibatalkan} /></TableCell>
                {bolehTulis ? <TableCell className="text-right"><TombolBatal path="/ops/tutup-hari" id={t.id} dibatalkan={t.dibatalkan} onDone={() => { daftar.reload(); pra.reload(); }} label="Buka lagi" /></TableCell> : null}</TableRow>); })}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
