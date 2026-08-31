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
  deleteBAPNota,
  downloadBAPNota,
  listPO,
  listBAPNota,
  uploadBAPNota,
  mitraTree,
  konfirmasiBapMitra,
  previewInvoice,
  generateInvoice,
} from "@/lib/api";
import type { BAPNotaOut, InvoiceGenerateRequest, InvoicePreviewResult } from "@/lib/types";
import { GENERATE_INVOICE_SUPPORTED } from "@/lib/types";
import { formatDate, formatQty, formatIDR } from "@/lib/utils";

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

type PTOption = { id: number; nama: string; group: string };

const MAKS_BAP_PER_INVOICE = 4;

type WizardItem = {
  no_bap: string;
  site: string;
  qty: number;
  fileNames: string[];
  notaIds: number[];
};

export type WizardHandle = {
  addNotas: (notas: BAPNotaOut[]) => void;
  openUpload: () => void;
};

// Wizard "Terbit Invoice": 1 tempat, 3 langkah -- (1) unggah BAP (boleh banyak
// lembar/foto sekaligus, dikelompokkan otomatis per nomor BAP), (2) pratinjau
// (nomor invoice, alokasi PO, pajak) SEBELUM apa pun tersimpan, (3) generate
// nyata (memotong PO asli) HANYA setelah admin klik setuju. Menggantikan dialog
// "Generate Invoice" lama yang tadinya ada di halaman /invoices (30 Jul 2026).
//
// forwardRef (31 Jul 2026): kartu "BAP Belum Diterbitkan Invoice" di bawah bisa
// memuat BAP yang SUDAH terunggah (app_bap_nota) langsung ke sini tanpa unggah
// ulang -- inilah perbaikan akar masalah "unggah ulang ditolak" yang dilaporkan
// owner (BAP tetap ada di server, tapi state wizard di layar hilang begitu
// pindah halaman -- sekarang BAP itu tetap kelihatan & bisa dilanjutkan).
const TerbitInvoiceWizard = React.forwardRef<WizardHandle, { onGenerated: () => void; onUploaded: () => void }>(
  function TerbitInvoiceWizard({ onGenerated, onUploaded }, ref) {
  const { selected } = useBadanUsaha();
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [items, setItems] = React.useState<WizardItem[]>([]);
  const [invDate, setInvDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = React.useState<InvoicePreviewResult | null>(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [poSites, setPoSites] = React.useState<string[]>([]);

  React.useEffect(() => {
    listPO({ badan_usaha_kode: selected })
      .then((pos) =>
        setPoSites(
          [...new Set(pos.filter((p) => p.status === "aktif" && p.site).map((p) => p.site as string))].sort(),
        ),
      )
      .catch(() => setPoSites([]));
  }, [selected]);

  const uniqueSites = React.useMemo(
    () => Array.from(new Set(items.map((i) => i.site).filter(Boolean))),
    [items],
  );
  const site = uniqueSites[0] ?? "";
  const siteError =
    uniqueSites.length > 1
      ? `BAP yang diunggah punya site berbeda-beda (${uniqueSites.join(", ")}). Satu invoice hanya boleh 1 site -- klik Reset, lalu unggah terpisah per site.`
      : null;
  const supportedBu = GENERATE_INVOICE_SUPPORTED.includes(selected);
  const satuan = selected === "DKP" ? "kg" : "m3";

  async function handleFilesSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setUploading(true);
    setPreview(null);
    try {
      const results: BAPNotaOut[] = [];
      for (const file of files) {
        try {
          const nota = await uploadBAPNota(file, selected);
          results.push(nota);
        } catch (err) {
          toast.error(
            `Gagal unggah ${file.name}: ${err instanceof ApiError ? err.message : "error tidak diketahui"}`,
          );
        }
      }
      if (results.length > 0) {
        const existingKeys = new Set(items.map((it) => it.no_bap));
        const existingFiles = new Set(items.flatMap((it) => it.fileNames));
        const map = new Map<string, WizardItem>(
          items.map((it) => [it.no_bap, { ...it, fileNames: [...it.fileNames], notaIds: [...it.notaIds] }]),
        );
        const dobelFile: string[] = [];
        const dobelBap: string[] = [];
        const salahSite: string[] = [];
        let ditambah = 0;
        for (const nota of results) {
          const fname = nota.original_filename ?? "berkas";
          const key = nota.no_bap && nota.no_bap.trim() ? nota.no_bap.trim() : `(tanpa-nomor-${map.size + 1})`;
          if (existingFiles.has(fname)) {
            dobelFile.push(fname);
            continue;
          }
          if (existingKeys.has(key)) {
            dobelBap.push(key);
            continue;
          }
          const siteOcr = (nota.site ?? "").trim();
          if (poSites.length > 0 && siteOcr && !poSites.includes(siteOcr)) {
            salahSite.push(`${key} (site ${siteOcr})`);
            continue;
          }
          const siteFinal = poSites.includes(siteOcr) ? siteOcr : "";
          const existing = map.get(key);
          if (existing) {
            existing.fileNames = [...existing.fileNames, fname];
            existing.notaIds = [...existing.notaIds, nota.id];
          } else {
            map.set(key, {
              no_bap: key,
              site: siteFinal,
              qty: nota.qty_kg ?? nota.qty_m3 ?? 0,
              fileNames: [fname],
              notaIds: [nota.id],
            });
            ditambah += 1;
          }
          existingFiles.add(fname);
        }
        setItems(Array.from(map.values()));
        if (dobelFile.length > 0) {
          toast.error(`Berkas sama sudah diunggah, ditolak: ${[...new Set(dobelFile)].join(", ")}.`);
        }
        if (dobelBap.length > 0) {
          toast.error(`BAP dobel (nomor sudah ada), ditolak: ${[...new Set(dobelBap)].join(", ")}. Untuk multi-lembar, unggah semua lembar sekaligus dalam satu kali pilih file.`);
        }
        if (salahSite.length > 0) {
          toast.error(`BAP ditolak - site tidak terdaftar di PO workspace ${selected}: ${[...new Set(salahSite)].join(", ")}.`);
        }
        if (ditambah > 0) {
          toast.success(`${ditambah} BAP terbaca & terarsip. Cek daftar sebelum klik Selesai.`);
        }
      }
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
      // 2 Agu 2026: segarkan kartu "BAP Belum Diterbitkan Invoice" tiap ada
      // unggahan baru, supaya penanda "Kemungkinan kembar" langsung terlihat.
      onUploaded();
    }
  }

  // Muat BAP yang SUDAH terunggah sebelumnya (dari kartu "BAP Belum Diterbitkan
  // Invoice") langsung ke daftar wizard -- tanpa panggil uploadBAPNota lagi,
  // karena berkasnya sudah tercatat di app_bap_nota. Dipanggil lewat ref.
  function addNotasToItems(notas: BAPNotaOut[]) {
    if (notas.length === 0) return;
    setPreview(null);
    let ditambah = 0;
    const dilewati: string[] = [];
    setItems((prev) => {
      const existingKeys = new Set(prev.map((it) => it.no_bap));
      const existingFiles = new Set(prev.flatMap((it) => it.fileNames));
      const map = new Map<string, WizardItem>(
        prev.map((it) => [it.no_bap, { ...it, fileNames: [...it.fileNames], notaIds: [...it.notaIds] }]),
      );
      for (const nota of notas) {
        const fname = nota.original_filename ?? "berkas";
        const key = nota.no_bap && nota.no_bap.trim() ? nota.no_bap.trim() : `(tanpa-nomor-${map.size + 1})`;
        if (existingFiles.has(fname) || existingKeys.has(key) || map.has(key)) {
          dilewati.push(key);
          continue;
        }
        const siteOcr = (nota.site ?? "").trim();
        map.set(key, {
          no_bap: key,
          site: siteOcr,
          qty: nota.qty_kg ?? nota.qty_m3 ?? 0,
          fileNames: [fname],
          notaIds: [nota.id],
        });
        existingFiles.add(fname);
        ditambah += 1;
      }
      return Array.from(map.values());
    });
    if (dilewati.length > 0) {
      toast.error(`Sudah ada di daftar wizard, dilewati: ${[...new Set(dilewati)].join(", ")}.`);
    }
    if (ditambah > 0) {
      toast.success(`${ditambah} BAP dimuat ke wizard dari daftar tersimpan -- lanjutkan ke pratinjau di bawah.`);
    }
  }

  React.useImperativeHandle(ref, () => ({
    addNotas: addNotasToItems,
    openUpload: () => fileRef.current?.click(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }));

  function updateQty(no_bap: string, qty: number) {
    setItems((prev) => prev.map((it) => (it.no_bap === no_bap ? { ...it, qty } : it)));
    setPreview(null);
  }

  function updateSite(no_bap: string, site: string) {
    setItems((prev) => prev.map((it) => (it.no_bap === no_bap ? { ...it, site } : it)));
    setPreview(null);
  }

  function removeItem(no_bap: string) {
    setItems((prev) => prev.filter((it) => it.no_bap !== no_bap));
    setPreview(null);
  }

  function reset() {
    setItems([]);
    setPreview(null);
  }

  function buildRequest(): InvoiceGenerateRequest | null {
    if (items.length === 0) {
      toast.error("Unggah minimal satu BAP dulu.");
      return null;
    }
    if (siteError) {
      toast.error(siteError);
      return null;
    }
    if (items.length > MAKS_BAP_PER_INVOICE) {
      toast.error(`Maksimal ${MAKS_BAP_PER_INVOICE} BAP per invoice.`);
      return null;
    }
    if (!site) {
      toast.error("Site belum dipilih -- pilih site dari daftar PO dulu.");
      return null;
    }
    if (poSites.length > 0 && !poSites.includes(site)) {
      toast.error(`Site "${site}" tidak terdaftar di PO workspace ${selected}. Pilih dari daftar.`);
      return null;
    }
    if (items.some((it) => !it.qty || it.qty <= 0)) {
      toast.error("Semua BAP wajib punya volume (qty) lebih dari 0.");
      return null;
    }
    // BAP tanpa nomor dikirim dgn no_bap KOSONG (nomor tak dicetak di invoice);
    // identitas & anti-dobel-tagih pakai nota_ids (id unggahan app_bap_nota).
    const bersih = (k: string) => (k.startsWith("(tanpa-nomor") ? "" : k);
    return {
      badan_usaha_kode: selected,
      site,
      no_bap: bersih(items[0].no_bap),
      inv_date: invDate,
      items: items.map((it) => ({ no_bap: bersih(it.no_bap), qty: it.qty })),
      nota_ids: items.flatMap((it) => it.notaIds),
    };
  }

  async function handlePreview() {
    const body = buildRequest();
    if (!body) return;
    setPreviewing(true);
    try {
      const res = await previewInvoice(body);
      setPreview(res);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal membuat pratinjau.");
      setPreview(null);
    } finally {
      setPreviewing(false);
    }
  }

  async function handleGenerate() {
    const body = buildRequest();
    if (!body) return;
    setGenerating(true);
    try {
      const res = await generateInvoice(body);
      if (res.status === "success") {
        toast.success(`Invoice ${res.inv_no ?? ""} berhasil terbit.`);
        reset();
        onGenerated();
      } else {
        toast.error(res.message ?? "Gagal menerbitkan invoice.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menerbitkan invoice.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Card id="wizard-terbit-invoice">
      <CardHeader>
        <CardTitle className="text-base">Terbitkan Invoice dari BAP ({selected})</CardTitle>
        <p className="text-xs text-muted-foreground">
          Unggah BAP (boleh beberapa lembar/foto sekaligus, maksimal {MAKS_BAP_PER_INVOICE} nomor
          BAP per invoice). Beberapa halaman dengan nomor BAP yang sama dianggap satu BAP.
          Setelah itu, lihat pratinjau (nomor invoice, alokasi PO, pajak) sebelum benar-benar
          menerbitkan -- generate akan memotong PO asli.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!supportedBu ? (
          <p className="text-sm text-muted-foreground">
            Terbit invoice dari web belum didukung untuk badan usaha {selected}.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                ref={fileRef}
                type="file"
                accept="application/pdf,image/*"
                multiple
                className="hidden"
                onChange={handleFilesSelected}
              />
              {items.length === 0 ? (
                <Button
                  type="button"
                  className="gap-1.5"
                  disabled={uploading}
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload className="h-4 w-4" />
                  {uploading ? "Membaca dokumen..." : "Unggah BAP (bisa beberapa lembar)"}
                </Button>
              ) : (
                <>
                  <p className="text-sm font-medium">
                    BAP untuk 1 invoice ({items.length}/{MAKS_BAP_PER_INVOICE})
                  </p>
                  <Button type="button" variant="ghost" size="sm" onClick={reset}>
                    Reset
                  </Button>
                </>
              )}
            </div>

            {siteError ? <p className="text-sm text-destructive">{siteError}</p> : null}

            {items.length > 0 && !siteError ? (
              <div className="flex flex-col gap-3">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>No. BAP</TableHead>
                      <TableHead>Site</TableHead>
                      <TableHead>Volume ({satuan})</TableHead>
                      <TableHead>Halaman</TableHead>
                      <TableHead className="text-right">Aksi</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((it) => (
                      <TableRow key={it.no_bap}>
                        <TableCell className="font-medium">{it.no_bap}</TableCell>
                        <TableCell>
                          <Select
                            value={it.site || undefined}
                            onValueChange={(v) => updateSite(it.no_bap, v)}
                          >
                            <SelectTrigger className="w-40">
                              <SelectValue placeholder="Pilih site" />
                            </SelectTrigger>
                            <SelectContent>
                              {poSites.map((sName) => (
                                <SelectItem key={sName} value={sName}>
                                  {sName}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {poSites.length === 0 ? (
                            <p className="mt-1 text-[10px] text-amber-600">
                              Belum ada PO aktif untuk workspace ini.
                            </p>
                          ) : !it.site ? (
                            <p className="mt-1 text-[10px] text-amber-600">
                              Pilih site sesuai PO terdaftar.
                            </p>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            step="any"
                            className="w-28"
                            value={it.qty || ""}
                            onChange={(e) => updateQty(it.no_bap, Number(e.target.value))}
                          />
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {it.fileNames.length} lembar
                        </TableCell>
                        <TableCell className="text-right">
                          <Button type="button" variant="ghost" size="sm" onClick={() => removeItem(it.no_bap)}>
                            Hapus
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="wizard-tanggal">Tanggal Invoice</Label>
                    <Input
                      id="wizard-tanggal"
                      type="date"
                      value={invDate}
                      onChange={(e) => { setInvDate(e.target.value); setPreview(null); }}
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="gap-1.5"
                    disabled={uploading || items.length >= MAKS_BAP_PER_INVOICE}
                    onClick={() => fileRef.current?.click()}
                  >
                    <Upload className="h-4 w-4" />
                    {uploading ? "Membaca dokumen..." : "Unggah BAP lanjutan"}
                  </Button>
                  <Button type="button" disabled={previewing} onClick={handlePreview}>
                    {previewing ? "Menghitung..." : "Selesai — Lihat Pratinjau"}
                  </Button>
                  {items.length >= MAKS_BAP_PER_INVOICE ? (
                    <span className="text-xs text-muted-foreground">
                      Maksimal {MAKS_BAP_PER_INVOICE} BAP tercapai.
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}

            {preview ? (
              <Card className="border-dashed">
                <CardHeader>
                  <CardTitle className="text-sm">
                    Pratinjau Invoice {preview.inv_no_preview} -- {preview.site}
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">{preview.catatan}</p>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Deskripsi</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead>Harga</TableHead>
                        <TableHead className="text-right">Jumlah</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.items.map((it) => (
                        <TableRow key={it.urutan}>
                          <TableCell>{it.deskripsi}</TableCell>
                          <TableCell>{formatQty(it.qty, satuan)}</TableCell>
                          <TableCell>{formatIDR(it.harga)}</TableCell>
                          <TableCell className="text-right">{formatIDR(it.jumlah)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>

                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                      Sisa PO setelah dipotong:
                    </p>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>No. PO</TableHead>
                          <TableHead>Dipotong</TableHead>
                          <TableHead>Sisa Sebelum</TableHead>
                          <TableHead>Sisa Sesudah</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {preview.po_splits.map((s) => (
                          <TableRow key={s.po_no}>
                            <TableCell>{s.po_no}</TableCell>
                            <TableCell>{formatQty(s.qty_dipotong, satuan)}</TableCell>
                            <TableCell>{formatQty(s.sisa_sebelum, satuan)}</TableCell>
                            <TableCell>{formatQty(s.sisa_sesudah, satuan)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>

                  <div className="flex flex-col gap-1 rounded-md bg-accent/50 p-3 text-sm">
                    <div className="flex justify-between">
                      <span>Sub Total</span><span>{formatIDR(preview.sub_total)}</span>
                    </div>
                    {preview.dpp > 0 || preview.ppn > 0 ? (
                      <>
                        <div className="flex justify-between">
                          <span>DPP Nilai Lain</span><span>{formatIDR(preview.dpp)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>PPN 12%</span><span>{formatIDR(preview.ppn)}</span>
                        </div>
                      </>
                    ) : null}
                    <div className="flex justify-between font-semibold">
                      <span>Grand Total</span><span>{formatIDR(preview.grand_total)}</span>
                    </div>
                  </div>

                  <Button type="button" disabled={generating} onClick={handleGenerate}>
                    {generating ? "Menerbitkan..." : "Setuju & Terbitkan Invoice"}
                  </Button>
                </CardContent>
              </Card>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
});

// Kartu "BAP Belum Diterbitkan Invoice" (31 Jul 2026) -- menggantikan
// NotaCetakCard ("Arsip BAP") yang sebelumnya disembunyikan (SHOW_ARSIP_BAP)
// dan kartu "Daftar BAP Tercatat" (tabel `bap`, isinya justru BAP yang SUDAH
// terpakai invoice -- lihat catatan di bap.py::_tolak_bap_sudah_dipakai).
// Sumber data di sini: app_bap_nota WHERE dipakai_invoice IS NULL, supaya BAP
// yang sudah terunggah tetap kelihatan lintas navigasi halaman -- pemicu
// laporan owner "unggah ulang ditolak" adalah wizard yang lupa state begitu
// pindah halaman, padahal BAP-nya sudah tersimpan di server.
function BapBelumInvoiceCard({
  refreshTick,
  wizardRef,
}: {
  refreshTick: number;
  wizardRef: React.RefObject<WizardHandle | null>;
}) {
  const { selected } = useBadanUsaha();
  const router = useRouter();
  const [notaList, setNotaList] = React.useState<BAPNotaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selectedIds, setSelectedIds] = React.useState<Set<number>>(new Set());
  const [downloadingId, setDownloadingId] = React.useState<number | null>(null);
  const [hapusNota, setHapusNota] = React.useState<BAPNotaOut | null>(null);
  const [deletingId, setDeletingId] = React.useState<number | null>(null);

  const [ptOptions, setPtOptions] = React.useState<PTOption[]>([]);
  const [konfNota, setKonfNota] = React.useState<BAPNotaOut | null>(null);
  const [konfPt, setKonfPt] = React.useState<string>("");

  const load = React.useCallback(() => {
    setLoading(true);
    listBAPNota({ badan_usaha_kode: selected, include_downloaded: true, belum_invoice: true })
      .then((list) => {
        setNotaList(list);
        setSelectedIds(new Set());
      })
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat daftar BAP belum diinvoice");
      })
      .finally(() => setLoading(false));
  }, [selected, router]);

  React.useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, refreshTick]);

  React.useEffect(() => {
    mitraTree()
      .then((tree) =>
        setPtOptions(
          tree.flatMap((g) => g.pt.map((pt) => ({ id: pt.id, nama: pt.nama, group: g.nama }))),
        ),
      )
      .catch(() => setPtOptions([]));
  }, []);

  // Penanda "Kemungkinan kembar" (2 Agu 2026). BAP TANPA NOMOR tidak bisa
  // dideduplikasi otomatis oleh sistem (identitasnya = per unggahan, lihat
  // doc 12_bap_tanpa_nomor.md), sehingga berkas yang sama diunggah dua kali
  // menumpuk jadi arsip hantu yang selamanya berstatus "belum diinvoice"
  // (kejadian nyata: nota id 6 & 7 produksi, dibersihkan 2 Agu 2026).
  // Keputusan owner: unggahan TIDAK diblokir -- cukup DITANDAI supaya
  // ketahuan mata; centang yang benar utk invoice, hapus yang kembar.
  const kembarIds = React.useMemo(() => {
    const ember = new Map<string, number[]>();
    for (const n of notaList) {
      const vol = n.qty_kg ?? n.qty_m3;
      if (vol === null || vol === undefined) continue;
      const kunci = `${(n.tanggal ?? "").trim()}|${String(vol)}`;
      const arr = ember.get(kunci);
      if (arr) arr.push(n.id);
      else ember.set(kunci, [n.id]);
    }
    const hasil = new Set<number>();
    for (const arr of ember.values()) {
      if (arr.length > 1) arr.forEach((id) => hasil.add(id));
    }
    return hasil;
  }, [notaList]);

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleLanjutkan() {
    const notas = notaList.filter((n) => selectedIds.has(n.id));
    if (notas.length === 0) {
      toast.error("Pilih minimal satu BAP dulu.");
      return;
    }
    if (notas.length > MAKS_BAP_PER_INVOICE) {
      toast.error(`Maksimal ${MAKS_BAP_PER_INVOICE} BAP per invoice -- kurangi pilihan.`);
      return;
    }
    wizardRef.current?.addNotas(notas);
    setSelectedIds(new Set());
    document.getElementById("wizard-terbit-invoice")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleTambahBap() {
    document.getElementById("wizard-terbit-invoice")?.scrollIntoView({ behavior: "smooth", block: "start" });
    wizardRef.current?.openUpload();
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
      toast.success("Nota cetak diunduh (arsip tetap tersimpan).");
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

  async function handleHapus() {
    if (!hapusNota) return;
    setDeletingId(hapusNota.id);
    try {
      await deleteBAPNota(hapusNota.id);
      toast.success("Arsip BAP dihapus.");
      setHapusNota(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus arsip BAP.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">BAP Belum Diterbitkan Invoice ({selected})</CardTitle>
        <p className="text-xs text-muted-foreground">
          BAP yang sudah terunggah (dari wizard di atas atau bot Telegram Izawa AI) tapi belum
          dipakai untuk invoice mana pun. Daftar ini tetap tersimpan walau Anda pindah halaman --
          tidak perlu unggah ulang. Centang satu atau beberapa BAP (site harus sama, maksimal{" "}
          {MAKS_BAP_PER_INVOICE}), lalu klik &quot;Lanjutkan Terbit Invoice&quot;, atau klik
          &quot;Tambah BAP&quot; untuk unggah yang baru.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            disabled={selectedIds.size === 0}
            onClick={handleLanjutkan}
          >
            Lanjutkan Terbit Invoice{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
          </Button>
          <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={handleTambahBap}>
            <Upload className="h-4 w-4" />
            Tambah BAP
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8"></TableHead>
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
                <TableCell colSpan={10} className="text-center text-muted-foreground">
                  Memuat...
                </TableCell>
              </TableRow>
            ) : notaList.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="text-center text-muted-foreground">
                  Tidak ada BAP yang menunggu invoice.
                </TableCell>
              </TableRow>
            ) : (
              notaList.map((nota) => (
                <TableRow key={nota.id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-input"
                      checked={selectedIds.has(nota.id)}
                      onChange={() => toggleSelect(nota.id)}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    <div className="flex flex-col gap-0.5">
                      <span>{nota.no_bap ?? "(tidak terbaca)"}</span>
                      {kembarIds.has(nota.id) ? (
                        <Badge
                          variant="warning"
                          className="w-fit text-[10px]"
                          title="Ada BAP lain yang belum diinvoice dengan tanggal & volume persis sama. Pastikan ini bukan berkas yang sama diunggah dua kali."
                        >
                          Kemungkinan kembar
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
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
                    <div className="flex items-center justify-end gap-1.5">
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
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        disabled={deletingId === nota.id}
                        onClick={() => setHapusNota(nota)}
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

      <Dialog open={hapusNota !== null} onOpenChange={(v) => { if (!v) setHapusNota(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Hapus arsip BAP?</DialogTitle>
            <DialogDescription>
              No. BAP {hapusNota?.no_bap ?? "-"} · Site {hapusNota?.site ?? "-"}. Arsip &amp; nota cetaknya dihapus permanen dari server. Tindakan ini tidak bisa dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setHapusNota(null)}>
              Batal
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deletingId !== null}
              onClick={handleHapus}
            >
              {deletingId !== null ? "Menghapus..." : "Ya, hapus"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function BAPContent() {
  const [refreshTick, setRefreshTick] = React.useState(0);
  const wizardRef = React.useRef<WizardHandle | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Terbit Invoice</h1>
        <p className="text-sm text-muted-foreground">
          Satu tempat: unggah BAP, lihat pratinjau, lalu terbitkan invoice. BAP yang belum
          dipakai invoice tetap tersimpan di daftar bawah walau Anda pindah halaman.
        </p>
      </div>

      <TerbitInvoiceWizard
        ref={wizardRef}
        onGenerated={() => setRefreshTick((t) => t + 1)}
        onUploaded={() => setRefreshTick((t) => t + 1)}
      />

      <BapBelumInvoiceCard refreshTick={refreshTick} wizardRef={wizardRef} />
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
