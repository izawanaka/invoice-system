"use client";

import * as React from "react";
import { toast } from "sonner";
import { Upload, Trash2, FileCheck2 } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized } from "@/lib/auth-context";
import {
  ApiError,
  ocrExtractFaktur,
  createFakturPajak,
  getFakturPajakList,
  deleteFakturPajak,
} from "@/lib/api";
import type { FakturPajakOcrOut, FakturPajakOut } from "@/lib/types";
import { formatDate, formatIDR } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

// Halaman "Faktur Pajak" (Fase 3, 30 Jul 2026) -- upload foto/PDF Faktur Pajak
// (dokumen dari Konsultan/Coretax), ekstraksi OCR pratinjau, lalu user MEMILIH
// SENDIRI invoice sistem mana yang ditautkan (tidak pernah auto-link) sebelum
// disimpan. Cross-check tiga arah (DPP/PPN/Total vs invoice) dijalankan di
// backend saat simpan -- hasilnya ditandai matched/mismatch/pending di tabel.

function StatusCocokBadge({ status }: { status: string }) {
  if (status === "matched") {
    return <Badge className="bg-green-600 hover:bg-green-600">Cocok</Badge>;
  }
  if (status === "mismatch") {
    return <Badge variant="destructive">Tidak Cocok</Badge>;
  }
  return <Badge variant="secondary">Pending</Badge>;
}

