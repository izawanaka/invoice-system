"use client";

// /pabrik/stok -- Saldo & Mutasi Stok (rekap): sak kosong + stok jadi + opname terakhir.
import * as React from "react";
import { Halaman, KartuRekap, Kosong, fmtN, fmtTgl, useLoad } from "@/components/pabrik/ui";
import { getSaldo, listOpname, listPengiriman, listProduksi } from "@/lib/pabrik-api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function StokPage() {
  const saldo = useLoad(getSaldo, []);
  const opname = useLoad(() => listOpname(), []);
  const prod = useLoad(() => listProduksi(), []);
  const kirim = useLoad(() => listPengiriman(), []);
  const s = saldo.data;
  const gerak = [
    ...(prod.data ?? []).filter((p) => !p.dibatalkan).map((p) => ({ k: `p${p.id}`, tanggal: p.tanggal, jenis: "produksi", ket: `Lot ${p.nomor_lot} · QC ${p.status_qc}`, delta: p.jumlah_sak })),
    ...(kirim.data ?? []).filter((p) => !p.dibatalkan).map((p) => ({ k: `k${p.id}`, tanggal: p.tanggal, jenis: "kirim", ket: `SJ ${p.no_surat_jalan} → ${p.tujuan_kode}${p.no_bap ? ` · BAP ${p.no_bap}` : ""}`, delta: -p.jumlah_sak })),
    ...(opname.data ?? []).filter((o) => !o.dibatalkan && o.jenis === "stok_jadi").map((o) => ({ k: `o${o.id}`, tanggal: o.tanggal, jenis: "opname", ket: `fisik ${fmtN(o.nilai_terukur)} vs sistem ${fmtN(o.nilai_sistem)}`, delta: o.selisih })),
  ].sort((a, b) => (a.tanggal < b.tanggal ? 1 : -1)).slice(0, 100);
  return (
    <Halaman judul="Saldo & Mutasi Stok" desc="Saldo = jumlah ledger (P2), tidak pernah diedit langsung. Koreksi hanya lewat stock opname owner." kembali="/pabrik/modul/produksi">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Sak kosong</p><p className="text-2xl font-semibold">{s ? fmtN(s.sak_kosong) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Rusak tunggu retur</p><p className="text-2xl font-semibold">{s ? fmtN(s.sak_rusak_belum_retur) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Stok jadi (sak)</p><p className="text-2xl font-semibold">{s ? fmtN(s.stok_jadi) : "…"}</p></div>
        <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Opname terakhir</p><p className="text-sm font-semibold">{opname.data?.[0] ? `${fmtTgl(opname.data[0].tanggal)} · ${opname.data[0].jenis}` : "belum pernah"}</p></div>
      </div>
      <KartuRekap judul="Pergerakan stok jadi" desc="Produksi (+), pengiriman (−), opname (±). 100 baris terakhir.">
        {gerak.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Tanggal</TableHead><TableHead>Jenis</TableHead><TableHead>Keterangan</TableHead><TableHead className="text-right">Sak</TableHead></TableRow></TableHeader>
            <TableBody>{gerak.map((g) => <TableRow key={g.k}><TableCell>{fmtTgl(g.tanggal)}</TableCell><TableCell className="capitalize">{g.jenis}</TableCell><TableCell className="text-xs">{g.ket}</TableCell><TableCell className={"text-right font-medium " + (g.delta < 0 ? "text-destructive" : "")}>{g.delta > 0 ? "+" : ""}{fmtN(g.delta)}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
