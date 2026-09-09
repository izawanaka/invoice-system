"use client";

// /pabrik/bap-pabrik -- BAP Versi Pabrik (K4/P7): hanya kolom aman. Bukti perhitungan bonus & klaim untuk kepala.
import * as React from "react";
import { Halaman, KartuRekap, FilterBulan, Kosong, fmtN, fmtTgl, bulanIni, useLoad } from "@/components/pabrik/ui";
import { listBapPabrik } from "@/lib/pabrik-api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function BapPabrikPage() {
  const [bulan, setBulan] = React.useState(bulanIni());
  const bap = useLoad(() => listBapPabrik(bulan), [bulan]);
  const rows = bap.data ?? [];
  return (
    <Halaman judul="BAP Versi Pabrik" desc="BAP yang sudah ditautkan owner ke surat jalan. Volume di sini yang menjadi dasar Sak Netto bulan (Konsep B)." kembali="/pabrik/modul/kirim">
      <KartuRekap judul="BAP tertaut" desc={`${rows.length} baris · ${fmtN(rows.reduce((a, r) => a + r.jumlah_sak, 0))} sak dikirim`} aksi={<FilterBulan value={bulan} onChange={setBulan} />}>
        {rows.length === 0 ? <Kosong teks="Belum ada BAP tertaut bulan ini" /> : (
          <Table><TableHeader><TableRow><TableHead>No BAP</TableHead><TableHead>Tgl BAP</TableHead><TableHead className="text-right">Volume BAP</TableHead><TableHead>SJ</TableHead><TableHead>Tgl kirim</TableHead><TableHead className="text-right">Sak dikirim</TableHead><TableHead>Tujuan</TableHead><TableHead className="text-right">Sak klaim</TableHead></TableRow></TableHeader>
            <TableBody>{rows.map((r) => <TableRow key={r.pengiriman_id}><TableCell className="font-medium">{r.no_bap}</TableCell><TableCell>{fmtTgl(r.tgl_bap)}</TableCell><TableCell className="text-right">{fmtN(r.qty_bap, 2)} {r.satuan_bap}</TableCell><TableCell>{r.no_surat_jalan}</TableCell><TableCell>{fmtTgl(r.tanggal_kirim)}</TableCell><TableCell className="text-right">{r.jumlah_sak}</TableCell><TableCell>{r.tujuan_kode}</TableCell><TableCell className="text-right">{r.sak_klaim}</TableCell></TableRow>)}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