function UploadFakturCard({ onSaved }: { onSaved: () => void }) {
  const { selected } = useBadanUsaha();
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [ocring, setOcring] = React.useState(false);
  const [ocr, setOcr] = React.useState<FakturPajakOcrOut | null>(null);
  const [invoiceId, setInvoiceId] = React.useState<string>("");
  const [nomorFaktur, setNomorFaktur] = React.useState("");
  const [tanggalFaktur, setTanggalFaktur] = React.useState("");
  const [dpp, setDpp] = React.useState("");
  const [ppn, setPpn] = React.useState("");
  const [total, setTotal] = React.useState("");
  const [catatan, setCatatan] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  function reset() {
    setFile(null);
    setOcr(null);
    setInvoiceId("");
    setNomorFaktur("");
    setTanggalFaktur("");
    setDpp("");
    setPpn("");
    setTotal("");
    setCatatan("");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setOcring(true);
    setOcr(null);
    try {
      const hasil = await ocrExtractFaktur(f, selected);
      setOcr(hasil);
      setNomorFaktur(hasil.nomor_faktur ?? "");
      setTanggalFaktur(hasil.tanggal_faktur ?? "");
      setDpp(hasil.dpp != null ? String(hasil.dpp) : "");
      setPpn(hasil.ppn != null ? String(hasil.ppn) : "");
      setTotal(hasil.total != null ? String(hasil.total) : "");
      setCatatan(hasil.catatan_keraguan ?? "");
      if (hasil.kandidat_invoice.length > 0) {
        setInvoiceId(String(hasil.kandidat_invoice[0].invoice_id));
      }
      if (hasil.catatan_keraguan) {
        toast.warning(`Ada field yang perlu diisi/dicek manual: ${hasil.catatan_keraguan}`);
      }
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal membaca dokumen Faktur Pajak");
      setFile(null);
    } finally {
      setOcring(false);
    }
  }

  async function handleSave() {
    if (!file) return;
    if (!invoiceId) {
      toast.error("Pilih dulu invoice sistem yang sesuai dengan Faktur Pajak ini");
      return;
    }
    setSaving(true);
    try {
      const hasil = await createFakturPajak({
        invoice_id: Number(invoiceId),
        badan_usaha_kode: selected,
        file,
        nomor_faktur: nomorFaktur || null,
        tanggal_faktur: tanggalFaktur || null,
        dpp: dpp ? Number(dpp) : null,
        ppn: ppn ? Number(ppn) : null,
        total: total ? Number(total) : null,
        catatan_keraguan: catatan || null,
      });
      if (hasil.status_cocok === "mismatch") {
        toast.warning(`Faktur Pajak tersimpan, tapi TIDAK COCOK: ${hasil.catatan_selisih ?? ""}`);
      } else {
        toast.success(`Faktur Pajak ${hasil.nomor_faktur ?? ""} tersimpan (${hasil.status_cocok}).`);
      }
      reset();
      onSaved();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan Faktur Pajak");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Upload className="h-4 w-4" /> Unggah Faktur Pajak
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <Label htmlFor="faktur-file">Foto / PDF Faktur Pajak</Label>
          <Input
            id="faktur-file"
            ref={fileRef}
            type="file"
            accept="image/*,.pdf"
            onChange={handleFile}
            disabled={ocring || saving}
          />
        </div>

        {ocring && <p className="text-sm text-muted-foreground">Membaca dokumen...</p>}

        {ocr && (
          <div className="flex flex-col gap-3 rounded-md border border-border p-3">
            {ocr.catatan_keraguan && (
              <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
                Perlu diisi/dicek manual: {ocr.catatan_keraguan}
              </p>
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label>Nomor Faktur {!nomorFaktur && <span className="text-amber-600">(perlu diisi manual)</span>}</Label>
                <Input value={nomorFaktur} onChange={(e) => setNomorFaktur(e.target.value)} placeholder="010.XXX-XX.XXXXXXXX" />
              </div>
              <div>
                <Label>Tanggal Faktur {!tanggalFaktur && <span className="text-amber-600">(perlu diisi manual)</span>}</Label>
                <Input type="date" value={tanggalFaktur} onChange={(e) => setTanggalFaktur(e.target.value)} />
              </div>
              <div>
                <Label>DPP {!dpp && <span className="text-amber-600">(perlu diisi manual)</span>}</Label>
                <Input type="number" value={dpp} onChange={(e) => setDpp(e.target.value)} />
              </div>
              <div>
                <Label>PPN {!ppn && <span className="text-amber-600">(perlu diisi manual)</span>}</Label>
                <Input type="number" value={ppn} onChange={(e) => setPpn(e.target.value)} />
              </div>
              <div>
                <Label>Total {!total && <span className="text-amber-600">(perlu diisi manual)</span>}</Label>
                <Input type="number" value={total} onChange={(e) => setTotal(e.target.value)} />
              </div>
              <div>
                <Label>Invoice Sistem Terkait (WAJIB dipilih)</Label>
                <Select value={invoiceId} onValueChange={setInvoiceId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Pilih invoice..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ocr.kandidat_invoice.map((c) => (
                      <SelectItem key={c.invoice_id} value={String(c.invoice_id)}>
                        {c.no_invoice} — {c.customer ?? "-"} — {c.grand_total != null ? formatIDR(c.grand_total) : "-"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Catatan Keraguan (opsional, boleh diedit)</Label>
              <Input value={catatan} onChange={(e) => setCatatan(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={reset} disabled={saving}>Batal</Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Menyimpan..." : "Simpan Faktur Pajak"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FakturPajakTable({
  items, onDeleted,
}: {
  items: FakturPajakOut[];
  onDeleted: () => void;
}) {
  const [toDelete, setToDelete] = React.useState<FakturPajakOut | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await deleteFakturPajak(toDelete.id);
      toast.success("Faktur Pajak dihapus.");
      setToDelete(null);
      onDeleted();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus Faktur Pajak");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileCheck2 className="h-4 w-4" /> Daftar Faktur Pajak
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nomor Faktur</TableHead>
              <TableHead>Invoice</TableHead>
              <TableHead>Tanggal</TableHead>
              <TableHead className="text-right">DPP</TableHead>
              <TableHead className="text-right">PPN</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Aksi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                  Belum ada Faktur Pajak diunggah.
                </TableCell>
              </TableRow>
            )}
            {items.map((it) => (
              <TableRow key={it.id}>
                <TableCell>{it.nomor_faktur ?? "-"}</TableCell>
                <TableCell>{it.no_invoice}</TableCell>
                <TableCell>{it.tanggal_faktur ? formatDate(it.tanggal_faktur) : "-"}</TableCell>
                <TableCell className="text-right">{it.dpp != null ? formatIDR(it.dpp) : "-"}</TableCell>
                <TableCell className="text-right">{it.ppn != null ? formatIDR(it.ppn) : "-"}</TableCell>
                <TableCell className="text-right">{it.total != null ? formatIDR(it.total) : "-"}</TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1">
                    <StatusCocokBadge status={it.status_cocok} />
                    {it.status_cocok === "mismatch" && it.catatan_selisih && (
                      <span className="max-w-xs text-xs text-destructive">{it.catatan_selisih}</span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" onClick={() => setToDelete(it)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={!!toDelete} onOpenChange={(open) => !open && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Hapus Faktur Pajak?</DialogTitle>
            <DialogDescription>
              Faktur {toDelete?.nomor_faktur ?? "(tanpa nomor)"} untuk invoice {toDelete?.no_invoice} akan
              dihapus permanen beserta berkasnya. Tindakan ini tidak bisa dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={deleting}>Batal</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleting}>
              {deleting ? "Menghapus..." : "Hapus"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function FakturPajakPageInner() {
  const { selected } = useBadanUsaha();
  const [items, setItems] = React.useState<FakturPajakOut[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    getFakturPajakList(selected)
      .then(setItems)
      .catch((err) => {
        if (isUnauthorized(err)) return;
        toast.error("Gagal memuat daftar Faktur Pajak");
      })
      .finally(() => setLoading(false));
  }, [selected]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Faktur Pajak</h1>
        <p className="text-sm text-muted-foreground">
          Unggah Faktur Pajak dari Konsultan, cocokkan dengan Invoice sistem, dan pantau hasil cross-check
          DPP/PPN/Total.
        </p>
      </div>
      <UploadFakturCard onSaved={load} />
      {loading ? (
        <p className="text-sm text-muted-foreground">Memuat...</p>
      ) : (
        <FakturPajakTable items={items} onDeleted={load} />
      )}
    </div>
  );
}

export default function FakturPajakPage() {
  return (
    <RequireAuth>
      <AppShell>
        <FakturPajakPageInner />
      </AppShell>
    </RequireAuth>
  );
}
