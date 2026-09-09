"use client";

// /pabrik -- Beranda workspace PABRIK ala Accurate: saldo hari ini + grid modul/fungsi.
// PABRIK_FE_B2B7_9SEP2026 (menggantikan dashboard B1; master pemasok/petak pindah ke /pabrik/master).
import * as React from "react";
import Link from "next/link";
import { Factory } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Launcher, Legenda, fmtN, fmtRp, fmtTgl, useLoad, usePeran, today } from "@/components/pabrik/ui";
import { MODUL } from "@/lib/pabrik-menu";
import { getSaldo, listLot, listTemuan, ringkasanHari } from "@/lib/pabrik-api";

function Angka({ label, nilai, ket, href }: { label: string; nilai: string; ket?: string; href: string }) {
  return (
    <Link href={href}>
      <Card className="h-full transition-colors hover:bg-accent/40">
        <CardHeader className="pb-1"><CardDescription>{label}</CardDescription><CardTitle className="text-2xl">{nilai}</CardTitle></CardHeader>
        {ket ? <CardContent className="text-xs text-muted-foreground">{ket}</CardContent> : null}
      </Card>
    </Link>
  );
}

function Beranda() {
  const { user } = usePeran();
  const saldo = useLoad(getSaldo, []);
  const lot = useLoad(() => listLot(true), []);
  const temuan = useLoad(() => listTemuan("terbuka"), []);
  const hari = useLoad(() => ringkasanHari(today()), []);
  const s = saldo.data;
  const r = hari.data?.ringkasan as Record<string, number> | undefined;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Factory className="h-6 w-6" /> Pabrik Cocopeat</h1>
        <p className="text-sm text-muted-foreground">{user?.nama ? `Halo, ${user.nama}. ` : ""}Pilih fungsi di bawah untuk input atau melihat rekap.</p>
      </div>

      <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
        <Angka label="Sak kosong" nilai={s ? fmtN(s.sak_kosong) : "…"} ket={s ? `rusak tunggu retur ${s.sak_rusak_belum_retur}` : undefined} href="/pabrik/sak" />
        <Angka label="Stok jadi (sak)" nilai={s ? fmtN(s.stok_jadi) : "…"} href="/pabrik/stok" />
        <Angka label="Kas kecil" nilai={s ? fmtRp(s.kas) : "…"} href="/pabrik/kas" />
        <Angka label="Lot aktif" nilai={lot.data ? String(lot.data.length) : "…"} ket={lot.data?.slice(0, 3).map((l) => `${l.petak} ${l.status}`).join(" · ")} href="/pabrik/lot" />
        <Angka label="Temuan audit terbuka" nilai={temuan.data ? String(temuan.data.length) : "…"} ket={temuan.data?.length ? temuan.data.slice(0, 2).map((t) => t.kode).join(", ") : "bersih"} href="/pabrik/audit" />
      </div>

      <Card className={hari.data?.sudah_ditutup ? "border-green-300" : "border-warning/60"}>
        <CardContent className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">Hari ini {fmtTgl(today())}:</span>
            {r ? (<>
              <Badge variant="outline">{r.truk_masuk} truk · {fmtN(r.kubik_masuk, 1)} kubik</Badge>
              <Badge variant="outline">{r.sak_diproduksi} sak diproduksi</Badge>
              <Badge variant="outline">{r.sak_dikirim} sak dikirim</Badge>
              <Badge variant="outline">{r.kas} kas · {r.upah} upah</Badge>
            </>) : null}
          </div>
          <Link href="/pabrik/tutup-hari" className="text-xs font-medium underline-offset-2 hover:underline">
            {hari.data?.sudah_ditutup ? "✅ Hari sudah ditutup" : "Belum ditutup → Tutup Hari"}
          </Link>
        </CardContent>
      </Card>

      {MODUL.map((m) => (
        <section key={m.slug} className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between border-b pb-1">
            <h2 className="flex items-center gap-2 text-base font-semibold"><m.icon className="h-4 w-4" /> {m.label}</h2>
            <Link href={`/pabrik/modul/${m.slug}`} className="text-xs text-muted-foreground hover:underline">{m.desc}</Link>
          </div>
          <Launcher fungsi={m.fungsi} kecil />
        </section>
      ))}
      <Legenda />
    </div>
  );
}

export default function PabrikPage() {
  return (<RequireAuth><AppShell><Beranda /></AppShell></RequireAuth>);
}
