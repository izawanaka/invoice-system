"use client";

// /pabrik/lot -- Lot & Tahap (B2). K9: tahap tengah hanya status + tanggal; siap_karung minta EC/kadar air; habis = rendemen final.
import * as React from "react";
import { toast } from "sonner";

import { Halaman, KartuInput, KartuRekap, Field, Kosong, errMsg, fmtN, fmtTgl, today, useLoad, usePeran } from "@/components/pabrik/ui";
import { bukaLot, listLot, listTahap, ubahTahap, type Lot, type Tahap } from "@/lib/pabrik-api";
import { listPetak } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const URUT = ["curah", "giling", "basah", "jemur", "siap_karung", "habis"];
const LABEL: Record<string, string> = { curah: "Curah", giling: "Giling", basah: "Basah", jemur: "Jemur", siap_karung: "Siap karung", habis: "Habis" };
const WARNA: Record<string, "outline" | "secondary" | "warning" | "success" | "default"> = { curah: "outline", giling: "secondary", basah: "secondary", jemur: "warning", siap_karung: "success", habis: "default" };

function DialogTahap({ lot, onDone }: { lot: Lot; onDone: () => void }) {
  const berikut = URUT[URUT.indexOf(lot.status) + 1];
  const [open, setOpen] = React.useState(false);
  const [tgl, setTgl] = React.useState(today());
  const [ec, setEc] = React.useState(""); const [ka, setKa] = React.useState(""); const [cat, setCat] = React.useState("");
  const [riwayat, setRiwayat] = React.useState<Tahap[] | null>(null);
  const [sibuk, setSibuk] = React.useState(false);
  if (!berikut) return null;
  async function buka() { setOpen(true); try { setRiwayat(await listTahap(lot.lot_id)); } catch { setRiwayat([]); } }
  async function simpan() {
    setSibuk(true);
    try {
      const r = await ubahTahap(lot.lot_id, { tahap: berikut, tanggal_mulai: tgl, ec: ec ? Number(ec) : undefined, kadar_air_pct: ka ? Number(ka) : undefined, catatan: cat || undefined });
      toast.success(berikut === "habis" ? `Lot ${r.nomor_lot} habis. Rendemen final ${r.rendemen ?? "—"} sak/kubik` : `Lot ${r.nomor_lot} → ${LABEL[berikut]}`);
      setOpen(false); onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  return (<>
    <Button size="sm" variant={berikut === "habis" ? "destructive" : "default"} onClick={buka}>→ {LABEL[berikut]}</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent>
      <DialogHeader><DialogTitle>{lot.petak} · {lot.nomor_lot}: {LABEL[lot.status]} → {LABEL[berikut]}</DialogTitle>
        <DialogDescription>{berikut === "habis" ? "Lot ditutup; rendemen final = sak jadi ÷ kubik masuk, diuji ke kisaran wajar." : berikut === "siap_karung" ? "Isi EC & kadar air bila alat tersedia (wajib bila parameter batas sudah diisi owner)." : "Tahap hanya maju satu langkah, tanpa angka volume (K9)."}</DialogDescription></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Tanggal mulai"><Input type="date" value={tgl} onChange={(e) => setTgl(e.target.value)} /></Field>
        {berikut === "siap_karung" ? (<><Field label="EC (mS/cm)"><Input type="number" step="0.01" value={ec} onChange={(e) => setEc(e.target.value)} /></Field><Field label="Kadar air (%)"><Input type="number" step="0.1" value={ka} onChange={(e) => setKa(e.target.value)} /></Field></>) : null}
        <Field label="Catatan"><Input value={cat} onChange={(e) => setCat(e.target.value)} /></Field>
      </div>
      {riwayat ? <p className="text-xs text-muted-foreground">Riwayat: {riwayat.map((t) => `${LABEL[t.tahap]} ${fmtTgl(t.tanggal_mulai)}`).join(" → ") || "—"}</p> : null}
      <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Batal</Button><Button onClick={simpan} disabled={sibuk}>Simpan tahap</Button></DialogFooter>
    </DialogContent></Dialog>
  </>);
}

export default function LotPage() {
  const { bolehTulis } = usePeran();
  const [semua, setSemua] = React.useState(false);
  React.useEffect(() => { if (new URLSearchParams(window.location.search).get("tab") === "ringkas") setSemua(true); }, []);
  const lot = useLoad(() => listLot(!semua), [semua]);
  const petak = useLoad(listPetak, []);
  const [petakId, setPetakId] = React.useState(""); const [tgl, setTgl] = React.useState(today()); const [sibuk, setSibuk] = React.useState(false);
  const petakBebas = (petak.data ?? []).filter((p) => p.aktif && !(lot.data ?? []).some((l) => l.petak_id === p.id && l.status !== "habis"));
  async function buka() {
    if (!petakId) return toast.error("Pilih petak");
    setSibuk(true);
    try { const r = await bukaLot({ petak_id: Number(petakId), tanggal_buka: tgl }); toast.success(`Lot ${r.nomor_lot} dibuka di petak ${r.petak}`); setPetakId(""); lot.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = lot.data ?? [];
  return (
    <Halaman judul="Lot & Tahap" desc="1 petak = 1 lot aktif (P6). Alur: curah → giling → basah → jemur → siap karung → habis." kembali="/pabrik/modul/bahan"
      aksi={<Button variant="outline" size="sm" onClick={() => setSemua((v) => !v)}>{semua ? "Hanya lot aktif" : "Tampilkan lot habis"}</Button>}>
      {bolehTulis ? (
        <KartuInput judul="Buka lot baru" desc="Nomor lot otomatis (tahun-urut). Petak yang masih punya lot aktif tidak bisa dipilih.">
          <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto] sm:items-end">
            <Field label="Petak"><Select value={petakId} onValueChange={setPetakId}><SelectTrigger><SelectValue placeholder={petakBebas.length ? "Pilih petak kosong" : "Semua petak terpakai"} /></SelectTrigger>
              <SelectContent>{petakBebas.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.nomor}</SelectItem>)}</SelectContent></Select></Field>
            <Field label="Tanggal buka"><Input type="date" value={tgl} onChange={(e) => setTgl(e.target.value)} /></Field>
            <Button onClick={buka} disabled={sibuk}>Buka lot</Button>
          </div>
        </KartuInput>) : null}
      <KartuRekap judul={semua ? "Semua lot" : "Lot aktif"} desc="Sisa WIP = estimasi (kubik − sak ÷ rendemen standar), bukan angka ukur.">
        {rows.length === 0 ? <Kosong teks="Belum ada lot" /> : (
          <Table><TableHeader><TableRow><TableHead>Petak</TableHead><TableHead>Lot</TableHead><TableHead>Tahap</TableHead><TableHead>Buka</TableHead><TableHead className="text-right">Kubik</TableHead><TableHead className="text-right">Sak jadi</TableHead><TableHead className="text-right">Lolos QC</TableHead><TableHead className="text-right">Rendemen</TableHead><TableHead className="text-right">Sisa WIP</TableHead><TableHead className="text-right">Umur</TableHead>{bolehTulis ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>{rows.map((l) => (
              <TableRow key={l.lot_id}>
                <TableCell className="font-medium">{l.petak}</TableCell><TableCell>{l.nomor_lot}</TableCell>
                <TableCell><Badge variant={WARNA[l.status]}>{LABEL[l.status]}</Badge>{l.lewat_batas_karung ? <Badge variant="destructive" className="ml-1">lewat batas</Badge> : null}</TableCell>
                <TableCell>{fmtTgl(l.tanggal_buka)}</TableCell><TableCell className="text-right">{fmtN(l.kubik_masuk, 2)}</TableCell><TableCell className="text-right">{l.sak_jadi}</TableCell><TableCell className="text-right">{l.sak_lolos_qc}</TableCell>
                <TableCell className="text-right">{l.rendemen ?? "—"}</TableCell><TableCell className="text-right">{l.sisa_wip_estimasi_kubik === null ? "—" : fmtN(l.sisa_wip_estimasi_kubik, 2)}</TableCell><TableCell className="text-right">{l.umur_hari} hr</TableCell>
                {bolehTulis ? <TableCell className="text-right"><DialogTahap lot={l} onDone={lot.reload} /></TableCell> : null}
              </TableRow>))}</TableBody></Table>)}
      </KartuRekap>
    </Halaman>
  );
}
