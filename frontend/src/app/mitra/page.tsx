"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, Building2, Pencil, FileText, Upload, Download, Trash2 } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import {
  ApiError,
  mitraTree,
  createMitraGroup,
  createMitraPT,
  mitraPTDetail,
  renameMitraGroup,
  renameMitraPT,
  listKontrak,
  uploadKontrak,
  deleteKontrak,
  downloadKontrak,
} from "@/lib/api";
import type { MitraGroup, MitraPTDetail, KontrakOut } from "@/lib/types";
import { formatQty, formatDate } from "@/lib/utils";
import { useBadanUsaha } from "@/lib/badan-usaha-context";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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

function KontrakDialog({ group, bu, onClose }: { group: MitraGroup | null; bu: string; onClose: () => void }) {
  const [items, setItems] = React.useState<KontrakOut[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [nomor, setNomor] = React.useState("");
  const [judul, setJudul] = React.useState("");
  const [tanggal, setTanggal] = React.useState("");
  const [masa, setMasa] = React.useState("");
  const [nilai, setNilai] = React.useState("");
  const [catatan, setCatatan] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [delId, setDelId] = React.useState<number | null>(null);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const load = React.useCallback(() => {
    if (!group) return;
    setLoading(true);
    listKontrak(group.id, bu)
      .then(setItems)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Gagal memuat kontrak"))
      .finally(() => setLoading(false));
  }, [group, bu]);

  React.useEffect(() => {
    if (group) load();
  }, [group, load]);

  function resetForm() {
    setFile(null);
    setNomor("");
    setJudul("");
    setTanggal("");
    setMasa("");
    setNilai("");
    setCatatan("");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function submitUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!group) return;
    if (!file) {
      toast.error("Pilih berkas kontrak dulu.");
      return;
    }
    setSaving(true);
    try {
      await uploadKontrak(group.id, file, {
        badan_usaha_kode: bu,
        nomor_kontrak: nomor.trim(),
        judul: judul.trim(),
        tanggal: tanggal || undefined,
        masa_berlaku: masa.trim(),
        nilai: nilai.trim(),
        catatan: catatan.trim(),
      });
      toast.success("Kontrak diunggah. Ringkasan akan diisi setelah Claude membacanya.");
      resetForm();
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunggah kontrak");
    } finally {
      setSaving(false);
    }
  }

  async function unduh(k: KontrakOut) {
    try {
      const blob = await downloadKontrak(k.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = k.original_filename || `kontrak_${k.id}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh kontrak");
    }
  }

  async function hapus(k: KontrakOut) {
    try {
      await deleteKontrak(k.id);
      toast.success("Kontrak dihapus.");
      setDelId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus kontrak");
    }
  }

  return (
    <Dialog open={group !== null} onOpenChange={(v) => { if (!v) { setDelId(null); onClose(); } }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Kontrak &mdash; {group?.nama}</DialogTitle>
          <DialogDescription>
            Dokumen kontrak payung untuk Group ini. Workspace aktif: <b>{bu}</b>. Setelah berkas
            diunggah, Claude membaca isinya lalu mengisi Ringkasan.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submitUpload} className="flex flex-col gap-3 rounded-md border border-border p-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kfile">Berkas kontrak (PDF/foto)</Label>
            <Input
              id="kfile"
              type="file"
              ref={fileRef}
              accept=".pdf,image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="knomor">Nomor kontrak</Label>
              <Input id="knomor" value={nomor} onChange={(e) => setNomor(e.target.value)} placeholder="mis. 001/KTR/2026" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="kjudul">Judul / perihal</Label>
              <Input id="kjudul" value={judul} onChange={(e) => setJudul(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ktgl">Tanggal</Label>
              <Input id="ktgl" type="date" value={tanggal} onChange={(e) => setTanggal(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="kmasa">Masa berlaku</Label>
              <Input id="kmasa" value={masa} onChange={(e) => setMasa(e.target.value)} placeholder="mis. s/d 31 Des 2026" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="knilai">Nilai (opsional)</Label>
              <Input id="knilai" value={nilai} onChange={(e) => setNilai(e.target.value)} placeholder="mis. 1.500.000.000" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="kcat">Catatan</Label>
              <Input id="kcat" value={catatan} onChange={(e) => setCatatan(e.target.value)} />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={saving} className="gap-1.5">
              <Upload className="h-4 w-4" /> {saving ? "Mengunggah..." : "Unggah Kontrak"}
            </Button>
          </div>
        </form>

        <div className="flex max-h-[45vh] flex-col gap-2 overflow-y-auto">
          {loading ? (
            <p className="text-sm text-muted-foreground">Memuat...</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Belum ada kontrak untuk workspace {bu}.</p>
          ) : (
            items.map((k) => (
              <div key={k.id} className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex flex-col">
                    <span className="text-sm font-semibold">
                      {k.nomor_kontrak || k.judul || k.original_filename || `Kontrak #${k.id}`}
                      {k.badan_usaha_kode ? (
                        <Badge variant="outline" className="ml-2 text-[10px]">{k.badan_usaha_kode}</Badge>
                      ) : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {k.judul && k.nomor_kontrak ? `${k.judul} · ` : ""}
                      {k.tanggal ? `Tgl ${formatDate(k.tanggal)}` : ""}
                      {k.masa_berlaku ? ` · ${k.masa_berlaku}` : ""}
                      {k.nilai != null ? ` · Rp ${k.nilai.toLocaleString("id-ID")}` : ""}
                    </span>
                    {k.catatan ? <span className="text-xs text-muted-foreground">{k.catatan}</span> : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {k.punya_file ? (
                      <button
                        type="button"
                        onClick={() => unduh(k)}
                        title="Unduh berkas kontrak"
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <Download className="h-4 w-4" />
                      </button>
                    ) : null}
                    {delId === k.id ? (
                      <span className="flex items-center gap-1 text-xs">
                        <button type="button" onClick={() => hapus(k)} className="font-medium text-destructive">Hapus?</button>
                        <button type="button" onClick={() => setDelId(null)} className="text-muted-foreground">batal</button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setDelId(k.id)}
                        title="Hapus kontrak"
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 rounded bg-muted/40 p-2 text-xs">
                  <span className="font-medium">Ringkasan: </span>
                  {k.ringkasan ? (
                    <span className="whitespace-pre-wrap">{k.ringkasan}</span>
                  ) : (
                    <span className="text-muted-foreground">Belum ada &mdash; akan diisi setelah Claude membaca kontrak.</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function MitraContent() {
  // Peran "viewer" (Pengamat, 4 Sep 2026): hanya melihat & membaca.
  const { user } = useAuth();
  const isViewer = user?.role === "viewer";

  const router = useRouter();
  const { selected } = useBadanUsaha();
  const [tree, setTree] = React.useState<MitraGroup[]>([]);
  const [loadingTree, setLoadingTree] = React.useState(true);
  const [selectedPt, setSelectedPt] = React.useState<number | null>(null);
  const [detail, setDetail] = React.useState<MitraPTDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = React.useState(false);
  const [kontrakGroup, setKontrakGroup] = React.useState<MitraGroup | null>(null);

  const [groupOpen, setGroupOpen] = React.useState(false);
  const [groupNama, setGroupNama] = React.useState("");
  const [groupAlamat, setGroupAlamat] = React.useState("");
  const [groupNpwp, setGroupNpwp] = React.useState("");
  const [ptOpen, setPtOpen] = React.useState(false);
  const [ptNama, setPtNama] = React.useState("");
  const [ptGroupId, setPtGroupId] = React.useState<string>("");
  const [renameTarget, setRenameTarget] = React.useState<{ kind: "group" | "pt"; id: number; nama: string } | null>(null);
  const [renameNama, setRenameNama] = React.useState("");
  const [renameAlamat, setRenameAlamat] = React.useState("");
  const [renameNpwp, setRenameNpwp] = React.useState("");

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
      await createMitraGroup(groupNama.trim(), groupAlamat.trim(), groupNpwp.trim());
      toast.success("Group ditambahkan.");
      setGroupOpen(false);
      setGroupNama("");
      setGroupAlamat("");
      setGroupNpwp("");
      loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menambah group");
    }
  }

  async function submitPt(e: React.FormEvent) {
    e.preventDefault();
    if (!ptNama.trim() || !ptGroupId) {
      toast.error("Pilih group dan isi nama PT.");
      return;
    }
    try {
      await createMitraPT(Number(ptGroupId), ptNama.trim());
      toast.success("PT ditambahkan.");
      setPtOpen(false);
      setPtNama("");
      loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menambah PT");
    }
  }

  async function submitRename(e: React.FormEvent) {
    e.preventDefault();
    if (!renameTarget || !renameNama.trim()) return;
    try {
      if (renameTarget.kind === "group") {
        await renameMitraGroup(renameTarget.id, renameNama.trim(), renameAlamat.trim(), renameNpwp.trim());
      } else {
        await renameMitraPT(renameTarget.id, renameNama.trim());
      }
      toast.success("Data diperbarui.");
      const t = renameTarget;
      setRenameTarget(null);
      setRenameNama("");
      setRenameAlamat("");
      setRenameNpwp("");
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
            Group &rarr; PT &rarr; PO aktif &rarr; Invoice. PT dianggap identik dengan
            site &mdash; PO aktif muncul otomatis kalau nama site PO ada di dalam nama PT.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={groupOpen} onOpenChange={setGroupOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="gap-1.5" disabled={isViewer}>
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
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="galamat">Alamat (opsional)</Label>
                  <Textarea id="galamat" value={groupAlamat} onChange={(e) => setGroupAlamat(e.target.value)} rows={2} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="gnpwp">No. NPWP (opsional)</Label>
                  <Input id="gnpwp" value={groupNpwp} onChange={(e) => setGroupNpwp(e.target.value)} placeholder="00.000.000.0-000.000" />
                </div>
                <DialogFooter>
                  <Button type="submit">Simpan</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
          <Dialog open={ptOpen} onOpenChange={setPtOpen}>
            <DialogTrigger asChild>
              <Button className="gap-1.5" disabled={tree.length === 0 || isViewer}>
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
                  <Input id="ptnama" value={ptNama} onChange={(e) => setPtNama(e.target.value)} placeholder="mis. Sesayap (tulis nama yang memuat nama site)" required />
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
                      onClick={() => { setRenameTarget({ kind: "group", id: g.id, nama: g.nama }); setRenameNama(g.nama); setRenameAlamat(g.alamat ?? ""); setRenameNpwp(g.npwp ?? ""); }}
                      className="ml-1 text-muted-foreground hover:text-foreground"
                      title="Ubah nama group"
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setKontrakGroup(g)}
                      className="text-muted-foreground hover:text-foreground"
                      title="Kelola kontrak group"
                    >
                      <FileText className="h-3 w-3" />
                    </button>
                  </div>
                  {(g.alamat || g.npwp) && (
                    <div className="pl-5 text-[11px] leading-tight text-muted-foreground">
                      {g.alamat ? <p>{g.alamat}</p> : null}
                      {g.npwp ? <p>NPWP: {g.npwp}</p> : null}
                    </div>
                  )}
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
                  onClick={() => { setRenameTarget({ kind: "pt", id: detail.pt.id, nama: detail.pt.nama }); setRenameNama(detail.pt.nama); }}
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

      <KontrakDialog group={kontrakGroup} bu={selected} onClose={() => setKontrakGroup(null)} />

      <Dialog open={renameTarget !== null} onOpenChange={(v) => { if (!v) { setRenameTarget(null); setRenameNama(""); setRenameAlamat(""); setRenameNpwp(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah {renameTarget?.kind === "group" ? "Group" : "PT"}</DialogTitle>
            <DialogDescription>
              {renameTarget?.kind === "group" ? "Perbaiki nama, alamat, dan NPWP kalau ada salah input." : "Perbaiki nama kalau ada salah input."}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitRename} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rnama">Nama baru</Label>
              <Input id="rnama" value={renameNama} onChange={(e) => setRenameNama(e.target.value)} required />
            </div>
            {renameTarget?.kind === "group" ? (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ralamat">Alamat (opsional)</Label>
                  <Textarea id="ralamat" value={renameAlamat} onChange={(e) => setRenameAlamat(e.target.value)} rows={2} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="rnpwp">No. NPWP (opsional)</Label>
                  <Input id="rnpwp" value={renameNpwp} onChange={(e) => setRenameNpwp(e.target.value)} placeholder="00.000.000.0-000.000" />
                </div>
              </>
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
