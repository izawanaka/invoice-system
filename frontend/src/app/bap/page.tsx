"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Download, Upload } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { isUnauthorized } from "@/lib/auth-context";
import {
  ApiError,
  downloadBAPNota,
  listBAP,
  listBAPNota,
  uploadBAPNota,
  mitraTree,
  konfirmasiBapMitra,
} from "@/lib/api";
import type { BAPNotaOut, BAPOut } from "@/lib/types";
import { formatDate, formatQty } from "@/lib/utils";

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
import { StatusBadge } from "@/components/status-badge";

type PTOption = { id: number; nama: string; group: string };

function NotaCetakCard() {
  const { selected } = useBadanUsaha();
  const [notaList, setNotaList] = React.useState<BAPNotaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [uploading, setUploading] = React.useState(false);
  const [downloadingId, setDownloadingId] = React.useState<number | null>(null);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const [ptOptions, setPtOptions] = React.useState<PTOption[]>([]);
  const [konfNota, setKonfNota] = React.useState<BAPNotaOut | null>(null);
  const [konfPt, setKonfPt] = React.useState<string>("");

  const load = React.useCallback(() => {
    setLoading(true);
    listBAPNota({ badan_usaha_kode: selected })
      .then(setNotaList)
      .catch((err) =>
        toast.error(err instanceof ApiError ? err.message : "Gagal memuat daftar nota cetak"),
      )
      .finally(() => setLoading(false));
  }, [selected]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => {
    mitraTree()
      .then((tree) =>
        setPtOptions(
          tree.flatMap((g) => g.pt.map((pt) => ({ id: pt.id, nama: pt.nama, group: g.nama }))),
        ),
      )
      .catch(() => setPtOptions([]));
  }, []);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const nota = await uploadBAPNota(file, selected);
      if (nota.mitra_pt_nama) {
        toast.success(
          `BAP ${nota.no_bap ?? ""} terbaca - terdeteksi untuk ${nota.mitra_pt_nama}.`,
        );
      } else {
        toast.message(
          `BAP terunggah${nota.no_bap ? " (" + nota.no_bap + ")" : ""} - sistem ragu untuk PT mana. Pilih PT di kolom \"Untuk (PT)\".`,
        );
      }
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunggah BAP.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDownload(nota: BAPNotaOut) {
    setDownloadingId(nota.id);
    try {
      const blob = await downloadBAPNota(nota.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nota_cetak_${(nota.no_bap ?? "bap").split("/").join("_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Nota cetak diunduh - item dihapus dari daftar (arsip tetap tersimpan).");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh nota cetak.");
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleKonfirmasi() {
    if (!konfNota || !konfPt) return;
    try {
      await konfirmasiBapMitra(konfNota.id, Number(konfPt));
      toast.success("BAP dicatat untuk PT terpilih.");
      setKonfNota(null);
      setKonfPt("");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan PT untuk BAP.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="text-base">Nota Cetak BAP ({selected})</CardTitle>
          <p className="text-xs text-muted-foreground">
            BAP bisa masuk dari DUA pintu: unggah di sini, atau kirim ke bot Telegram
            Izawa AI. Sistem menebak BAP ini untuk PT/mitra mana; kalau ragu, pilih PT
            di kolom "Untuk (PT)". Setelah nota diunduh, item hilang dari daftar (arsip tetap).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            ref={fileRef}
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            type="button"
            className="gap-1.5"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="h-4 w-4" />
            {uploading ? "Membaca dokumen..." : "Unggah BAP"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>No. BAP</TableHead>
              <TableHead>Site</TableHead>
              <TableHead>Tanggal</TableHead>
              <TableHead>Volume</TableHead>
              <TableHead>OCR</TableHead>
              <TableHead>Masuk Lewat</TableHead>
              <TableHead>Untuk (PT)</TableHead>
              <TableHead>Diunggah</TableHead>
              <TableHead className="text-right">Nota Cetak</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-muted-foreground">
                  Memuat...
                </TableCell>
              </TableRow>
            ) : notaList.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-muted-foreground">
                  Tidak ada nota cetak yang menunggu diunduh.
                </TableCell>
              </TableRow>
            ) : (
              notaList.map((nota) => (
                <TableRow key={nota.id}>
                  <TableCell className="font-medium">{nota.no_bap ?? "(tidak terbaca)"}</TableCell>
                  <TableCell>{nota.site ?? "-"}</TableCell>
                  <TableCell>{nota.tanggal ?? "-"}</TableCell>
                  <TableCell>
                    {nota.qty_kg
                      ? formatQty(nota.qty_kg, "kg")
                      : nota.qty_m3
                        ? formatQty(nota.qty_m3, "m3")
                        : "-"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {nota.jenis ?? "-"} · {nota.confidence ?? "-"}
                  </TableCell>
                  <TableCell className="text-xs">
                    <span className="rounded bg-accent px-1.5 py-0.5 capitalize text-accent-foreground">
                      {nota.sumber ?? "web"}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">
                    {nota.mitra_pt_nama ? (
                      <div className="flex flex-col gap-0.5">
                        <Badge variant="success" className="text-[10px]">{nota.mitra_pt_nama}</Badge>
                        <span className="text-[10px] text-muted-foreground">
                          {nota.deteksi_status === "auto" ? "terdeteksi otomatis" : "dipilih admin"}
                        </span>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="gap-1 text-xs"
                        onClick={() => { setKonfNota(nota); setKonfPt(""); }}
                      >
                        Pilih PT
                      </Button>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(nota.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      disabled={downloadingId === nota.id}
                      onClick={() => handleDownload(nota)}
                    >
                      <Download className="h-4 w-4" />
                      {downloadingId === nota.id ? "Mengunduh..." : "Unduh"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={konfNota !== null} onOpenChange={(v) => { if (!v) { setKonfNota(null); setKonfPt(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>BAP ini untuk PT mana?</DialogTitle>
            <DialogDescription>
              No. BAP {konfNota?.no_bap ?? "-"} · Site {konfNota?.site ?? "-"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label>PT (Mitra)</Label>
            <Select value={konfPt} onValueChange={setKonfPt}>
              <SelectTrigger>
                <SelectValue placeholder="Pilih PT" />
              </SelectTrigger>
              <SelectContent>
                {ptOptions.map((o) => (
                  <SelectItem key={o.id} value={String(o.id)}>
                    {o.nama} ({o.group})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {ptOptions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Belum ada PT. Tambahkan dulu di menu Mitra.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button onClick={handleKonfirmasi} disabled={!konfPt}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function BAPContent() {
  const { selected } = useBadanUsaha();
  const router = useRouter();
  const [bapList, setBapList] = React.useState<BAPOut[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    listBAP({ badan_usaha_kode: selected })
      .then(setBapList)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat data BAP");
      })
      .finally(() => setLoading(false));
  }, [selected, router]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Terbit Invoice</h1>
        <p className="text-sm text-muted-foreground">
          Unggah BAP (foto/PDF) untuk menerbitkan invoice, dan lihat BAP yang sudah tercatat.
        </p>
      </div>

      <NotaCetakCard />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Daftar BAP Tercatat ({selected})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No. BAP</TableHead>
                <TableHead>Site</TableHead>
                <TableHead>Tanggal BAP</TableHead>
                <TableHead>Volume</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Dibuat</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    Memuat...
                  </TableCell>
                </TableRow>
              ) : bapList.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    Tidak ada data BAP.
                  </TableCell>
                </TableRow>
              ) : (
                bapList.map((bap) => (
                  <TableRow key={bap.id}>
                    <TableCell className="font-medium">{bap.no_bap ?? "-"}</TableCell>
                    <TableCell>{bap.site ?? "-"}</TableCell>
                    <TableCell>{formatDate(bap.tgl_bap)}</TableCell>
                    <TableCell>{formatQty(bap.total_qty, bap.satuan)}</TableCell>
                    <TableCell>
                      <StatusBadge status={bap.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(bap.created_at)}
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

export default function BAPPage() {
  return (
    <RequireAuth>
      <AppShell>
        <BAPContent />
      </AppShell>
    </RequireAuth>
  );
}
