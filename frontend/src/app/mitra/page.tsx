"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, Building2, Pencil } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { isUnauthorized } from "@/lib/auth-context";
import {
  ApiError,
  mitraTree,
  createMitraGroup,
  createMitraPT,
  mitraPTDetail,
  renameMitraGroup,
  renameMitraPT,
} from "@/lib/api";
import type { MitraGroup, MitraPTDetail } from "@/lib/types";
import { formatQty, formatDate } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const TAHAP_LABEL: Record<string, string> = {
  terbit: "Terbit",
  ke_konsultan: "Di Konsultan",
  faktur_ada: "Faktur Pajak Ada",
  terkirim: "Terkirim",
};

function MitraContent() {
  const router = useRouter();
  const [tree, setTree] = React.useState<MitraGroup[]>([]);
  const [loadingTree, setLoadingTree] = React.useState(true);
  const [selectedPt, setSelectedPt] = React.useState<number | null>(null);
  const [detail, setDetail] = React.useState<MitraPTDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = React.useState(false);

  const [groupOpen, setGroupOpen] = React.useState(false);
  const [groupNama, setGroupNama] = React.useState("");
  const [ptOpen, setPtOpen] = React.useState(false);
  const [ptNama, setPtNama] = React.useState("");
  const [ptSite, setPtSite] = React.useState("");
  const [ptGroupId, setPtGroupId] = React.useState<string>("");
  const [renameTarget, setRenameTarget] = React.useState<{ kind: "group" | "pt"; id: number; nama: string; site?: string | null } | null>(null);
  const [renameNama, setRenameNama] = React.useState("");
  const [renameSite, setRenameSite] = React.useState("");

  const loadTree = React.useCallback(() => {
    setLoadingTree(true);
    mitraTree()
      .then(setTree)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat data mitra");
      })
      .finally(() => setLoadingTree(false));
  }, [router]);

  React.useEffect(() => {
    loadTree();
  }, [loadTree]);

  const loadDetail = React.useCallback((ptId: number) => {
    setLoadingDetail(true);
    mitraPTDetail(ptId)
      .then(setDetail)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Gagal memuat detail PT"))
      .finally(() => setLoadingDetail(false));
  }, []);

  React.useEffect(() => {
    if (selectedPt != null) loadDetail(selectedPt);
  }, [selectedPt, loadDetail]);

  async function submitGroup(e: React.FormEvent) {
    e.preventDefault();
    if (!groupNama.trim()) return;
    try {
      await createMitraGroup(groupNama.trim());
      toast.success("Group ditambahkan.");
      setGroupOpen(false);
      setGroupNama("");
      loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menambah group");
    }
  }

  async function submitPt(e: React.FormEvent) {
    e.preventDefault();
    if (!ptNama.trim() || !ptGroupId || !ptSite.trim()) {
      toast.error("Pilih group, isi nama PT, dan isi site.");
      return;
    }
    try {
      await createMitraPT(Number(ptGroupId), ptNama.trim(), ptSite.trim());
      toast.success("PT ditambahkan.");
      setPtOpen(false);
      setPtNama("");
      setPtSite("");
      loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menambah PT");
    }
  }

  async function submitRename(e: React.FormEvent) {
    e.preventDefault();
    if (!renameTarget || !renameNama.trim()) return;
    if (renameTarget.kind === "pt" && !renameSite.trim()) {
      toast.error("Isi site PT.");
      return;
    }
    try {
      if (renameTarget.kind === "group") {
        await renameMitraGroup(renameTarget.id, renameNama.trim());
      } else {
        await renameMitraPT(renameTarget.id, renameNama.trim(), renameSite.trim());
      }
      toast.success("Nama diperbarui.");
      const t = renameTarget;
      setRenameTarget(null);
      setRenameNama("");
      setRenameSite("");
      loadTree();
      if (t.kind === "pt" && selectedPt === t.id) loadDetail(t.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal memperbarui nama");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Mitra</h1>
          <p className="text-sm text-muted-foreground">
            Group &rarr; PT &rarr; PO aktif &rarr; Invoice. PO aktif muncul otomatis
            berdasarkan site PT; invoice mengikuti PO-nya.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={groupOpen} onOpenChange={setGroupOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="gap-1.5">
                <Plus className="h-4 w-4" /> Group
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Tambah Group</DialogTitle>
                <DialogDescription>Kelompok yang membawahi beberapa PT.</DialogDescription>
              </DialogHeader>
              <form onSubmit={submitGroup} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="gnama">Nama Group</Label>
                  <Input id="gnama" value={groupNama} onChange={(e) => setGroupNama(e.target.value)} required />
                </div>
                <DialogFooter>
                  <Button type="submit">Simpan</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
          <Dialog open={ptOpen} onOpenChange={setPtOpen}>
            <DialogTrigger asChild>
              <Button className="gap-1.5" disabled={tree.length === 0}>
                <Plus className="h-4 w-4" /> PT
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Tambah PT</DialogTitle>
                <DialogDescription>Customer/PT di bawah sebuah Group.</DialogDescription>
              </DialogHeader>
              <form onSubmit={submitPt} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Group</Label>
                  <Select value={ptGroupId} onValueChange={setPtGroupId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Pilih group" />
                    </SelectTrigger>
                    <SelectContent>
                      {tree.map((g) => (
                        <SelectItem key={g.id} value={String(g.id)}>{g.nama}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ptnama">Nama PT</Label>
                  <Input id="ptnama" value={ptNama} onChange={(e) => setPtNama(e.target.value)} required />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ptsite">Site</Label>
                  <Input id="ptsite" value={ptSite} onChange={(e) => setPtSite(e.target.value)} placeholder="mis. Sesayap" required />
                </div>
                <DialogFooter>
                  <Button type="submit">Simpan</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Daftar Group &amp; PT</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {loadingTree ? (
              <p className="text-sm text-muted-foreground">Memuat...</p>
            ) : tree.length === 0 ? (
              <p className="text-sm text-muted-foreground">Belum ada Group. Tambahkan dulu.</p>
            ) : (
              tree.map((g) => (
                <div key={g.id} className="flex flex-col gap-1">
                  <div className="flex items-center gap-1.5 text-sm font-semibold">
                    <Building2 className="h-4 w-4 text-muted-foreground" /> {g.nama}
                    <button
                      type="button"
                      onClick={() => { setRenameTarget({ kind: "group", id: g.id, nama: g.nama }); setRenameNama(g.nama); }}
                      className="ml-1 text-muted-foreground hover:text-foreground"
                      title="Ubah nama group"
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="flex flex-col gap-0.5 pl-5">
                    {g.pt.length === 0 ? (
                      <span className="text-xs text-muted-foreground">(belum ada PT)</span>
                    ) : (
                      g.pt.map((pt) => (
                        <button
                          key={pt.id}
                          type="button"
                          onClick={() => setSelectedPt(pt.id)}
                          className={
                            "flex items-center justify-between rounded-md px-2 py-1 text-left text-sm transition-colors " +
                            (selectedPt === pt.id
                              ? "bg-accent text-accent-foreground"
                              : "hover:bg-accent hover:text-accent-foreground")
                          }
                        >
                          <span>{pt.nama}</span>
                          <Badge variant="outline" className="text-[10px]">{pt.jml_po_aktif} PO</Badge>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">
              {detail ? detail.pt.nama : "Detail PT"}
              {detail?.pt.group_nama ? (
                <span className="ml-2 text-xs font-normal text-muted-foreground">({detail.pt.group_nama})</span>
              ) : null}
              {detail ? (
                <button
                  type="button"
                  onClick={() => { setRenameTarget({ kind: "pt", id: detail.pt.id, nama: detail.pt.nama, site: detail.pt.site }); setRenameNama(detail.pt.nama); setRenameSite(detail.pt.site ?? ""); }}
                  className="ml-2 align-middle text-muted-foreground hover:text-foreground"
                  title="Ubah nama PT"
                >
                  <Pencil className="inline h-3.5 w-3.5" />
                </button>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {selectedPt == null ? (
              <p className="text-sm text-muted-foreground">Pilih PT di kiri untuk melihat PO aktif &amp; invoice-nya.</p>
            ) : loadingDetail || !detail ? (
              <p className="text-sm text-muted-foreground">Memuat...</p>
            ) : (
              <>
                {detail.po_terhubung.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Belum ada PO yang ditautkan ke PT ini.</p>
                ) : (
                  detail.po_terhubung.map((po) => (
                    <div key={po.po_id} className="rounded-md border border-border">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-card px-3 py-2">
                        <div className="flex flex-col">
                          <span className="text-sm font-semibold">
                            {po.po_no}
                            <span className="ml-2 text-xs font-normal text-muted-foreground">
                              {po.badan_usaha_kode} · {po.site ?? "-"}
                            </span>
                          </span>
                          <span className="text-sm font-bold text-foreground">
                            Sisa {po.sisa_qty != null ? formatQty(po.sisa_qty, po.satuan) : "-"} · Terpakai {po.pct_used != null ? `${po.pct_used.toFixed(1)}%` : "0%"}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={po.status === "aktif" ? "success" : "secondary"}>{po.status}</Badge>
                        </div>
                      </div>
                      {po.invoices.length === 0 ? (
                        <p className="px-3 py-2 text-xs text-muted-foreground">Belum ada invoice terbit dari PO ini.</p>
                      ) : (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>No. Invoice</TableHead>
                              <TableHead>Tanggal</TableHead>
                              <TableHead>Volume</TableHead>
                              <TableHead>Tahap</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {po.invoices.map((inv) => (
                              <TableRow key={inv.no_invoice}>
                                <TableCell className="font-medium">{inv.no_invoice}</TableCell>
                                <TableCell>{formatDate(inv.tgl_invoice)}</TableCell>
                                <TableCell>{inv.total_qty != null ? formatQty(inv.total_qty, inv.satuan) : "-"}</TableCell>
                                <TableCell>
                                  <Badge variant="outline" className="text-[10px]">
                                    {inv.tahap_dok ? (TAHAP_LABEL[inv.tahap_dok] ?? inv.tahap_dok) : "-"}
                                  </Badge>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      )}
                    </div>
                  ))
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={renameTarget !== null} onOpenChange={(v) => { if (!v) { setRenameTarget(null); setRenameNama(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah Nama {renameTarget?.kind === "group" ? "Group" : "PT"}</DialogTitle>
            <DialogDescription>Perbaiki nama kalau ada salah input.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitRename} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rnama">Nama baru</Label>
              <Input id="rnama" value={renameNama} onChange={(e) => setRenameNama(e.target.value)} required />
            </div>
            {renameTarget?.kind === "pt" ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rsite">Site</Label>
                <Input id="rsite" value={renameSite} onChange={(e) => setRenameSite(e.target.value)} required />
              </div>
            ) : null}
            <DialogFooter>
              <Button type="submit">Simpan</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function MitraPage() {
  return (
    <RequireAuth>
      <AppShell>
        <MitraContent />
      </AppShell>
    </RequireAuth>
  );
}
