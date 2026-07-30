"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, Upload, CheckCircle2, MoreHorizontal, Printer, Send, Truck, Download } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import {
  ApiError,
  checkFakturPajakStatus,
  generateInvoice,
  listInvoices,
  updatePaymentStatus,
  updateTahapDok,
  uploadFakturPajak,
  uploadResi,
  downloadResi,
} from "@/lib/api";
import type { BAPItemIn, InvoiceGenerateRequest, InvoiceOut } from "@/lib/types";
import { GENERATE_INVOICE_SUPPORTED } from "@/lib/types";
import { formatDate, formatIDR } from "@/lib/utils";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const EMPTY_ITEM: BAPItemIn = { no_bap: "", qty: 0 };

// Tahap dokumen fisik invoice (operasional, TERPISAH dari pelunasan status).
const TAHAP_LABEL: Record<string, string> = {
  terbit: "Terbit",
  ke_konsultan: "Di Konsultan",
  faktur_ada: "Faktur Pajak Ada",
  terkirim: "Terkirim",
};
const TAHAP_VARIANT: Record<string, "outline" | "warning" | "default" | "success"> = {
  terbit: "outline",
  ke_konsultan: "warning",
  faktur_ada: "default",
  terkirim: "success",
};
function TahapBadge({ tahap }: { tahap: string | null | undefined }) {
  if (!tahap) return <Badge variant="outline">-</Badge>;
  return <Badge variant={TAHAP_VARIANT[tahap] ?? "outline"}>{TAHAP_LABEL[tahap] ?? tahap}</Badge>;
}

function BuFilterPills({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  const all = ["ALL", ...options];
  return (
    <div className="flex items-center gap-1">
      {all.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
            value === opt
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
          )}
        >
          {opt === "ALL" ? "Semua" : opt}
        </button>
      ))}
    </div>
  );
}

