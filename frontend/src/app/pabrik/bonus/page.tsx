"use client";

// /pabrik/bonus -- Rekap Bonus (B6, Konsep B) + triwulan. Kepala hanya melihat miliknya; owner membekukan (P8) dan membayar triwulan.
import * as React from "react";
import { toast } from "sonner";
import { Lock } from "lucide-react";

import { Halaman, KartuRekap, Field, Kosong, errMsg, fmtN, fmtRp, fmtTgl, today, bulanIni, useLoad, usePeran } from "@/components/pabrik/ui";
import { bayarTriwulan, bekukan, listKaryawan, rekapBonus, triwulan, type Karyawan } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const Q = (b: string) => `${b.slice(0, 4)}-Q${Math.floor((Number(b.slice(5, 7)) - 1) / 3) + 1}`;

export default function BonusPage() {
  const { isOwner } = usePeran();
  const [bulan, setBulan] = React.useState(bulanIni());
  const rekap = useLoad(() => rekapBonus(bulan), [bulan]);
  const tw = useLoad(() => triwulan(Q(bulan)), [bulan]);
  const kar = useLoad(() => (isOwner ? listKaryawan() : Promise.resolve([] as Karyawan[])), [isOwner]);
  const nama = (id: number) => kar.data?.find((k) => k.id === id)?.nama ?? `Kepala #${id}`;
  const [sibuk, setSibuk] = React.useState(false);
  async function beku(kid: number) {
    if (!confirm(`Bekukan rekap ${bulan}? Setelah dibekukan tidak dihitung ulang (P8).`)) return;
    setSibuk(true);
    try { await bekukan(bulan, kid); toast.success("Rekap dibekukan"); rekap.reload(); tw.reload(); } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  async function bayar(kid: number) {
    setSibuk(true);
    try { const r = await bayarTriwulan({ periode: Q(bulan), karyawan_id: kid, tanggal_bayar: today() }); toast.success(`Pembayaran ${fmtRp(r.total)} dicatat`); tw.reload(); } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = rekap.data ?? [];
  return (
    <Halaman judul="Rekap Bonus" desc="Sak Netto = sak dari BAP tertaut − potongan. Bonus jenjang marjinal × pengali klaim. Bulan tanpa BAP = bonus 0 (Konsep B)." kembali="/pabrik/modul/kirim"
      aksi={<Field label="Bulan"><Input type="month" value={bulan} onChange={(e) => setBulan(e.target.value)} className="h-8" /></Field>}>
      {rows.length === 0 ? <KartuRekap judul={`Rekap ${bulan}`}><Kosong teks={rekap.loading ? "Memuat…" : "Belum ada kepala aktif / rekap untuk bulan ini"} /></KartuRekap> : rows.map((r) => (
        <KartuRekap key={r.id} judul={`${nama(r.karyawan_id)} · ${r.bulan}`} desc={r.status === "menunggu_parameter" ? "Menunggu parameter sak per m³ (KKS) dari owner" : r.status === "dibekukan" ? "Dibekukan — angka final" : "Draft — dihitung ulang setiap dibuka"}
          aksi={<div className="flex items-center gap-2"><Badge variant={r.status === "dibekukan" ? "default" : r.status === "menunggu_parameter" ? "warning" : "outline"}>{r.status}</Badge>{isOwner && r.status === "draft" ? <Button size="sm" onClick={() => beku(r.karyawan_id)} disabled={sibuk} className="gap-1"><Lock className="h-3.5 w-3.5" /> Bekukan</Button> : null}</div>}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8 text-sm">
            {[["Sak dari BAP", fmtN(r.sak_bap)], ["Sak dikirim", fmtN(r.sak_dikirim)], ["Potongan", fmtN(r.potongan)], ["Sak netto", fmtN(r.sak_netto)], ["Sisa negatif", fmtN(r.sisa_negatif)], ["Klaim", `${fmtN(r.sak_klaim)} (${fmtN(r.pct_klaim, 2)}%)`], ["Pengali", String(r.pengali)], ["Bonus jenjang", fmtRp(r.bonus_jenjang)]].map(([l, v]) => (
              <div key={l} className="rounded-md border p-2"><p className="text-[11px] text-muted-foreground">{l}</p><p className="font-semibold">{v}</p></div>))}
          </div>
          <p className="mt-3 text-lg">Bonus bulan: <b>{fmtRp(r.bonus_bulan)}</b>{r.m3_kks_tanpa_konversi ? <span className="ml-2 text-xs text-muted-foreground">({fmtN(r.m3_kks_tanpa_konversi, 2)} m³ KKS belum dikonversi)</span> : null}</p>
        </KartuRekap>))}
      <KartuRekap judul={`Triwulan ${Q(bulan)}`} desc="Dibayar paling lambat tanggal 15 bulan pertama triwulan berikutnya, hanya bila 3 bulan sudah dibekukan.">
        {(tw.data ?? []).length === 0 ? <Kosong teks="Belum ada rekap di triwulan ini" /> : (
          <Table><TableHeader><TableRow><TableHead>Kepala</TableHead><TableHead>Bulan</TableHead><TableHead className="text-right">Total beku</TableHead><TableHead>Pembayaran</TableHead>{isOwner ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{(tw.data ?? []).map((t) => <TableRow key={t.karyawan_id}><TableCell className="font-medium">{nama(t.karyawan_id)}</TableCell><TableCell className="text-xs">{t.bulan.map((b) => `${b.bulan} ${fmtRp(b.bonus)} (${b.status === "dibekukan" ? "beku" : b.status})`).join(" · ")}</TableCell><TableCell className="text-right font-semibold">{fmtRp(t.total_dibekukan)}</TableCell><TableCell>{t.dibayar ? <Badge variant="success">dibayar {fmtTgl(t.dibayar.tanggal)}</Badge> : t.semua_dibekukan ? <Badge variant="warning">siap dibayar</Badge> : <Badge variant="outline">belum lengkap</Badge>}</TableCell>{isOwner ? <TableCell className="text-right">{!t.dibayar && t.semua_dibekukan ? <Button size="sm" onClick={() => bayar(t.karyawan_id)} disabled={sibuk}>Catat pembayaran</Button> : null}</TableCell> : null}</TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
