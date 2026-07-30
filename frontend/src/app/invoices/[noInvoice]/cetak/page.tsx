"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Download, Printer, CheckCircle2, AlertTriangle } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { isUnauthorized } from "@/lib/auth-context";
import { ApiError, paketCetakInfo, paketCetakPdf } from "@/lib/api";
import type { PaketCetakInfo } from "@/lib/types";
import { formatIDR } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function CetakContent() {
  const params = useParams<{ noInvoice: string }>();
  const router = useRouter();
  const noInvoice = decodeURIComponent(params.noInvoice ?? "");

  const [info, setInfo] = React.useState<PaketCetakInfo | null>(null);
  const [pdfUrl, setPdfUrl] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const frameRef = React.useRef<HTMLIFrameElement | null>(null);
  const urlRef = React.useRef<string | null>(null);

  const muat = React.useCallback(() => {
    if (!noInvoice) return;
    setLoading(true);
    Promise.all([paketCetakInfo(noInvoice), paketCetakPdf(noInvoice)])
      .then(([meta, blob]) => {
        setInfo(meta);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        setPdfUrl(url);
      })
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal menyiapkan paket cetak");
      })
      .finally(() => setLoading(false));
  }, [noInvoice, router]);

  React.useEffect(() => {
    muat();
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [muat]);

  function cetak() {
    const f = frameRef.current;
    if (!f?.contentWindow) {
      toast.error("Pratinjau belum siap.");
      return;
    }
    f.contentWindow.focus();
    f.contentWindow.print();
  }

  function unduh() {
    if (!pdfUrl) return;
    const a = document.createElement("a");
    a.href = pdfUrl;
    a.download = `paket_cetak_${noInvoice.replace(/\//g, "_")}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const inv = info?.invoice;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => router.push("/invoices")}>
            <ArrowLeft className="h-4 w-4" /> Kembali
          </Button>
          <div>
            <h1 className="text-lg font-semibold">Paket Cetak — {noInvoice}</h1>
            <p className="text-xs text-muted-foreground">
              Invoice + PO + Faktur Pajak + BAP digabung jadi satu dokumen. Review dulu, baru cetak.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" disabled={!pdfUrl} onClick={unduh}>
            <Download className="h-4 w-4" /> Unduh PDF
          </Button>
          <Button size="sm" className="gap-1.5" disabled={!pdfUrl} onClick={cetak}>
            <Printer className="h-4 w-4" /> Cetak Semua
          </Button>
        </div>
      </div>

      {info ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {info.siap_cetak ? (
                <span className="flex items-center gap-2 text-emerald-600">
                  <CheckCircle2 className="h-4 w-4" /> Paket lengkap — siap dicetak & dikirim
                </span>
              ) : (
                <span className="flex items-center gap-2 text-amber-600">
                  <AlertTriangle className="h-4 w-4" /> Ada bagian yang belum lengkap
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {inv ? (
              <p className="text-sm text-muted-foreground">
                {inv.customer ?? "-"} · {inv.site ?? "-"} ·{" "}
                {inv.grand_total != null ? formatIDR(inv.grand_total) : "-"}
                {inv.no_faktur_pajak ? ` · FP ${inv.no_faktur_pajak}` : ""}
              </p>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2">
              {info.bagian.map((b) => (
                <div
                  key={b.kode}
                  className="rounded-md border border-border p-3 text-sm"
                >
                  <p className="flex items-center gap-2 font-medium">
                    {b.lengkap ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
                    )}
                    {b.judul}
                  </p>
                  {b.berkas.length > 0 ? (
                    <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
                      {b.berkas.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  ) : null}
                  {b.masalah.length > 0 ? (
                    <ul className="mt-1 list-inside list-disc text-xs text-amber-700">
                      {b.masalah.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Bagian yang belum lengkap tetap ikut dicetak sebagai halaman penanda, supaya
              ketahuan sebelum dokumen dikirim ke customer.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Card className="flex-1">
        <CardContent className="p-0">
          {loading ? (
            <p className="p-6 text-sm text-muted-foreground">Menyiapkan pratinjau...</p>
          ) : pdfUrl ? (
            <iframe
              ref={frameRef}
              src={pdfUrl}
              title={`Paket cetak ${noInvoice}`}
              className="h-[75vh] w-full rounded-md"
            />
          ) : (
            <p className="p-6 text-sm text-muted-foreground">Pratinjau tidak tersedia.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function CetakPaketPage() {
  return (
    <RequireAuth>
      <AppShell>
        <CetakContent />
      </AppShell>
    </RequireAuth>
  );
}
