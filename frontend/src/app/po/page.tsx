"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized } from "@/lib/auth-context";
import { ApiError, createPO, listPO } from "@/lib/api";
import type { POCreateRequest, POSisaOut } from "@/lib/types";
import { formatIDR, formatQty, cn } from "@/lib/utils";

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
import { Progress } from "@/components/ui/progress";
import { WarningBadge } from "@/components/status-badge";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const EMPTY_FORM: POCreateRequest = {
  badan_usaha_kode: "",
  po_no: "",
  site: "",
  customer: "",
  total_qty: 0,
  satuan: "",
  harga_satuan: 0,
  cust_addr: null,
  payment_terms: null,
  tgl_masuk: null,
  catatan: null,
  warning_threshold_pct: 80,
};

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

function POContent() {
  const { list: buList } = useBadanUsaha();
  const router = useRouter();
  const [poList, setPoList] = React.useState<POSisaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [buFilter, setBuFilter] = React.useState("ALL");
  const [statusFilter, setStatusFilter] = React.useState<string>("ALL");
  const [warningOnly, setWarningOnly] = React.useState(false);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [form, setForm] = React.useState<POCreateRequest>(EMPTY_FORM);
  const [submitting, setSubmitting] = React.useState(false);

  const buOptions = buList.map((bu) => bu.kode);

  const load = React.useCallback(() => {
    setLoading(true);
    listPO({
      badan_usaha_kode: buFilter === "ALL" ? undefined : buFilter,
      warning_only: warningOnly || undefined,
    })
      .then(setPoList)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat data PO");
      })
      .finally(() => setLoading(false));
  }, [buFilter, warningOnly, router]);

  React.useEffect(() => {
    load();
  }, [load]);

  const filteredPo = React.useMemo(() => {
    return poList.filter((po) => {
      const sisa = Number(po.sisa_qty ?? 0);
      const aktif = po.status === "aktif" && sisa > 1e-6;
      if (statusFilter === "aktif") return aktif;
      if (statusFilter === "selesai") return !aktif;
      return true;
    });
  }, [poList, statusFilter]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.badan_usaha_kode) {
      toast.error("Pilih badan usaha terlebih dahulu.");
      return;
    }
    setSubmitting(true);
    try {
      await createPO(form);
      toast.success(`PO ${form.po_no} berhasil dicatat.`);
      setDialogOpen(false);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan PO.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Purchase Order</h1>
          <p className="text-sm text-muted-foreground">Daftar PO dan sisa kuantitas per PO.</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="gap-1.5">
              <Plus className="h-4 w-4" /> Catat PO Baru
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Catat PO Baru</DialogTitle>
              <DialogDescription>
                Data akan disimpan sesuai badan usaha yang dipilih. Pastikan nomor PO dan kuantitas benar.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5 col-span-2">
                  <Label>Badan Usaha</Label>
                  <Select
                    value={form.badan_usaha_kode}
                    onValueChange={(v) => setForm((f) => ({ ...f, badan_usaha_kode: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Pilih badan usaha" />
                    </SelectTrigger>
                    <SelectContent>
                      {buList.map((bu) => (
                        <SelectItem key={bu.kode} value={bu.kode}>
                          {bu.kode} — {bu.nama}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="po_no">Nomor PO</Label>
                  <Input
                    id="po_no"
                    required
                    value={form.po_no}
                    onChange={(e) => setForm((f) => ({ ...f, po_no: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="site">Site</Label>
                  <Input
                    id="site"
                    required
                    value={form.site}
                    onChange={(e) => setForm((f) => ({ ...f, site: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5 col-span-2">
                  <Label htmlFor="customer">Customer</Label>
                  <Input
                    id="customer"
                    required
                    value={form.customer}
                    onChange={(e) => setForm((f) => ({ ...f, customer: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="total_qty">Total Qty</Label>
                  <Input
                    id="total_qty"
                    type="number"
                    step="any"
                    required
                    value={form.total_qty}
                    onChange={(e) => setForm((f) => ({ ...f, total_qty: Number(e.target.value) }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="satuan">Satuan</Label>
                  <Input
                    id="satuan"
                    required
                    value={form.satuan}
                    onChange={(e) => setForm((f) => ({ ...f, satuan: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="harga_satuan">Harga Satuan (Rp)</Label>
                  <Input
                    id="harga_satuan"
                    type="number"
                    step="any"
                    required
                    value={form.harga_satuan}
                    onChange={(e) => setForm((f) => ({ ...f, harga_satuan: Number(e.target.value) }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="warning_threshold_pct">Ambang Peringatan (%)</Label>
                  <Input
                    id="warning_threshold_pct"
                    type="number"
                    step="any"
                    value={form.warning_threshold_pct ?? ""}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        warning_threshold_pct: e.target.value ? Number(e.target.value) : null,
                      }))
                    }
                  />
                </div>
                <div className="flex flex-col gap-1.5 col-span-2">
                  <Label htmlFor="payment_terms">Termin Pembayaran</Label>
                  <Input
                    id="payment_terms"
                    value={form.payment_terms ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, payment_terms: e.target.value || null }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5 col-span-2">
                  <Label htmlFor="catatan">Catatan</Label>
                  <Textarea
                    id="catatan"
                    value={form.catatan ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, catatan: e.target.value || null }))}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Menyimpan..." : "Simpan PO"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="text-base">Daftar PO</CardTitle>
            <BuFilterPills options={buOptions} value={buFilter} onChange={setBuFilter} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-8 w-[140px] text-xs">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Semua status</SelectItem>
                <SelectItem value="aktif">Aktif</SelectItem>
                <SelectItem value="selesai">Selesai</SelectItem>
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant={warningOnly ? "default" : "outline"}
              size="sm"
              onClick={() => setWarningOnly((v) => !v)}
            >
              Sisa menipis saja
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Badan Usaha</TableHead>
                <TableHead>No. PO</TableHead>
                <TableHead>Site</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Harga Satuan</TableHead>
                <TableHead>Pemakaian</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : filteredPo.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    Tidak ada data PO.
                  </TableCell>
                </TableRow>
              ) : (
                filteredPo.map((po) => (
                  <TableRow
                    key={`${po.kode}-${po.po_no}`}
                    className="cursor-pointer"
                    onClick={() =>
                      router.push(`/po/${encodeURIComponent(po.po_no)}?kode=${po.kode}`)
                    }
                    title="Klik untuk lihat rincian PO & invoice pemotongnya"
                  >
                    <TableCell className="font-medium">{po.kode}</TableCell>
                    <TableCell>{po.po_no}</TableCell>
                    <TableCell>{po.site ?? "-"}</TableCell>
                    <TableCell>{po.customer ?? "-"}</TableCell>
                    <TableCell>{formatIDR(po.harga_satuan)}</TableCell>
                    <TableCell className="min-w-[180px]">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            {formatQty(po.used_qty, po.satuan)} / {formatQty(po.total_qty, po.satuan)}
                          </span>
                          <span>{po.pct_used.toFixed(1)}%</span>
                        </div>
                        <Progress value={po.pct_used} />
                        <span className="text-xs text-muted-foreground">
                          Sisa {formatQty(po.sisa_qty, po.satuan)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col items-start gap-1">
                        <span className="text-xs capitalize">{po.status === "aktif" && Number(po.sisa_qty ?? 0) > 1e-6 ? "aktif" : "selesai"}</span>
                        <WarningBadge isWarning={po.is_warning} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function POPage() {
  return (
    <RequireAuth>
      <AppShell>
        <POContent />
      </AppShell>
    </RequireAuth>
  );
}
