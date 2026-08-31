"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, ClipboardList, FileText, Receipt, ArrowRight } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { listPO, listInvoices, listBAP } from "@/lib/api";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { useRouter } from "next/navigation";
import { formatIDR, formatQty } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { WarningBadge } from "@/components/status-badge";
import type { POSisaOut, InvoiceOut } from "@/lib/types";

function DashboardContent() {
  const { user } = useAuth();
  const bolehLihatPelunasan = user?.role === "owner";
  const router = useRouter();
  const [poList, setPoList] = React.useState<POSisaOut[]>([]);
  const [invoiceList, setInvoiceList] = React.useState<InvoiceOut[]>([]);
  const [bapCount, setBapCount] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);
  const { list: buList, selected } = useBadanUsaha();

  React.useEffect(() => {
    // Ringkasan PER WORKSPACE -- ikut memfilter saat ganti workspace (DKP/KKS).
    // (Sebelumnya global gabungan DKP+KKS; diubah atas permintaan owner 31 Jul 2026.)
    setLoading(true);
    Promise.all([
      listPO({ badan_usaha_kode: selected }),
      listInvoices({ badan_usaha_kode: selected }),
      listBAP({ badan_usaha_kode: selected }),
    ])
      .then(([po, inv, bap]) => {
        setPoList(po);
        setInvoiceList(inv);
        setBapCount(bap.length);
      })
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router, selected]);

  const poWarning = poList.filter((p) => p.is_warning);
  const poAktif = poList.filter((p) => p.status?.toLowerCase() === "aktif" || p.status?.toLowerCase() === "active");
  const namaWorkspace = buList.find((bu) => bu.kode === selected)?.nama ?? selected;
  const invoiceOutstanding = invoiceList.filter((i) => i.status === "generated");
  const outstandingTotal = invoiceOutstanding.reduce((acc, i) => acc + (i.grand_total ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Ringkasan Workspace: {selected}</h1>
        <p className="text-sm text-muted-foreground">
          PO aktif, BAP, dan invoice dari {namaWorkspace} ({selected}) saja. Ganti workspace lewat menu akun untuk lihat BU lain.
        </p>
      </div>

      <div
        className={
          bolehLihatPelunasan
            ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
            : "grid grid-cols-1 gap-4 sm:grid-cols-3"
        }
      >
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">PO Aktif</CardTitle>
            <ClipboardList className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{loading ? "-" : poAktif.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">PO Sisa Menipis</CardTitle>
            <AlertTriangle className="h-4 w-4 text-warning" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{loading ? "-" : poWarning.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">BAP Tercatat</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{loading ? "-" : bapCount}</p>
          </CardContent>
        </Card>
        {bolehLihatPelunasan ? (
          <Card>
            <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Invoice Outstanding</CardTitle>
              <Receipt className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">{loading ? "-" : invoiceOutstanding.length}</p>
              <p className="text-xs text-muted-foreground">{loading ? "" : formatIDR(outstandingTotal)}</p>
            </CardContent>
          </Card>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Sisa PO (m3 / kg)</CardTitle>
          <CardDescription>Sisa kuantitas tiap PO aktif di workspace {selected}.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Memuat...</p>
          ) : poAktif.length === 0 ? (
            <p className="text-sm text-muted-foreground">Belum ada PO aktif.</p>
          ) : (
            <div className="flex flex-col divide-y divide-border">
              {poAktif.map((po) => (
                <div key={`${po.kode}-${po.po_no}`} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <div>
                    <p className="font-medium">
                      {po.site ?? "-"} · {po.po_no}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      sisa {formatQty(po.sisa_qty, po.satuan)} dari {formatQty(po.total_qty, po.satuan)} ({po.pct_used.toFixed(1)}% terpakai)
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-2xl font-bold tabular-nums leading-none">{formatQty(po.sisa_qty, po.satuan)}</p>
                      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">sisa</p>
                    </div>
                    <WarningBadge isWarning={po.is_warning} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Link href="/po">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <ClipboardList className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Purchase Order</p>
                <p className="text-xs text-muted-foreground">Kelola PO (per workspace aktif)</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/bap">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Terbit Invoice</p>
                <p className="text-xs text-muted-foreground">Unggah BAP &amp; terbitkan invoice</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/invoices">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <Receipt className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Rekap Invoice</p>
                <p className="text-xs text-muted-foreground">Daftar invoice (per workspace aktif)</p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <AppShell>
        <DashboardContent />
      </AppShell>
    </RequireAuth>
  );
}
