"use client";

// /pabrik/hpp -- HPP Bulanan (owner): (kas keluar bernota + upah + beli sak) ÷ sak lolos QC. Kas tanpa nota dipisah (A5).
import { Halaman, KartuRekap, Kosong, fmtN, fmtRp, useLoad, usePeran } from "@/components/pabrik/ui";
import { listHpp } from "@/lib/pabrik-api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function HppPage() {
  const { isOwner } = usePeran();
  const hpp = useLoad(listHpp, []);
  if (!isOwner) return <Halaman judul="HPP Bulanan" kembali="/pabrik/modul/kas"><p className="text-sm text-muted-foreground">Halaman ini hanya untuk Owner.</p></Halaman>;
  const rows = hpp.data ?? [];
  return (
    <Halaman judul="HPP Bulanan" desc="Biaya kas kecil (bernota + upah + beli sak) dibagi sak lolos QC bulan itu. Harga jual tidak pernah masuk workspace ini." kembali="/pabrik/modul/kas">
      <KartuRekap judul="Per bulan">
        {rows.length === 0 ? <Kosong /> : (
          <Table><TableHeader><TableRow><TableHead>Bulan</TableHead><TableHead className="text-right">Biaya masuk HPP</TableHead><TableHead className="text-right">Kas tanpa nota (dikecualikan)</TableHead><TableHead className="text-right">Sak lolos QC</TableHead><TableHead className="text-right">HPP / sak</TableHead></TableRow></TableHeader>
            <TableBody>{rows.map((r) => <TableRow key={r.bulan}><TableCell className="font-medium">{r.bulan}</TableCell><TableCell className="text-right">{fmtRp(r.biaya_kas)}</TableCell><TableCell className="text-right text-muted-foreground">{fmtRp(r.biaya_tanpa_nota)}</TableCell><TableCell className="text-right">{fmtN(r.sak_lolos_qc)}</TableCell><TableCell className="text-right font-semibold">{r.hpp_per_sak === null ? "— (belum ada sak lolos QC)" : fmtRp(r.hpp_per_sak)}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
