"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Upload, CheckCircle2, MoreHorizontal, Printer, Truck, Download, FileText, Ban } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import {
  ApiError,
  checkFakturPajakStatus,
  listInvoices,
  lihatPembayaran,
  catatPembayaran,
  hapusPembayaran,
  uploadFakturPajak,
  uploadResi,
  downloadResi,
  cekDokumenInvoice,
  downloadDokumen,
  batalkanInvoice,
} from "@/lib/api";
import type { InvoiceOut, DokumenItem, PembayaranItem, PembayaranRingkas } from "@/lib/types";
import { formatDate, formatIDR } from "@/lib/utils";

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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
  // Pengamat boleh MELIHAT riwayat cicilan (keputusan owner 4 Sep 2026),
  // tapi tidak boleh mencatat/menghapus/melunaskan.
  const { user } = useAuth();
  const isViewer = user?.role === "viewer";
  const [ringkas, setRingkas] = React.useState<PembayaranRingkas | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [nominal, setNominal] = React.useState("");
  const [tglBayar, setTglBayar] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = React.useState(false);

  const muat = React.useCallback(() => {
    if (!invoice) return;
    setLoading(true);
    lihatPembayaran(invoice.no_invoice)
      .then(setRingkas)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Gagal memuat pembayaran."))
      .finally(() => setLoading(false));
  }, [invoice]);

  React.useEffect(() => {
    if (open && invoice) {
      setNominal("");
      muat();
    }
  }, [open, invoice, muat]);

  async function tambahCicilan(lunaskan: boolean) {
    if (!invoice) return;
    const body: { nominal?: number; tgl_bayar?: string; lunaskan?: boolean } = { tgl_bayar: tglBayar };
    if (lunaskan) {
      body.lunaskan = true;
    } else {
      const n = Number(nominal.replace(/[^0-9.]/g, ""));
      if (!n || n <= 0) {
        toast.error("Isi nominal pembayaran dulu.");
        return;
      }
      body.nominal = n;
    }
    setBusy(true);
    try {
      const r = await catatPembayaran(invoice.no_invoice, body);
      setRingkas(r);
      setNominal("");
      toast.success(lunaskan ? "Ditandai lunas." : "Cicilan dicatat.");
      onUpdated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mencatat pembayaran.");
    } finally {
      setBusy(false);
    }
  }

  async function hapusCicilan(item: PembayaranItem) {
    if (!invoice) return;
    setBusy(true);
    try {
      const r = await hapusPembayaran(item.id);
      setRingkas(r);
      toast.success("Cicilan dihapus.");
      onUpdated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus cicilan.");
    } finally {
      setBusy(false);
    }
  }

  const fmt = (n: number | null | undefined) =>
    n == null ? "-" : new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Pembayaran Invoice</DialogTitle>
          <DialogDescription>{invoice?.no_invoice}</DialogDescription>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground py-2">Memuat...</p>
        ) : ringkas ? (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md border p-2">
                <p className="text-[10px] uppercase text-muted-foreground">Tagihan</p>
                <p className="text-sm font-semibold">{fmt(ringkas.grand_total)}</p>
              </div>
              <div className="rounded-md border p-2">
                <p className="text-[10px] uppercase text-muted-foreground">Dibayar</p>
                <p className="text-sm font-semibold text-success">{fmt(ringkas.total_dibayar)}</p>
              </div>
              <div className="rounded-md border p-2">
                <p className="text-[10px] uppercase text-muted-foreground">Sisa</p>
                <p className="text-sm font-semibold text-warning">{fmt(ringkas.sisa)}</p>
              </div>
            </div>
            <StatusBadge status={ringkas.status} />
            {ringkas.daftar.length > 0 ? (
              <div className="flex flex-col gap-1">
                {ringkas.daftar.map((it) => (
                  <div key={it.id} className="flex items-center justify-between rounded-md border px-2 py-1 text-sm">
                    <span className="text-muted-foreground">{it.tgl_bayar ?? "-"}</span>
                    <span className="font-medium">{fmt(it.nominal)}</span>
                    {!isViewer ? (
                      <Button variant="ghost" size="sm" disabled={busy} onClick={() => hapusCicilan(it)}>Hapus</Button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
            {ringkas.sisa > 0 && !isViewer ? (
              <div className="flex flex-col gap-2 border-t pt-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tgl_bayar">Tanggal Bayar</Label>
                  <Input id="tgl_bayar" type="date" value={tglBayar} onChange={(e) => setTglBayar(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="nominal">Nominal Cicilan</Label>
                  <Input id="nominal" inputMode="numeric" placeholder="mis. 1000000" value={nominal} onChange={(e) => setNominal(e.target.value)} />
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" disabled={busy} onClick={() => tambahCicilan(false)}>Catat Cicilan</Button>
                  <Button className="flex-1" disabled={busy} onClick={() => tambahCicilan(true)}>Lunaskan Sisa</Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-success font-medium">Invoice sudah lunas.</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground py-2">-</p>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Tutup</Button>
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
  const { selected } = useBadanUsaha();
  const { user } = useAuth();
  // Keputusan owner 28 Jul 2026: staf boleh apa saja KECUALI melihat pelunasan
  // invoice. Backend sudah mengirim status/tgl_bayar/outstanding = null utk staf
  // (routers/invoices.py), jadi ini murni supaya tampilannya tidak menyisakan
  // kolom kosong yang membingungkan -- BUKAN satu-satunya lapisan pengaman.
  const bolehLihatPelunasan = user?.role === "owner" || user?.role === "viewer";
  // Pengamat: boleh MELIHAT (termasuk pelunasan), tidak boleh menulis/mengunduh.
  // Server sudah menolak; ini supaya tidak ada tombol mati yang membingungkan.
  const isViewer = user?.role === "viewer";
  const router = useRouter();
  const [invoiceList, setInvoiceList] = React.useState<InvoiceOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const buFilter = selected;
  const [activeTab, setActiveTab] = React.useState<"outstanding" | "lunas">("outstanding");
  const [paymentTarget, setPaymentTarget] = React.useState<InvoiceOut | null>(null);
  const [fakturTarget, setFakturTarget] = React.useState<InvoiceOut | null>(null);
  const [resiTarget, setResiTarget] = React.useState<InvoiceOut | null>(null);
  const [cekTarget, setCekTarget] = React.useState<InvoiceOut | null>(null);
  const [batalTarget, setBatalTarget] = React.useState<InvoiceOut | null>(null);
  const [membatalkan, setMembatalkan] = React.useState(false);
  // Fitur centang & jumlah otomatis (owner): cari kombinasi invoice yang cocok
  // dengan satu pembayaran gabungan dari customer.
  const [siteFilter, setSiteFilter] = React.useState<string>("ALL");
  const [dipilih, setDipilih] = React.useState<Record<string, boolean>>({});
  const [lunaskanOpen, setLunaskanOpen] = React.useState(false);
  const [tglBayarMassal, setTglBayarMassal] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [melunasi, setMelunasi] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    listInvoices({
      badan_usaha_kode: buFilter,
      // Tidak difilter status di backend -- Outstanding/Lunas dipisah di klien
      // supaya invoice "sebagian" (cicilan) tetap masuk Outstanding, bukan hilang
      // begitu saja dari kedua tab (dulu cuma "generated"/"paid" yang tercakup).
    })
      .then(setInvoiceList)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat data invoice");
      })
      .finally(() => setLoading(false));
  }, [buFilter, router]);

  React.useEffect(() => {
    load();
  }, [load]);

  // Ganti workspace -> kosongkan centang & filter site (daftar site ikut berganti).
  React.useEffect(() => {
    setDipilih({});
    setSiteFilter("ALL");
  }, [buFilter]);

  // Outstanding = belum lunas (mencakup "generated" & "sebagian"/cicilan).
  // Begitu status jadi "paid", baris otomatis pindah ke tab Lunas saat data
  // di-refresh (mis. sesudah "Lunaskan Sisa" di dialog Kelola Pembayaran).
  // Saring per site dulu (dropdown "Semua Site" / nama site) -- tab & hitungan ikut.
  const bySite = React.useMemo(
    () => (siteFilter === "ALL" ? invoiceList : invoiceList.filter((inv) => (inv.site ?? "-") === siteFilter)),
    [invoiceList, siteFilter],
  );
  const siteList = React.useMemo(() => {
    const s = new Set<string>();
    invoiceList.forEach((inv) => s.add(inv.site ?? "-"));
    return Array.from(s).sort();
  }, [invoiceList]);
  const displayList = React.useMemo(() => {
    if (!bolehLihatPelunasan) return bySite;
    return activeTab === "outstanding"
      ? bySite.filter((inv) => inv.status !== "paid")
      : bySite.filter((inv) => inv.status === "paid");
  }, [bySite, bolehLihatPelunasan, activeTab]);
  const outstandingCount = React.useMemo(
    () => bySite.filter((inv) => inv.status !== "paid").length,
    [bySite],
  );
  const lunasCount = React.useMemo(
    () => bySite.filter((inv) => inv.status === "paid").length,
    [bySite],
  );
  // Invoice yang dicentang (kunci = no_invoice) + jumlah otomatisnya.
  const terpilihList = React.useMemo(
    () => invoiceList.filter((inv) => dipilih[inv.no_invoice]),
    [invoiceList, dipilih],
  );
  const totalTerpilih = React.useMemo(() => {
    let tagihan = 0;
    let dibayar = 0;
    terpilihList.forEach((inv) => {
      const grand = inv.grand_total ?? 0;
      tagihan += grand;
      // Invoice lunas lama (paid sebelum fitur cicilan ada) tidak punya baris
      // cicilan -- anggap terbayar penuh supaya Sisa Tagihan tidak menyesatkan.
      dibayar += inv.status === "paid" ? Math.max(grand, inv.total_dibayar ?? 0) : inv.total_dibayar ?? 0;
    });
    return { tagihan, dibayar, sisa: Math.max(tagihan - dibayar, 0) };
  }, [terpilihList]);
  const semuaTampilTercentang =
    displayList.length > 0 && displayList.every((inv) => dipilih[inv.no_invoice]);

  function toggleSemua() {
    setDipilih((prev) => {
      const next = { ...prev };
      if (semuaTampilTercentang) displayList.forEach((inv) => delete next[inv.no_invoice]);
      else
        displayList.forEach((inv) => {
          next[inv.no_invoice] = true;
        });
      return next;
    });
  }

  // Lunaskan semua invoice terpilih yang belum lunas: pakai endpoint pembayaran
  // per-invoice yang sudah teruji (lunaskan=true = bayar sisa), satu per satu.
  async function handleLunaskanTerpilih() {
    const targets = terpilihList.filter((inv) => inv.status !== "paid");
    if (targets.length === 0) {
      toast.error("Tidak ada invoice terpilih yang masih punya sisa tagihan.");
      return;
    }
    setMelunasi(true);
    let sukses = 0;
    const gagal: string[] = [];
    for (const inv of targets) {
      try {
        await catatPembayaran(inv.no_invoice, {
          lunaskan: true,
          tgl_bayar: tglBayarMassal,
          catatan: "Pelunasan massal (Rekap Invoice)",
        });
        sukses += 1;
      } catch {
        gagal.push(inv.no_invoice);
      }
    }
    setMelunasi(false);
    setLunaskanOpen(false);
    if (sukses > 0) toast.success(`${sukses} invoice ditandai lunas.`);
    if (gagal.length > 0) toast.error(`Gagal melunaskan: ${gagal.join(", ")}`);
    setDipilih({});
    load();
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

  async function handleBatalkan() {
    if (!batalTarget) return;
    setMembatalkan(true);
    try {
      await batalkanInvoice(batalTarget.no_invoice);
      toast.success(`Invoice ${batalTarget.no_invoice} dibatalkan -- qty PO & BAP terkait sudah dikembalikan.`);
      setBatalTarget(null);
      load();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal membatalkan invoice");
    } finally {
      setMembatalkan(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Rekap Invoice</h1>
          <p className="text-sm text-muted-foreground">
            {bolehLihatPelunasan
              ? "Kelola status pembayaran & faktur pajak. Untuk menerbitkan invoice baru, buka menu Terbit Invoice."
              : "Unggah faktur pajak & cetak paket dokumen. Untuk menerbitkan invoice baru, buka menu Terbit Invoice."}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="text-base">Rekap Invoice</CardTitle>
            <span className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
              Workspace: {selected}
            </span>
            <Select value={siteFilter} onValueChange={setSiteFilter}>
              <SelectTrigger className="h-8 w-[180px]">
                <SelectValue placeholder="Semua Site" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Semua Site</SelectItem>
                {siteList.map((st) => (
                  <SelectItem key={st} value={st}>
                    {st}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {bolehLihatPelunasan ? (
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "outstanding" | "lunas")}>
              <TabsList>
                <TabsTrigger value="outstanding">Outstanding ({outstandingCount})</TabsTrigger>
                <TabsTrigger value="lunas">Lunas ({lunasCount})</TabsTrigger>
              </TabsList>
            </Tabs>
          ) : null}
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                {bolehLihatPelunasan ? (
                  <TableHead className="w-8">
                    <input
                      type="checkbox"
                      aria-label="Pilih semua yang tampil"
                      className="h-4 w-4 accent-primary align-middle"
                      checked={semuaTampilTercentang}
                      onChange={toggleSemua}
                    />
                  </TableHead>
                ) : null}
                <TableHead>No. Invoice</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Site</TableHead>
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
                  <TableCell colSpan={bolehLihatPelunasan ? 10 : 7} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : displayList.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={bolehLihatPelunasan ? 10 : 7} className="text-center text-muted-foreground">
                    {bolehLihatPelunasan
                      ? activeTab === "outstanding"
                        ? "Tidak ada invoice outstanding (semua sudah lunas)."
                        : "Belum ada invoice yang lunas."
                      : "Tidak ada data invoice."}
                  </TableCell>
                </TableRow>
              ) : (
                displayList.map((inv) => (
                  <TableRow key={inv.id} data-state={dipilih[inv.no_invoice] ? "selected" : undefined}>
                    {bolehLihatPelunasan ? (
                      <TableCell>
                        <input
                          type="checkbox"
                          aria-label={`Pilih ${inv.no_invoice}`}
                          className="h-4 w-4 accent-primary align-middle"
                          checked={!!dipilih[inv.no_invoice]}
                          onChange={() =>
                            setDipilih((prev) => ({ ...prev, [inv.no_invoice]: !prev[inv.no_invoice] }))
                          }
                        />
                      </TableCell>
                    ) : null}
                    <TableCell>{inv.no_invoice}</TableCell>
                    <TableCell>{formatDate(inv.tgl_invoice)}</TableCell>
                    <TableCell>{inv.site ?? "-"}</TableCell>
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
                          {!isViewer ? (
                            <DropdownMenuItem
                              onClick={() =>
                                router.push(`/invoices/${encodeURIComponent(inv.no_invoice)}/cetak`)
                              }
                              className="gap-2"
                            >
                              <Printer className="h-4 w-4" /> Cetak Paket (Invoice+PO+FP+BAP)
                            </DropdownMenuItem>
                          ) : null}
                          {bolehLihatPelunasan ? (
                            <DropdownMenuItem
                              onClick={() => setPaymentTarget(inv)}
                              className="gap-2"
                            >
                              <CheckCircle2 className="h-4 w-4" /> Kelola Pembayaran
                            </DropdownMenuItem>
                          ) : null}
                          {!isViewer ? (
                            <>
                              <DropdownMenuItem onClick={() => setFakturTarget(inv)} className="gap-2">
                                <Upload className="h-4 w-4" /> Unggah Faktur Pajak
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => setResiTarget(inv)} className="gap-2">
                                <Truck className="h-4 w-4" /> Upload Bukti Resi (Terkirim)
                              </DropdownMenuItem>
                            </>
                          ) : null}
                          <DropdownMenuItem onClick={() => setCekTarget(inv)} className="gap-2">
                            <FileText className="h-4 w-4" /> Cek Dokumen (Paperless)
                          </DropdownMenuItem>
                          {inv.tahap_dok === "terkirim" && !isViewer ? (
                            <DropdownMenuItem onClick={() => handleUnduhResi(inv)} className="gap-2">
                              <Download className="h-4 w-4" /> Unduh Bukti Resi
                            </DropdownMenuItem>
                          ) : null}
                          {!isViewer ? (
                            <DropdownMenuItem
                              onClick={() => setBatalTarget(inv)}
                              className="gap-2 text-destructive focus:text-destructive"
                              // BatalInvoiceRekapMenuItem marker (jangan dihapus, penanda idempoten patch)
                            >
                              <Ban className="h-4 w-4" /> Batal Invoice
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

      {bolehLihatPelunasan && terpilihList.length > 0 ? (
        <div className="sticky bottom-2 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3 shadow-lg">
          <div className="flex flex-wrap items-center gap-4">
            <span className="text-sm font-medium">{terpilihList.length} invoice dipilih</span>
            <div className="text-sm">
              <span className="text-muted-foreground">Total Tagihan: </span>
              <span className="font-semibold">{formatIDR(totalTerpilih.tagihan)}</span>
            </div>
            <div className="text-sm">
              <span className="text-muted-foreground">Sudah Dibayar: </span>
              <span className="font-semibold text-success">{formatIDR(totalTerpilih.dibayar)}</span>
            </div>
            <div className="text-sm">
              <span className="text-muted-foreground">Sisa Tagihan: </span>
              <span className="font-semibold text-warning">{formatIDR(totalTerpilih.sisa)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setDipilih({})}>
              Kosongkan
            </Button>
            {!isViewer ? (
              <Button size="sm" onClick={() => setLunaskanOpen(true)} disabled={totalTerpilih.sisa <= 0}>
                Lunaskan Terpilih
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

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
      <CekDokumenDialog
        invoice={cekTarget}
        open={cekTarget !== null}
        onOpenChange={(v) => !v && setCekTarget(null)}
      />

      <Dialog open={lunaskanOpen} onOpenChange={(o) => !o && !melunasi && setLunaskanOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Lunaskan {terpilihList.filter((i) => i.status !== "paid").length} Invoice?
            </DialogTitle>
            <DialogDescription>
              Sisa tagihan sebesar {formatIDR(totalTerpilih.sisa)} akan dicatat sebagai pembayaran
              pelunasan untuk semua invoice terpilih yang belum lunas (invoice yang sudah lunas
              otomatis dilewati). Cocokkan dulu angka ini dengan uang yang masuk di rekening.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tgl_bayar_massal">Tanggal Bayar</Label>
            <Input
              id="tgl_bayar_massal"
              type="date"
              value={tglBayarMassal}
              onChange={(e) => setTglBayarMassal(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLunaskanOpen(false)} disabled={melunasi}>
              Batal
            </Button>
            <Button onClick={handleLunaskanTerpilih} disabled={melunasi}>
              {melunasi ? "Memproses..." : "Ya, Lunaskan Semua"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!batalTarget} onOpenChange={(o) => !o && setBatalTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Batalkan Invoice?</DialogTitle>
            <DialogDescription>
              Invoice {batalTarget?.no_invoice} akan dibatalkan (mis. salah terbit). Qty PO yang
              terpotong invoice ini akan DIKEMBALIKAN, dan BAP yang terpakai akan DILEPAS supaya bisa
              dipakai lagi untuk invoice baru. Invoice tidak dihapus (tetap tercatat sebagai batal).
              Tindakan ini tidak bisa dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBatalTarget(null)} disabled={membatalkan}>Batal</Button>
            <Button variant="destructive" onClick={handleBatalkan} disabled={membatalkan}>
              {membatalkan ? "Membatalkan..." : "Ya, Batalkan Invoice"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CekDokumenDialog({
  invoice,
  open,
  onOpenChange,
}: {
  invoice: InvoiceOut | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  // Pengamat boleh melihat DAFTAR dokumen terarsip, tidak boleh mengunduhnya.
  const { user } = useAuth();
  const isViewer = user?.role === "viewer";
  const [loading, setLoading] = React.useState(false);
  const [items, setItems] = React.useState<DokumenItem[]>([]);
  const [aktif, setAktif] = React.useState(true);
  const [unduhId, setUnduhId] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!open || !invoice) return;
    setLoading(true);
    setItems([]);
    setAktif(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    cekDokumenInvoice(invoice.no_invoice)
      .then((r) => {
        setItems(r.dokumen);
        setAktif(r.paperless_aktif);
      })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Gagal memuat daftar dokumen.");
      })
      .finally(() => setLoading(false));
  }, [open, invoice]);

  async function handleUnduh(item: DokumenItem) {
    setUnduhId(item.doc_id);
    try {
      const blob = await downloadDokumen(item.doc_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (item.jenis + "_" + (invoice ? invoice.no_invoice : String(item.doc_id))).replace(/[^A-Za-z0-9.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh dokumen.");
    } finally {
      setUnduhId(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Dokumen Invoice</DialogTitle>
          <DialogDescription>{invoice?.no_invoice} - arsip Paperless</DialogDescription>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground py-4">Memuat...</p>
        ) : !aktif ? (
          <p className="text-sm text-muted-foreground py-4">Paperless tidak aktif.</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            Belum ada dokumen terarsip untuk invoice ini.
          </p>
        ) : (
          <div className="flex flex-col gap-2 py-2">
            {items.map((item) => (
              <div
                key={item.jenis + "-" + item.doc_id}
                className="flex items-center justify-between rounded-md border p-2"
              >
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{item.jenis}</p>
                    <p className="text-xs text-muted-foreground">{item.judul}</p>
                  </div>
                </div>
                {isViewer ? null : (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={unduhId === item.doc_id}
                  onClick={() => handleUnduh(item)}
                  className="gap-2"
                >
                  <Download className="h-4 w-4" />
                  {unduhId === item.doc_id ? "Mengunduh..." : "Unduh"}
                </Button>
                )}
              </div>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Tutup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
