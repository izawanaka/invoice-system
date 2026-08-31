"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, ArrowRight } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const WORKSPACES = [
  { kode: "DKP", nama: "Cocopeat DKP", satuan: "kg", desc: "Terbit invoice cocopeat satuan kilogram (dengan PPN)." },
  { kode: "KKS", nama: "Cocopeat KKS", satuan: "m3", desc: "Terbit invoice cocopeat satuan meter kubik." },
];

function PilihContent() {
  const { selected, chosen, setSelected } = useBadanUsaha();
  const { user } = useAuth();
  const router = useRouter();

  function pilih(kode: string) {
    setSelected(kode);
    router.replace("/dashboard");
  }

  return (
    <div className="flex min-h-screen flex-1 flex-col items-center justify-center gap-8 bg-muted/30 p-6">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Pilih Masuk DKP atau KKS</h1>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {user?.nama ? "Halo, " + user.nama + ". " : ""}Pilih workspace. Terbit Invoice &amp; Laporan akan mengikuti pilihan ini. Ringkasan di Dashboard tetap gabungan DKP + KKS.
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
        {WORKSPACES.map((w) => (
          <button
            key={w.kode}
            type="button"
            onClick={() => pilih(w.kode)}
            className={cn(
              "flex flex-col items-start gap-3 rounded-xl border bg-card p-6 text-left shadow-sm transition-all hover:border-primary hover:shadow-md",
              chosen && selected === w.kode ? "border-primary ring-1 ring-primary" : "border-border",
            )}
          >
            <div className="flex w-full items-center justify-between">
              <span className="rounded-md bg-primary/10 px-2.5 py-1 text-lg font-bold text-primary">{w.kode}</span>
              <ClipboardList className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-base font-semibold">{w.nama}</p>
              <p className="mt-1 text-sm text-muted-foreground">{w.desc}</p>
              <p className="mt-2 text-xs text-muted-foreground">Satuan: {w.satuan}</p>
            </div>
            <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary">
              Masuk {w.kode} <ArrowRight className="h-4 w-4" />
            </span>
            {chosen && selected === w.kode ? (
              <span className="text-[11px] text-muted-foreground">Terakhir dipakai</span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function PilihPage() {
  return (
    <RequireAuth>
      <PilihContent />
    </RequireAuth>
  );
}
