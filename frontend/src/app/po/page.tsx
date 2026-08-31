"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, ScanLine } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized } from "@/lib/auth-context";
import {
  ApiError,
  createPO,
  deletePO,
  listPO,
  ocrExtractPO,
  setPOStatus,
  uploadPODokumen,
} from "@/lib/api";
import type { POCreateRequest, POOcrOut, POSisaOut } from "@/lib/types";
import { formatIDR, formatQty } from "@/lib/utils";

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

function POContent() {
  const { list: buList, selected } = useBadanUsaha();
  const router = useRouter();
  const [poList, setPoList] = React.useState<POSisaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const buFilter = selected;
  const [statusFilter, setStatusFilter] = React.useState<string>("ALL");
  const [warningOnly, setWarningOnly] = React.useState(false);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [form, setForm] = React.useState<POCreateRequest>(EMPTY_FORM);
  const [submitting, setSubmitting] = React.useState(false);
  const [hapusPo, setHapusPo] = React.useState<POSisaOut | null>(null);
  const [deletingPo, setDeletingPo] = React.useState(false);
  const [siteQuery, setSiteQuery] = React.useState("");

  // ---- Wizard "Tambah PO dari Foto/Scan" (Fase 2, 30 Jul 2026) ----
  const [ocrDialogOpen, setOcrDialogOpen] = React.useState(false);
  const [ocrFile, setOcrFile] = React.useState<File | null>(null);
  const [ocrLoading, setOcrLoading] = React.useState(false);
  const [ocrResult, setOcrResult] = React.useState<POOcrOut | null>(null);
  const [ocrForm, setOcrForm] = React.useState<POCreateRequest>(EMPTY_FORM);
  const [ocrSubmitting, setOcrSubmitting] = React.useState(false);


  const load = React.useCallback(() => {
    setLoading(true);
    listPO({
      badan_usaha_kode: buFilter,
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
    const q = siteQuery.trim().toLowerCase();
    return poList.filter((po) => {
      const sisa = Number(po.sisa_qty ?? 0);
      const aktif = po.status === "aktif" && sisa > 1e-6;
      if (statusFilter === "aktif" && !aktif) return false;
      if (statusFilter === "selesai" && aktif) return false;
      if (q && !(po.site ?? "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [poList, statusFilter, siteQuery]);

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

  function resetOcrWizard() {
    setOcrFile(null);
    setOcrResult(null);
    setOcrForm({ ...EMPTY_FORM, badan_usaha_kode: selected });
  }

  async function handleOcrExtract() {
    if (!ocrFile) {
      toast.error("Pilih foto/scan PO terlebih dahulu.");
      return;
    }
    setOcrLoading(true);
    try {
      const hasil = await ocrExtractPO(ocrFile, ocrForm.badan_usaha_kode || undefined);
      setOcrResult(hasil);
      setOcrForm((f) => ({
        ...f,
        po_no: hasil.po_no ?? "",
        site: hasil.site_saran ?? "",
        customer: hasil.customer ?? "",
        total_qty: hasil.total_qty ?? 0,
        satuan: hasil.satuan ?? "",
        harga_satuan: hasil.harga_satuan ?? 0,
        tgl_masuk: hasil.tanggal ?? null,
      }));
      if (hasil.po_no_sudah_ada) {
        toast.warning(`PO ${hasil.po_no} sepertinya SUDAH ADA -- periksa kembali sebelum menyimpan.`);
      }
      if (hasil.catatan_keraguan) {
        toast.warning("Ada field yang tidak yakin terbaca -- lihat catatan di bawah, lengkapi manual.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal membaca dokumen.");
    } finally {
      setOcrLoading(false);
    }
  }

  async function handleOcrSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ocrForm.badan_usaha_kode) {
      toast.error("Pilih badan usaha terlebih dahulu.");
      return;
    }
    setOcrSubmitting(true);
    try {
      await createPO(ocrForm);
      // Arsipkan otomatis berkas yang tadi dipakai OCR (keputusan owner: scan asli
      // WAJIB tersimpan di app_po_doc) -- kegagalan arsip TIDAK membatalkan PO yang
      // sudah tersimpan, hanya diberi peringatan.
      if (ocrFile) {
        try {
          await uploadPODokumen(ocrForm.po_no, ocrForm.badan_usaha_kode, ocrFile);
        } catch {
          toast.warning(`PO ${ocrForm.po_no} tersimpan, tapi gagal mengarsipkan berkas scan. Unggah manual di halaman rincian PO.`);
        }
      }
      toast.success(`PO ${ocrForm.po_no} berhasil dicatat dari hasil OCR.`);
      setOcrDialogOpen(false);
      resetOcrWizard();
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan PO.");
    } finally {
      setOcrSubmitting(false);
    }
  }

  async function handleHapusPo() {
    if (!hapusPo) return;
    setDeletingPo(true);
    try {
      await deletePO(hapusPo.po_no, hapusPo.kode);
      toast.success(`PO ${hapusPo.po_no} dihapus.`);
      setHapusPo(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus PO.");
    } finally {
      setDeletingPo(false);
    }
  }

  async function handleToggleStatus(po: POSisaOut) {
    const target = po.status === "aktif" ? "selesai" : "aktif";
    try {
      await setPOStatus(po.po_no, po.kode, target);
      toast.success(`PO ${po.po_no} ${target === "aktif" ? "diaktifkan kembali" : "dinonaktifkan"}.`);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengubah status PO.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Purchase Order</h1>
          <p className="text-sm text-muted-foreground">Daftar PO dan sisa kuantitas per PO.</p>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={(v) => {
            setDialogOpen(v);
            // Prefill badan usaha dgn workspace aktif (DKP/KKS) -- tetap bisa diganti.
            if (v) setForm((f) => ({ ...f, badan_usaha_kode: f.badan_usaha_kode || selected }));
          }}
        >
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
        <Dialog
          open={ocrDialogOpen}
          onOpenChange={(v) => {
            setOcrDialogOpen(v);
            if (v) setOcrForm((f) => ({ ...f, badan_usaha_kode: f.badan_usaha_kode || selected }));
            if (!v) resetOcrWizard();
          }}
        >
          <DialogTrigger asChild>
            <Button variant="outline" className="gap-1.5">
              <ScanLine className="h-4 w-4" /> Tambah PO dari Foto/Scan
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>Tambah PO dari Foto/Scan</DialogTitle>
              <DialogDescription>
                Unggah foto/scan PO -- sistem membaca isinya otomatis. Field yang tidak
                yakin terbaca akan DIKOSONGKAN dan WAJIB diisi/diperiksa manual sebelum
                disimpan (tidak ada yang ditebak).
              </DialogDescription>
            </DialogHeader>

            {!ocrResult ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Badan Usaha</Label>
                  <Select
                    value={ocrForm.badan_usaha_kode}
                    onValueChange={(v) => setOcrForm((f) => ({ ...f, badan_usaha_kode: v }))}
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
                  <Label htmlFor="ocr_file">Foto / Scan PO (JPG, PNG, atau PDF)</Label>
                  <Input
                    id="ocr_file"
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,.pdf,image/*,application/pdf"
                    onChange={(e) => setOcrFile(e.target.files?.[0] ?? null)}
                  />
                </div>
                <DialogFooter>
                  <Button type="button" disabled={ocrLoading || !ocrFile} onClick={handleOcrExtract}>
                    {ocrLoading ? "Membaca dokumen..." : "Baca & Ekstrak"}
                  </Button>
                </DialogFooter>
              </div>
            ) : (
              <form onSubmit={handleOcrSubmit} className="flex flex-col gap-3">
                {ocrResult.catatan_keraguan && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-800">
                    <span className="font-semibold">Catatan keraguan OCR: </span>
                    {ocrResult.catatan_keraguan}
                  </div>
                )}
                {ocrResult.po_no_sudah_ada && (
                  <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive">
                    PO ini kemungkinan SUDAH ADA di badan usaha yang dipilih. Periksa
                    kembali nomor PO sebelum menyimpan.
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5 col-span-2">
                    <Label>Badan Usaha</Label>
                    <Select
                      value={ocrForm.badan_usaha_kode}
                      onValueChange={(v) => setOcrForm((f) => ({ ...f, badan_usaha_kode: v }))}
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
                    <Label htmlFor="ocr_po_no">
                      Nomor PO {!ocrForm.po_no && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_po_no"
                      required
                      className={!ocrForm.po_no ? "border-destructive" : undefined}
                      value={ocrForm.po_no}
                      onChange={(e) => setOcrForm((f) => ({ ...f, po_no: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="ocr_site">
                      Site {!ocrForm.site && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_site"
                      required
                      className={!ocrForm.site ? "border-destructive" : undefined}
                      value={ocrForm.site}
                      onChange={(e) => setOcrForm((f) => ({ ...f, site: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5 col-span-2">
                    <Label htmlFor="ocr_customer">
                      Customer {!ocrForm.customer && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_customer"
                      required
                      className={!ocrForm.customer ? "border-destructive" : undefined}
                      value={ocrForm.customer}
                      onChange={(e) => setOcrForm((f) => ({ ...f, customer: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="ocr_total_qty">
                      Total Qty {!ocrForm.total_qty && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_total_qty"
                      type="number"
                      step="any"
                      required
                      className={!ocrForm.total_qty ? "border-destructive" : undefined}
                      value={ocrForm.total_qty}
                      onChange={(e) => setOcrForm((f) => ({ ...f, total_qty: Number(e.target.value) }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="ocr_satuan">
                      Satuan {!ocrForm.satuan && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_satuan"
                      required
                      placeholder="kg / m3"
                      className={!ocrForm.satuan ? "border-destructive" : undefined}
                      value={ocrForm.satuan}
                      onChange={(e) => setOcrForm((f) => ({ ...f, satuan: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="ocr_harga_satuan">
                      Harga Satuan (Rp) {!ocrForm.harga_satuan && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_harga_satuan"
                      type="number"
                      step="any"
                      required
                      className={!ocrForm.harga_satuan ? "border-destructive" : undefined}
                      value={ocrForm.harga_satuan}
                      onChange={(e) => setOcrForm((f) => ({ ...f, harga_satuan: Number(e.target.value) }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="ocr_tgl_masuk">
                      Tanggal PO {!ocrForm.tgl_masuk && <span className="text-destructive">(perlu diisi manual)</span>}
                    </Label>
                    <Input
                      id="ocr_tgl_masuk"
                      type="date"
                      required
                      className={!ocrForm.tgl_masuk ? "border-destructive" : undefined}
                      value={ocrForm.tgl_masuk ?? ""}
                      onChange={(e) => setOcrForm((f) => ({ ...f, tgl_masuk: e.target.value || null }))}
                    />
                  </div>
                </div>
                <DialogFooter className="gap-2">
                  <Button type="button" variant="ghost" onClick={resetOcrWizard}>
                    Ulangi Ekstraksi
                  </Button>
                  <Button type="submit" disabled={ocrSubmitting}>
                    {ocrSubmitting ? "Menyimpan..." : "Simpan PO"}
                  </Button>
                </DialogFooter>
              </form>
            )}
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="text-base">Daftar PO</CardTitle>
            <span className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
              Workspace: {selected}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="h-8 w-[150px] text-xs"
              placeholder="Cari site..."
              value={siteQuery}
              onChange={(e) => setSiteQuery(e.target.value)}
            />
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
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : filteredPo.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground">
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
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleToggleStatus(po)}
                        >
                          {po.status === "aktif" ? "Nonaktifkan" : "Aktifkan"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setHapusPo(po)}
                        >
                          Hapus
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={hapusPo !== null} onOpenChange={(v) => { if (!v) setHapusPo(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Hapus PO?</DialogTitle>
            <DialogDescription>
              PO {hapusPo?.po_no} · {hapusPo?.kode} · site {hapusPo?.site ?? "-"}. PO dihapus dari database &amp; tracker. Kalau PO sudah dipakai invoice, penghapusan ditolak otomatis.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setHapusPo(null)}>
              Batal
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deletingPo}
              onClick={handleHapusPo}
            >
              {deletingPo ? "Menghapus..." : "Ya, hapus PO"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