function GenerateInvoiceDialog({ onGenerated }: { onGenerated: () => void }) {
  const { list: buList } = useBadanUsaha();
  const supportedBu = buList.filter((bu) => GENERATE_INVOICE_SUPPORTED.includes(bu.kode));
  const [open, setOpen] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [buKode, setBuKode] = React.useState("");
  const [site, setSite] = React.useState("");
  const [invDate, setInvDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [customer, setCustomer] = React.useState("");
  const [items, setItems] = React.useState<BAPItemIn[]>([{ ...EMPTY_ITEM }]);

  function updateItem(idx: number, patch: Partial<BAPItemIn>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function addItem() {
    if (items.length >= 3) {
      toast.error("Maksimal 3 BAP per Invoice.");
      return;
    }
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!buKode) {
      toast.error("Pilih badan usaha (hanya DKP/KKS yang didukung saat ini).");
      return;
    }
    if (buKode === "DKP" && !customer.trim()) {
      toast.error("Customer wajib diisi untuk badan usaha DKP.");
      return;
    }
    const cleanItems = items.filter((it) => it.no_bap.trim());
    if (cleanItems.length === 0) {
      toast.error("Isi minimal satu nomor BAP.");
      return;
    }
    const body: InvoiceGenerateRequest = {
      badan_usaha_kode: buKode,
      site,
      no_bap: cleanItems[0].no_bap,
      inv_date: invDate,
      items: cleanItems,
      customer: customer.trim() || null,
    };
    setSubmitting(true);
    try {
      const res = await generateInvoice(body);
      if (res.status === "success") {
        toast.success(`Invoice ${res.inv_no ?? ""} berhasil dibuat.`);
        setOpen(false);
        setBuKode("");
        setSite("");
        setCustomer("");
        setItems([{ ...EMPTY_ITEM }]);
        onGenerated();
      } else {
        toast.error(res.message ?? "Gagal membuat invoice.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal membuat invoice.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="gap-1.5">
          <Plus className="h-4 w-4" /> Generate Invoice
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Invoice</DialogTitle>
          <DialogDescription>
            Hanya badan usaha DKP dan KKS yang didukung saat ini. Maksimal 3 BAP per invoice.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Badan Usaha</Label>
              <Select value={buKode} onValueChange={setBuKode}>
                <SelectTrigger>
                  <SelectValue placeholder="Pilih (DKP/KKS)" />
                </SelectTrigger>
                <SelectContent>
                  {supportedBu.length === 0 ? (
                    <SelectItem value="DKP">DKP</SelectItem>
                  ) : null}
                  {supportedBu.map((bu) => (
                    <SelectItem key={bu.kode} value={bu.kode}>
                      {bu.kode} — {bu.nama}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="inv_date">Tanggal Invoice</Label>
              <Input
                id="inv_date"
                type="date"
                required
                value={invDate}
                onChange={(e) => setInvDate(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="site">Site</Label>
              <Input id="site" required value={site} onChange={(e) => setSite(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="customer">
                Customer {buKode === "DKP" ? "(wajib untuk DKP)" : "(opsional)"}
              </Label>
              <Input
                id="customer"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
                required={buKode === "DKP"}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Daftar BAP (maks. 3)</Label>
              <Button type="button" variant="outline" size="sm" onClick={addItem}>
                Tambah BAP
              </Button>
            </div>
            {items.map((it, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <Input
                  placeholder="No. BAP"
                  value={it.no_bap}
                  onChange={(e) => updateItem(idx, { no_bap: e.target.value })}
                  className="flex-1"
                />
                <Input
                  type="number"
                  step="any"
                  placeholder="Qty"
                  value={it.qty || ""}
                  onChange={(e) => updateItem(idx, { qty: Number(e.target.value) })}
                  className="w-28"
                />
                {items.length > 1 ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeItem(idx)}>
                    Hapus
                  </Button>
                ) : null}
              </div>
            ))}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Memproses..." : "Generate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PaymentDialog({
  invoice,
  open,
  onOpenChange,
  onUpdated,
}: {
  invoice: InvoiceOut | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUpdated: () => void;
}) {
  const [tglBayar, setTglBayar] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = React.useState(false);

  async function handleConfirm() {
    if (!invoice) return;
    setSubmitting(true);
    try {
      await updatePaymentStatus(invoice.no_invoice, { status: "paid", tgl_bayar: tglBayar });
      toast.success(`Invoice ${invoice.no_invoice} ditandai lunas.`);
      onOpenChange(false);
      onUpdated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal memperbarui status pembayaran.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tandai Lunas</DialogTitle>
          <DialogDescription>Invoice {invoice?.no_invoice}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tgl_bayar">Tanggal Bayar</Label>
          <Input id="tgl_bayar" type="date" value={tglBayar} onChange={(e) => setTglBayar(e.target.value)} />
        </div>
        <DialogFooter>
          <Button onClick={handleConfirm} disabled={submitting}>
            {submitting ? "Menyimpan..." : "Konfirmasi Lunas"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FakturPajakDialog({
  invoice,
  open,
  onOpenChange,
  onUpdated,
}: {
  invoice: InvoiceOut | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUpdated: () => void;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [noFaktur, setNoFaktur] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [statusText, setStatusText] = React.useState<string | null>(null);
  const pollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  React.useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function handleUpload() {
    if (!invoice || !file) {
      toast.error("Pilih berkas faktur pajak terlebih dahulu.");
      return;
    }
    setSubmitting(true);
    setStatusText(null);
    try {
      const res = await uploadFakturPajak(invoice.no_invoice, file, noFaktur.trim() || undefined);
      if (!res.ok) {
        toast.error(res.message ?? "Upload gagal.");
        setSubmitting(false);
        return;
      }
      if (res.task_id) {
        setStatusText(res.status ?? "pending");
        let attempts = 0;
        pollRef.current = setInterval(async () => {
          attempts += 1;
          try {
            const s = await checkFakturPajakStatus(invoice.no_invoice, res.task_id!);
            setStatusText(s.status ?? "pending");
            const done = s.status && ["success", "SUCCESS", "failed", "FAILURE", "error"].includes(s.status);
            if (done || attempts >= 20) {
              stopPolling();
              setSubmitting(false);
              if (s.status && s.status.toLowerCase().includes("success")) {
                toast.success("Faktur pajak berhasil diunggah & diproses.");
                onOpenChange(false);
                onUpdated();
              } else if (done) {
                toast.error(s.message ?? "Pemrosesan faktur pajak gagal.");
              } else {
                toast.message("Masih diproses di latar belakang. Cek kembali nanti.");
              }
            }
          } catch {
            stopPolling();
            setSubmitting(false);
          }
        }, 3000);
      } else {
        toast.success("Faktur pajak berhasil diunggah.");
        setSubmitting(false);
        onOpenChange(false);
        onUpdated();
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunggah faktur pajak.");
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) stopPolling();
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unggah Faktur Pajak</DialogTitle>
          <DialogDescription>Invoice {invoice?.no_invoice}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="no_faktur">No. Faktur Pajak (opsional)</Label>
            <Input id="no_faktur" value={noFaktur} onChange={(e) => setNoFaktur(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="file">Berkas</Label>
            <Input
              id="file"
              type="file"
              accept="application/pdf,image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          {statusText ? (
            <p className="text-xs text-muted-foreground">Status pemrosesan: {statusText}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={handleUpload} disabled={submitting} className="gap-1.5">
            <Upload className="h-4 w-4" />
            {submitting ? "Memproses..." : "Unggah"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResiDialog({
  invoice,
  open,
  onOpenChange,
  onUpdated,
}: {
  invoice: InvoiceOut | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUpdated: () => void;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  async function handleUpload() {
    if (!invoice || !file) {
      toast.error("Pilih berkas bukti resi terlebih dahulu.");
      return;
    }
    setSubmitting(true);
    try {
      await uploadResi(invoice.no_invoice, file);
      toast.success(`Bukti resi terunggah - invoice ${invoice.no_invoice} ditandai Terkirim.`);
      onOpenChange(false);
      onUpdated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunggah bukti resi.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Bukti Resi</DialogTitle>
          <DialogDescription>
            Invoice {invoice?.no_invoice}. Unggahan bukti resi = penanda tahap Terkirim.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="resi_file">Berkas Resi (foto/PDF)</Label>
          <Input
            id="resi_file"
            type="file"
            accept="application/pdf,image/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <DialogFooter>
          <Button onClick={handleUpload} disabled={submitting} className="gap-1.5">
            <Truck className="h-4 w-4" />
            {submitting ? "Mengunggah..." : "Unggah & Tandai Terkirim"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InvoicesContent() {
  const { list: buList } = useBadanUsaha();
  const { user } = useAuth();
  // Keputusan owner 28 Jul 2026: staf boleh apa saja KECUALI melihat pelunasan
  // invoice. Backend sudah mengirim status/tgl_bayar/outstanding = null utk staf
  // (routers/invoices.py), jadi ini murni supaya tampilannya tidak menyisakan
  // kolom kosong yang membingungkan -- BUKAN satu-satunya lapisan pengaman.
  const bolehLihatPelunasan = user?.role === "owner";
  const router = useRouter();
  const [invoiceList, setInvoiceList] = React.useState<InvoiceOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [buFilter, setBuFilter] = React.useState("ALL");
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [paymentTarget, setPaymentTarget] = React.useState<InvoiceOut | null>(null);
  const [fakturTarget, setFakturTarget] = React.useState<InvoiceOut | null>(null);
  const [resiTarget, setResiTarget] = React.useState<InvoiceOut | null>(null);
  const buOptions = buList.map((bu) => bu.kode);

  const load = React.useCallback(() => {
    setLoading(true);
    listInvoices({
      badan_usaha_kode: buFilter === "ALL" ? undefined : buFilter,
      // Filter status = filter pelunasan; backend menolaknya utk staf (403).
      status: bolehLihatPelunasan && statusFilter !== "ALL" ? statusFilter : undefined,
    })
      .then(setInvoiceList)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat data invoice");
      })
      .finally(() => setLoading(false));
  }, [buFilter, statusFilter, bolehLihatPelunasan, router]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleTahap(inv: InvoiceOut, tahap: "terbit" | "ke_konsultan" | "faktur_ada" | "terkirim") {
    try {
      await updateTahapDok(inv.no_invoice, tahap);
      toast.success(`Tahap ${inv.no_invoice} → ${TAHAP_LABEL[tahap] ?? tahap}.`);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengubah tahap dokumen.");
    }
  }

  async function handleUnduhResi(inv: InvoiceOut) {
    try {
      const blob = await downloadResi(inv.no_invoice);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `resi_${inv.no_invoice.split("/").join("_")}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh bukti resi.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Rekap Invoice</h1>
          <p className="text-sm text-muted-foreground">
            {bolehLihatPelunasan
              ? "Generate invoice dari BAP tervalidasi, kelola status pembayaran & faktur pajak."
              : "Generate invoice dari BAP tervalidasi, unggah faktur pajak, dan cetak paket dokumen."}
          </p>
        </div>
        <GenerateInvoiceDialog onGenerated={load} />
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="text-base">Rekap Invoice</CardTitle>
            <BuFilterPills options={buOptions} value={buFilter} onChange={setBuFilter} />
          </div>
          {bolehLihatPelunasan ? (
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-8 w-[160px] text-xs">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Semua status</SelectItem>
                <SelectItem value="generated">Belum Lunas</SelectItem>
                <SelectItem value="paid">Sudah Lunas</SelectItem>
              </SelectContent>
            </Select>
          ) : null}
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Badan Usaha</TableHead>
                <TableHead>No. Invoice</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Grand Total</TableHead>
                {bolehLihatPelunasan ? <TableHead>Status</TableHead> : null}
                {bolehLihatPelunasan ? <TableHead>Outstanding</TableHead> : null}
                <TableHead>Tahap</TableHead>
                <TableHead>Faktur Pajak</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={bolehLihatPelunasan ? 10 : 8} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : invoiceList.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={bolehLihatPelunasan ? 10 : 8} className="text-center text-muted-foreground">
                    Tidak ada data invoice.
                  </TableCell>
                </TableRow>
              ) : (
                invoiceList.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="font-medium">{inv.badan_usaha_kode}</TableCell>
                    <TableCell>{inv.no_invoice}</TableCell>
                    <TableCell>{formatDate(inv.tgl_invoice)}</TableCell>
                    <TableCell>{inv.customer ?? "-"}</TableCell>
                    <TableCell>{formatIDR(inv.grand_total)}</TableCell>
                    {bolehLihatPelunasan ? (
                      <TableCell>
                        <StatusBadge status={inv.status} />
                      </TableCell>
                    ) : null}
                    {bolehLihatPelunasan ? (
                      <TableCell>
                        {inv.status === "paid"
                          ? `Lunas ${formatDate(inv.tgl_bayar)}`
                          : inv.hari_outstanding !== null && inv.hari_outstanding !== undefined
                            ? `${inv.hari_outstanding} hari`
                            : "-"}
                      </TableCell>
                    ) : null}
                    <TableCell><TahapBadge tahap={inv.tahap_dok} /></TableCell>
                    <TableCell>{inv.no_faktur_pajak ?? "-"}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() =>
                              router.push(`/invoices/${encodeURIComponent(inv.no_invoice)}/cetak`)
                            }
                            className="gap-2"
                          >
                            <Printer className="h-4 w-4" /> Cetak Paket (Invoice+PO+FP+BAP)
                          </DropdownMenuItem>
                          {bolehLihatPelunasan ? (
                            <DropdownMenuItem
                              disabled={inv.status === "paid"}
                              onClick={() => setPaymentTarget(inv)}
                              className="gap-2"
                            >
                              <CheckCircle2 className="h-4 w-4" /> Tandai Lunas
                            </DropdownMenuItem>
                          ) : null}
                          <DropdownMenuItem onClick={() => setFakturTarget(inv)} className="gap-2">
                            <Upload className="h-4 w-4" /> Unggah Faktur Pajak
                          </DropdownMenuItem>
                          <DropdownMenuItem disabled={inv.tahap_dok === "ke_konsultan"} onClick={() => handleTahap(inv, "ke_konsultan")} className="gap-2">
                            <Send className="h-4 w-4" /> Serahkan ke Konsultan
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setResiTarget(inv)} className="gap-2">
                            <Truck className="h-4 w-4" /> Upload Bukti Resi (Terkirim)
                          </DropdownMenuItem>
                          {inv.tahap_dok === "terkirim" ? (
                            <DropdownMenuItem onClick={() => handleUnduhResi(inv)} className="gap-2">
                              <Download className="h-4 w-4" /> Unduh Bukti Resi
                            </DropdownMenuItem>
                          ) : null}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <PaymentDialog
        invoice={paymentTarget}
        open={paymentTarget !== null}
        onOpenChange={(v) => !v && setPaymentTarget(null)}
        onUpdated={load}
      />
      <FakturPajakDialog
        invoice={fakturTarget}
        open={fakturTarget !== null}
        onOpenChange={(v) => !v && setFakturTarget(null)}
        onUpdated={load}
      />
      <ResiDialog
        invoice={resiTarget}
        open={resiTarget !== null}
        onOpenChange={(v) => !v && setResiTarget(null)}
        onUpdated={load}
      />
    </div>
  );
}

export default function InvoicesPage() {
  return (
    <RequireAuth>
      <AppShell>
        <InvoicesContent />
      </AppShell>
    </RequireAuth>
  );
}
