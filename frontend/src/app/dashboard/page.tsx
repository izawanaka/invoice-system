"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, ClipboardList, FileText, Receipt, ArrowRight } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { listPO, listInvoices, listBAP } from "@/lib/api";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { formatIDR, formatQty } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { WarningBadge } from "@/components/status-badge";
import type { POSisaOut, InvoiceOut } from "@/lib/types";

function DashboardContent() {
  const { selected } = useBadanUsaha();
  const { user } = useAuth();
  // Kartu "Invoice Outstanding" = jumlah & nilai invoice yang BELUM dibayar,
  // jadi itu informasi pelunasan -- disembunyikan dari staf (keputusan owner
  // 28 Jul 2026). Backend juga tidak mengirim status bayar utk staf, jadi
  // menghitungnya di sini pun akan salah, bukan cuma "bocor".
  const bolehLihatPelunasan = user?.role === "owner";
  const router = useRouter();
  const [poList, setPoList] = React.useState<POSisaOut[]>([]);
  const [invoiceList, setInvoiceList] = React.useState<InvoiceOut[]>([]);
  const [bapCount, setBapCount] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const kode = selected === "ALL" ? undefined : selected;
    setLoading(true);
    Promise.all([
      listPO({ badan_usaha_kode: kode }),
      listInvoices({ badan_usaha_kode: kode }),
      listBAP({ badan_usaha_kode: kode }),
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
  }, [selected, router]);

  const poWarning = poList.filter((p) => p.is_warning);
  const poAktif = poList.filter((p) => p.status?.toLowerCase() === "aktif" || p.status?.toLowerCase() === "active");
  const invoiceOutstanding = invoiceList.filter((i) => i.status === "generated");
  const outstandingTotal = invoiceOutstanding.reduce((acc, i) => acc + (i.grand_total ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Ringkasan</h1>
        <p className="text-sm text-muted-foreground">
          {selected === "ALL" ? "Semua badan usaha" : selected}
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
          <CardTitle>PO dengan sisa menipis</CardTitle>
          <CardDescription>PO yang melewati ambang batas peringatan (warning_threshold_pct).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Memuat...</p>
          ) : poWarning.length === 0 ? (
            <p className="text-sm text-muted-foreground">Tidak ada PO dengan sisa menipis saat ini.</p>
          ) : (
            <div className="flex flex-col divide-y divide-border">
              {poWarning.map((po) => (
                <div key={`${po.kode}-${po.po_no}`} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <div>
                    <p className="font-medium">
                      {po.kode} · {po.po_no}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {po.site ?? "-"} · sisa {formatQty(po.sisa_qty, po.satuan)} dari {formatQty(po.total_qty, po.satuan)} ({po.pct_used.toFixed(1)}% terpakai)
                    </p>
                  </div>
                  <WarningBadge isWarning={po.is_warning} />
                </div>
              ))}
            </div>
          )}
          <div className="mt-4">
            <Button asChild variant="outline" size="sm">
              <Link href="/po" className="gap-1">
                Lihat semua PO <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Link href="/po">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <ClipboardList className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Purchase Order</p>
                <p className="text-xs text-muted-foreground">Lihat & catat PO baru</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/bap">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">BAP</p>
                <p className="text-xs text-muted-foreground">Daftar berita acara</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/invoices">
          <Card className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center gap-3 p-4">
              <Receipt className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Invoice</p>
                <p className="text-xs text-muted-foreground">Generate & kelola invoice</p>
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
