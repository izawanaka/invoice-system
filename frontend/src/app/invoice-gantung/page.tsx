"use client";

import * as React from "react";
import { toast } from "sonner";
import { Send, Trash2, Pencil, Download, Eye, Ban } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useRouter } from "next/navigation";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized } from "@/lib/auth-context";
import {
  ApiError,
  listInvoices,
  listResi,
  resiDetail,
  createResi,
  editResi,
  deleteResi,
  downloadResiFile,
  downloadInvoicePdf,
  batalkanInvoice,
} from "@/lib/api";
import type { InvoiceOut, ResiListItem, ResiDetail } from "@/lib/types";
import { formatDate, formatIDR, formatQty } from "@/lib/utils";

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

function unduhBlob(blob: Blob, nama: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nama;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function InvoiceCheckList({
  invoices, checked, onToggle, kosong,
}: {
  invoices: { no_invoice: string; site: string | null; customer: string | null; grand_total: number | null }[];
  checked: Record<string, boolean>;
  onToggle: (no: string) => void;
  kosong: string;
}) {
  if (invoices.length === 0) {
    return <p className="text-sm text-muted-foreground">{kosong}</p>;
  }
  return (
    <div className="flex max-h-64 flex-col gap-1 overflow-y-auto rounded-md border border-border p-2">
      {invoices.map((inv) => (
        <label
          key={inv.no_invoice}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-accent"
        >
          <input
            type="checkbox"
            checked={!!checked[inv.no_invoice]}
            onChange={() => onToggle(inv.no_invoice)}
            className="h-4 w-4"
          />
          <span className="flex-1 text-sm">
            <span className="font-medium">{inv.no_invoice}</span>
            <span className="text-muted-foreground"> · {inv.site ?? "-"} · {inv.customer ?? "-"}</span>
          </span>
          <span className="text-xs text-muted-foreground">
            {inv.grand_total != null ? formatIDR(inv.grand_total) : "-"}
          </span>
        </label>
      ))}
    </div>
  );
}

function UnggahResiDialog({
  open, onOpenChange, gantung, onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  gantung: InvoiceOut[];
  onSaved: () => void;
}) {
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [checked, setChecked] = React.useState<Record<string, boolean>>({});
  const [noResi, setNoResi] = React.useState("");
  const [kurir, setKurir] = React.useState("");
  const [tglKirim, setTglKirim] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setFile(null); setChecked({}); setNoResi(""); setKurir(""); setTglKirim("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [open]);

  const dipilih = Object.keys(checked).filter((k) => checked[k]);

  async function handleSave() {
    if (dipilih.length === 0) { toast.error("Centang minimal satu invoice untuk resi ini"); return; }
    if (!file) { toast.error("Unggah berkas bukti resi dulu"); return; }
    setSaving(true);
    try {
      await createResi({
        file,
        no_invoices: dipilih,
        kurir: kurir || undefined,
        no_resi: noResi || undefined,
        tgl_kirim: tglKirim || undefined,
      });
      toast.success(`Resi tersimpan untuk ${dipilih.length} invoice. Invoice pindah ke Rekap.`);
      onOpenChange(false);
      onSaved();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan resi");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Unggah Resi Pengiriman</DialogTitle>
          <DialogDescription>
            Centang invoice yang dikirim dalam resi ini (boleh lebih dari satu), lalu unggah foto/PDF bukti
            resi. Invoice yang tercentang pindah dari Invoice Gantung ke Rekap.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <Label>Invoice yang dikirim ({dipilih.length} dipilih)</Label>
            <InvoiceCheckList
              invoices={gantung}
              checked={checked}
              onToggle={(no) => setChecked((c) => ({ ...c, [no]: !c[no] }))}
              kosong="Tidak ada invoice gantung."
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <Label>No. Resi (opsional)</Label>
              <Input value={noResi} onChange={(e) => setNoResi(e.target.value)} placeholder="mis. JP1234..." />
            </div>
            <div>
              <Label>Kurir (opsional)</Label>
              <Input value={kurir} onChange={(e) => setKurir(e.target.value)} placeholder="JNE / J&T / ..." />
            </div>
            <div>
              <Label>Tgl Kirim (opsional)</Label>
              <Input type="date" value={tglKirim} onChange={(e) => setTglKirim(e.target.value)} />
            </div>
          </div>
          <div>
            <Label htmlFor="resi-file">Foto / PDF Bukti Resi</Label>
            <Input
              id="resi-file"
              ref={fileRef}
              type="file"
              accept="image/*,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Batal</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? "Menyimpan..." : "Simpan Resi"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditResiDialog({
  resiId, gantung, onOpenChange, onSaved,
}: {
  resiId: number | null;
  gantung: InvoiceOut[];
  onOpenChange: (o: boolean) => void;
  onSaved: () => void;
}) {
  const [detail, setDetail] = React.useState<ResiDetail | null>(null);
  const [lepas, setLepas] = React.useState<Record<string, boolean>>({});
  const [tambah, setTambah] = React.useState<Record<string, boolean>>({});
  const [file, setFile] = React.useState<File | null>(null);
  const [noResi, setNoResi] = React.useState("");
  const [kurir, setKurir] = React.useState("");
  const [tglKirim, setTglKirim] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (resiId == null) return;
    setDetail(null); setLepas({}); setTambah({}); setFile(null);
    resiDetail(resiId)
      .then((d) => {
        setDetail(d);
        setNoResi(d.no_resi ?? "");
        setKurir(d.kurir ?? "");
        setTglKirim(d.tgl_kirim ?? "");
      })
      .catch((err) => {
        if (isUnauthorized(err)) return;
        toast.error("Gagal memuat detail resi");
      });
  }, [resiId]);

  async function handleSave() {
    if (resiId == null) return;
    const lepasList = Object.keys(lepas).filter((k) => lepas[k]);
    const tambahList = Object.keys(tambah).filter((k) => tambah[k]);
    setSaving(true);
    try {
      await editResi(resiId, {
        file: file || undefined,
        no_resi: noResi,
        kurir: kurir,
        tgl_kirim: tglKirim,
        tambah: tambahList,
        lepas: lepasList,
      });
      toast.success("Resi diperbarui.");
      onOpenChange(false);
      onSaved();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal memperbarui resi");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={resiId != null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit Resi</DialogTitle>
          <DialogDescription>
            Ubah data resi, ganti berkas, lepas invoice (kembali ke Gantung), atau tambah invoice gantung
            lain ke resi ini.
          </DialogDescription>
        </DialogHeader>
        {!detail ? (
          <p className="text-sm text-muted-foreground">Memuat...</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <Label>No. Resi</Label>
                <Input value={noResi} onChange={(e) => setNoResi(e.target.value)} />
              </div>
              <div>
                <Label>Kurir</Label>
                <Input value={kurir} onChange={(e) => setKurir(e.target.value)} />
              </div>
              <div>
                <Label>Tgl Kirim</Label>
                <Input type="date" value={tglKirim} onChange={(e) => setTglKirim(e.target.value)} />
              </div>
            </div>
            <div>
              <Label>Invoice di resi ini — centang untuk DILEPAS (balik ke Gantung)</Label>
              {detail.invoices.length === 0 ? (
                <p className="text-sm text-muted-foreground">Tidak ada invoice.</p>
              ) : (
                <div className="flex flex-col gap-1 rounded-md border border-border p-2">
                  {detail.invoices.map((inv) => (
                    <label key={inv.no_invoice} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-accent">
                      <input
                        type="checkbox"
                        checked={!!lepas[inv.no_invoice]}
                        onChange={() => setLepas((c) => ({ ...c, [inv.no_invoice]: !c[inv.no_invoice] }))}
                        className="h-4 w-4"
                      />
                      <span className="flex-1 text-sm">
                        <span className="font-medium">{inv.no_invoice}</span>
                        <span className="text-muted-foreground"> · {inv.site ?? "-"}</span>
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {inv.grand_total != null ? formatIDR(inv.grand_total) : "-"}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div>
              <Label>Tambah invoice gantung ke resi ini</Label>
              <InvoiceCheckList
                invoices={gantung}
                checked={tambah}
                onToggle={(no) => setTambah((c) => ({ ...c, [no]: !c[no] }))}
                kosong="Tidak ada invoice gantung untuk ditambahkan."
              />
            </div>
            <div>
              <Label htmlFor="resi-edit-file">Ganti berkas resi (opsional)</Label>
              <Input
                id="resi-edit-file"
                ref={fileRef}
                type="file"
                accept="image/*,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Batal</Button>
          <Button onClick={handleSave} disabled={saving || !detail}>{saving ? "Menyimpan..." : "Simpan Perubahan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailResiDialog({
  resiId, onOpenChange,
}: {
  resiId: number | null;
  onOpenChange: (o: boolean) => void;
}) {
  const [detail, setDetail] = React.useState<ResiDetail | null>(null);
  React.useEffect(() => {
    if (resiId == null) { setDetail(null); return; }
    resiDetail(resiId).then(setDetail).catch((err) => {
      if (isUnauthorized(err)) return;
      toast.error("Gagal memuat detail resi");
    });
  }, [resiId]);
  return (
    <Dialog open={resiId != null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Isi Resi {detail?.no_resi ?? ""}</DialogTitle>
          <DialogDescription>Invoice yang dikirim dalam resi ini.</DialogDescription>
        </DialogHeader>
        {!detail ? (
          <p className="text-sm text-muted-foreground">Memuat...</p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">
              Kurir: {detail.kurir ?? "-"} · Tgl kirim: {detail.tgl_kirim ? formatDate(detail.tgl_kirim) : "-"}
            </p>
            <div className="flex flex-col gap-1 rounded-md border border-border p-2">
              {detail.invoices.map((inv) => (
                <div key={inv.no_invoice} className="flex items-center justify-between text-sm">
                  <span className="font-medium">{inv.no_invoice}</span>
                  <span className="text-muted-foreground">{inv.site ?? "-"} · {inv.customer ?? "-"}</span>
                  <span>{inv.grand_total != null ? formatIDR(inv.grand_total) : "-"}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function InvoiceGantungInner() {
  const router = useRouter();
  const { selected } = useBadanUsaha();
  const [gantung, setGantung] = React.useState<InvoiceOut[]>([]);
  const [resi, setResi] = React.useState<ResiListItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [showUpload, setShowUpload] = React.useState(false);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [detailId, setDetailId] = React.useState<number | null>(null);
  const [toDelete, setToDelete] = React.useState<ResiListItem | null>(null);
  const [deleting, setDeleting] = React.useState(false);
  const [batalTarget, setBatalTarget] = React.useState<InvoiceOut | null>(null);
  const [membatalkan, setMembatalkan] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    Promise.all([listInvoices({ badan_usaha_kode: selected }), listResi()])
      .then(([inv, r]) => {
        setGantung(inv.filter((x) => x.tahap_dok !== "terkirim"));
        setResi(r);
      })
      .catch((err) => {
        if (isUnauthorized(err)) return;
        toast.error("Gagal memuat data Invoice Gantung");
      })
      .finally(() => setLoading(false));
  }, [selected]);

  React.useEffect(() => { load(); }, [load]);

  async function handleUnduh(r: ResiListItem) {
    try {
      const blob = await downloadResiFile(r.id);
      unduhBlob(blob, `resi_${r.no_resi || r.id}`);
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh berkas resi");
    }
  }

  async function handleUnduhInvoicePdf(noInvoice: string) {
    try {
      const blob = await downloadInvoicePdf(noInvoice);
      unduhBlob(blob, `Invoice_${noInvoice.replace(/\//g, "_")}`);
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh PDF invoice");
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

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      const res = await deleteResi(toDelete.id);
      toast.success(`Resi dihapus. ${res.invoice_balik_gantung.length} invoice kembali ke Invoice Gantung.`);
      setToDelete(null);
      load();
    } catch (err) {
      if (isUnauthorized(err)) return;
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus resi");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Invoice Gantung</h1>
        <p className="text-sm text-muted-foreground">
          Invoice yang sudah terbit tapi belum ada resi pengiriman. Unggah resi (boleh menggabung beberapa
          invoice) untuk memindahkannya ke Rekap Invoice.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Invoice Gantung ({gantung.length})</CardTitle>
          <Button onClick={() => setShowUpload(true)} disabled={gantung.length === 0} className="gap-2">
            <Send className="h-4 w-4" /> Unggah Resi Pengiriman
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No. Invoice</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Site</TableHead>
                <TableHead className="text-right">Volume</TableHead>
                <TableHead className="text-right">Harga Satuan</TableHead>
                <TableHead className="text-right">Grand Total</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground">Memuat...</TableCell></TableRow>
              )}
              {!loading && gantung.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground">Tidak ada invoice gantung — semua sudah ada resi.</TableCell></TableRow>
              )}
              {gantung.map((inv) => (
                <TableRow key={inv.no_invoice}>
                  <TableCell className="font-medium">{inv.no_invoice}</TableCell>
                  <TableCell>{inv.tgl_invoice ? formatDate(inv.tgl_invoice) : "-"}</TableCell>
                  <TableCell>{inv.site ?? "-"}</TableCell>
                  <TableCell className="text-right">{formatQty(inv.total_qty, inv.satuan)}</TableCell>
                  <TableCell className="text-right">{inv.total_qty ? formatIDR((inv.sub_total ?? inv.grand_total ?? 0) / inv.total_qty) : "-"}</TableCell>
                  <TableCell className="text-right">{inv.grand_total != null ? formatIDR(inv.grand_total) : "-"}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Unduh PDF Invoice saja"
                      onClick={() => handleUnduhInvoicePdf(inv.no_invoice)}
                      // InvoicePdfSoloButton marker (jangan dihapus, penanda idempoten patch)
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Batal Invoice"
                      onClick={() => setBatalTarget(inv)}
                      // BatalInvoiceButton marker (jangan dihapus, penanda idempoten patch)
                    >
                      <Ban className="h-4 w-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Resi Terunggah</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No. Resi</TableHead>
                <TableHead>Kurir</TableHead>
                <TableHead>Tgl Kirim</TableHead>
                <TableHead>Invoice</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!loading && resi.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground">Belum ada resi diunggah.</TableCell></TableRow>
              )}
              {resi.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.no_resi ?? "(tanpa nomor)"}</TableCell>
                  <TableCell>{r.kurir ?? "-"}</TableCell>
                  <TableCell>{r.tgl_kirim ? formatDate(r.tgl_kirim) : "-"}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{r.jml_invoice}</Badge>
                      <span className="max-w-xs truncate text-xs text-muted-foreground">{r.daftar_invoice}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" title="Lihat isi" onClick={() => setDetailId(r.id)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" title="Unduh berkas" onClick={() => handleUnduh(r)}>
                        <Download className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" title="Edit" onClick={() => setEditId(r.id)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" title="Hapus" onClick={() => setToDelete(r)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <UnggahResiDialog open={showUpload} onOpenChange={setShowUpload} gantung={gantung} onSaved={load} />
      <EditResiDialog resiId={editId} gantung={gantung} onOpenChange={(o) => !o && setEditId(null)} onSaved={load} />
      <DetailResiDialog resiId={detailId} onOpenChange={(o) => !o && setDetailId(null)} />

      <Dialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Hapus Resi?</DialogTitle>
            <DialogDescription>
              Resi {toDelete?.no_resi ?? "(tanpa nomor)"} akan dihapus. {toDelete?.jml_invoice ?? 0} invoice yang
              menempel akan KEMBALI ke Invoice Gantung. Tindakan ini tidak bisa dibatalkan.
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

      <Dialog open={!!batalTarget} onOpenChange={(o) => !o && setBatalTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Batalkan Invoice?</DialogTitle>
            <DialogDescription>
              Invoice {batalTarget?.no_invoice} akan dibatalkan. Qty PO yang terpotong invoice ini akan
              DIKEMBALIKAN, dan BAP yang terpakai akan DILEPAS supaya bisa dipakai lagi untuk invoice baru.
              Invoice tidak dihapus (tetap tercatat sebagai batal). Tindakan ini tidak bisa dibatalkan.
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

export default function InvoiceGantungPage() {
  return (
    <RequireAuth>
      <AppShell>
        <InvoiceGantungInner />
      </AppShell>
    </RequireAuth>
  );
}
