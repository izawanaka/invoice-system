"use client";

// /pabrik/modul/[slug] -- satu modul = grid kartu fungsi (pola popover Accurate, versi halaman agar enak di tablet).
import { useParams } from "next/navigation";
import { Halaman, Launcher, Legenda } from "@/components/pabrik/ui";
import { MODUL } from "@/lib/pabrik-menu";

export default function ModulPage() {
  const { modul } = useParams<{ modul: string }>();
  const m = MODUL.find((x) => x.slug === modul);
  if (!m) return <Halaman judul="Modul tidak ditemukan"><p className="text-sm text-muted-foreground">Kembali ke Beranda.</p></Halaman>;
  return (
    <Halaman judul={m.label} desc={m.desc}>
      <Launcher fungsi={m.fungsi} />
      <Legenda />
    </Halaman>
  );
}
