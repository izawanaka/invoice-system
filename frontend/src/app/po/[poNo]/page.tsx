"use client";

import * as React from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Download, Printer, Upload } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import {
  ApiError,
  downloadPODokumen,
  listPO,
  listPOInvoices,
  deletePODokumen,
  listPODokumen,
  uploadPODokumen,
} from "@/lib/api";
import type { PODocOut, POInvoiceCutOut, POSisaOut } from "@/lib/types";
import { formatDate, formatIDR, formatQty } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { StatusBadge, WarningBadge } from "@/components/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function DokumenPOCard({ poNo, kode }: { poNo: string; kode: string }) {
  const [docs, setDocs] = React.useState<PODocOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [uploading, setUploading] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const [hapusId, setHapusId] = React.useState<number | null>(null);
  const [deletingId, setDeletingId] = React.useState<number | null>(null);

  const muat = React.useCallback(() => {
    setLoading(true);
    listPODokumen(poNo, kode)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setLoading(false));
  }, [poNo, kode]);

  React.useEffect(() => {
    muat();
  }, [muat]);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadPODokumen(poNo, kode, file);
      toast.success("Scan PO tersimpan — akan ikut saat cetak paket invoice.");
      muat();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunggah scan PO.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function unduh(d: PODocOut) {
    try {
      const blob = await downloadPODokumen(d.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = d.original_filename ?? `po_${poNo}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh dokumen.");
    }
  }

  async function hapus(d: PODocOut) {
    setDeletingId(d.id);
    try {
      await deletePODokumen(d.id);
      toast.success("Scan PO dihapus. Kalau perlu, unggah scan yang benar.");
      setHapusId(null);
      muat();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus scan PO.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Card className="print:hidden">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="text-base">Scan PO Asli</CardTitle>
          <p className="text-xs text-muted-foreground">
            Dokumen PO dari customer. Ini yang ikut tercetak setiap kali paket invoice dicetak.
          </p>
        </div>
        <div>
          <Input
            ref={fileRef}
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            onChange={handleFile}
          />
          <Button
            type="button"
            size="sm"
            className="gap-1.5"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="h-4 w-4" />
            {uploading ? "Mengunggah..." : "Unggah Scan PO"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">Memuat...</p>
        ) : docs.length === 0 ? (
          <p className="text-sm text-amber-700">
            Belum ada scan PO. Paket cetak invoice yang memakai PO ini akan diberi halaman penanda
            &quot;belum diunggah&quot;.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{d.original_filename ?? `dokumen #${d.id}`}</span>
                {hapusId === d.id ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      disabled={deletingId === d.id}
                      onClick={() => hapus(d)}
                    >
                      {deletingId === d.id ? "Menghapus..." : "Ya, hapus"}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setHapusId(null)}>
                      Batal
                    </Button>
                  </div>
                ) : (
                  <div className="flex shrink-0 items-center gap-1">
                    <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => unduh(d)}>
                      <Download className="h-4 w-4" /> Lihat
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setHapusId(d.id)}
                    >
                      Hapus
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PODetailContent() {
  const params = useParams<{ poNo: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { selected } = useBadanUsaha();
  const { user } = useAuth();
  // Status invoice = informasi pelunasan; backend mengirim null utk staf
  // (routers/po.py), jadi kolomnya ikut disembunyikan supaya tidak jadi kolom
  // berisi "-" yang membingungkan.
  const bolehLihatPelunasan = user?.role === "owner";

  const poNo = decodeURIComponent(params.poNo ?? "");
  const kode = search.get("kode") ?? selected;

  const [po, setPo] = React.useState<POSisaOut | null>(null);
  const [rows, setRows] = React.useState<POInvoiceCutOut[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    if (!poNo) return;
    setLoading(true);
    Promise.all([listPO({ badan_usaha_kode: kode }), listPOInvoices(poNo, kode)])
      .then(([poList, cuts]) => {
        setPo(poList.find((p) => p.po_no === poNo) ?? null);
        setRows(cuts);
      })
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat rincian PO");
      })
      .finally(() => setLoading(false));
  }, [poNo, kode, router]);

  const totalDipotong = rows.reduce((acc, r) => acc + (r.qty || 0), 0);
  const totalSubtotal = rows.reduce((acc, r) => acc + (r.subtotal || 0), 0);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 print:max-w-none">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => router.push("/po")}>
          <ArrowLeft className="h-4 w-4" /> Kembali ke daftar PO
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => window.print()}>
          <Printer className="h-4 w-4" /> Cetak
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Rincian PO {poNo} <span className="text-muted-foreground">({kode})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Memuat...</p>
          ) : !po ? (
            <p className="text-sm text-muted-foreground">PO tidak ditemukan untuk {kode}.</p>
          ) : (
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Site</p>
                <p className="font-medium">{po.site ?? "-"}</p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">Customer</p>
                <p className="font-medium">{po.customer ?? "-"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Harga Satuan</p>
                <p className="font-medium">{formatIDR(po.harga_satuan)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Status</p>
                <p className="flex items-center gap-2 font-medium capitalize">
                  {po.status} <WarningBadge isWarning={po.is_warning} />
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Sisa</p>
                <p className="font-medium">{formatQty(po.sisa_qty, po.satuan)}</p>
              </div>
              <div className="col-span-2 md:col-span-3">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    Terpakai {formatQty(po.used_qty, po.satuan)} / {formatQty(po.total_qty, po.satuan)}
                  </span>
                  <span>{po.pct_used.toFixed(1)}%</span>
                </div>
                <Progress value={po.pct_used} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {poNo ? <DokumenPOCard poNo={poNo} kode={kode} /> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Invoice yang memotong PO ini</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No. Invoice</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>No. BAP</TableHead>
                <TableHead className="text-right">Qty Dipotong</TableHead>
                <TableHead className="text-right">Subtotal</TableHead>
                {bolehLihatPelunasan ? <TableHead>Status</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={bolehLihatPelunasan ? 6 : 5} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={bolehLihatPelunasan ? 6 : 5} className="text-center text-muted-foreground">
                    Belum ada invoice yang memotong PO ini.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((r, idx) => (
                  <TableRow key={`${r.no_invoice}-${idx}`}>
                    <TableCell className="font-medium">{r.no_invoice}</TableCell>
                    <TableCell>{formatDate(r.tgl_invoice)}</TableCell>
                    <TableCell>{r.no_bap ?? "-"}</TableCell>
                    <TableCell className="text-right">
                      {formatQty(r.qty, r.satuan ?? po?.satuan)}
                    </TableCell>
                    <TableCell className="text-right">
                      {r.subtotal != null ? formatIDR(r.subtotal) : "-"}
                    </TableCell>
                    {bolehLihatPelunasan ? (
                      <TableCell>
                        <StatusBadge status={r.status} />
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))
              )}
            </TableBody>
            {rows.length > 0 ? (
              <tfoot>
                <TableRow className="font-medium">
                  <TableCell colSpan={3}>Total</TableCell>
                  <TableCell className="text-right">
                    {formatQty(totalDipotong, po?.satuan)}
                  </TableCell>
                  <TableCell className="text-right">{formatIDR(totalSubtotal)}</TableCell>
                  {bolehLihatPelunasan ? <TableCell /> : null}
                </TableRow>
              </tfoot>
            ) : null}
          </Table>
          {po && rows.length > 0 ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Terpakai menurut PO: {formatQty(po.used_qty, po.satuan)} — cocokkan dengan total di atas.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function PODetailPage() {
  return (
    <RequireAuth>
      <AppShell>
        <React.Suspense fallback={<p className="text-sm text-muted-foreground">Memuat...</p>}>
          <PODetailContent />
        </React.Suspense>
      </AppShell>
    </RequireAuth>
  );
}
