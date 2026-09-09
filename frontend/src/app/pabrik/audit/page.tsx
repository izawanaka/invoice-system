"use client";

// /pabrik/audit -- Temuan Audit A1-A10 (B7). Admin/kepala: baca + tulis penjelasan. Owner: jalankan, tutup, terima usulan potongan.
import * as React from "react";
import { toast } from "sonner";
import { Play, Send } from "lucide-react";

import { Halaman, KartuRekap, Kosong, errMsg, fmtTgl, useLoad, usePeran } from "@/components/pabrik/ui";
import { jalankanAudit, listTemuan, penjelasanTemuan, terimaPotongan, tutupTemuan, type Temuan } from "@/lib/pabrik-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const TINGKAT: Record<string, "destructive" | "warning" | "outline"> = { flag: "destructive", peringatan: "warning", info: "outline" };

function Aksi({ t, onDone }: { t: Temuan; onDone: () => void }) {
  const { isOwner, bolehTulis } = usePeran();
  const [mode, setMode] = React.useState<null | "penjelasan" | "tutup">(null);
  const [teks, setTeks] = React.useState("");
  const [sibuk, setSibuk] = React.useState(false);
  if (t.status !== "terbuka") return null;
  async function kirim() {
    setSibuk(true);
    try {
      if (mode === "penjelasan") await penjelasanTemuan(t.id, teks); else await tutupTemuan(t.id, teks);
      toast.success(mode === "penjelasan" ? "Penjelasan tersimpan" : "Temuan ditutup"); setMode(null); setTeks(""); onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  async function terima() {
    if (!confirm(`Terima usulan potongan ${t.usulan_potongan_sak} sak?`)) return;
    try { await terimaPotongan(t.id); toast.success("Potongan dicatat, temuan ditutup"); onDone(); } catch (e) { toast.error(errMsg(e)); }
  }
  return (<div className="flex flex-wrap gap-1">
    {bolehTulis ? <Button size="sm" variant="outline" onClick={() => setMode("penjelasan")}>Penjelasan</Button> : null}
    {isOwner && t.usulan_potongan_sak ? <Button size="sm" variant="secondary" onClick={terima}>Terima potongan {t.usulan_potongan_sak} sak</Button> : null}
    {isOwner ? <Button size="sm" onClick={() => setMode("tutup")}>Tutup</Button> : null}
    <Dialog open={mode !== null} onOpenChange={(o) => !o && setMode(null)}><DialogContent>
      <DialogHeader><DialogTitle>{mode === "penjelasan" ? "Penjelasan dari lapangan" : "Tutup temuan"}</DialogTitle><DialogDescription>{t.pesan}</DialogDescription></DialogHeader>
      <Input value={teks} onChange={(e) => setTeks(e.target.value)} placeholder={mode === "penjelasan" ? "Apa yang terjadi (min. 5 huruf)" : "Catatan penutupan"} />
      <DialogFooter><Button variant="outline" onClick={() => setMode(null)}>Batal</Button><Button onClick={kirim} disabled={sibuk || teks.trim().length < 3}>Simpan</Button></DialogFooter>
    </DialogContent></Dialog>
  </div>);
}

export default function AuditPage() {
  const { isOwner } = usePeran();
  const [status, setStatus] = React.useState("terbuka");
  const temuan = useLoad(() => listTemuan(status), [status]);
  const [sibuk, setSibuk] = React.useState(false);
  async function jalankan(kirim: boolean) {
    setSibuk(true);
    try { const r = await jalankanAudit(kirim); toast.success(`Audit selesai: ${r.baru.length} baru, ${r.selesai_otomatis.length} selesai otomatis, ${r.terbuka.length} terbuka${kirim ? (r.telegram_terkirim ? " · Telegram terkirim" : " · Telegram GAGAL") : ""}`); temuan.reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSibuk(false); }
  }
  const rows = temuan.data ?? [];
  return (
    <Halaman judul="Temuan Audit" desc="Audit otomatis tiap pagi (A1–A10) dikirim ke Telegram owner. Tidak ada cek yang membedakan siapa pengetik (K2)." kembali="/pabrik/modul/harian"
      aksi={<div className="flex items-center gap-2">
        <Select value={status} onValueChange={setStatus}><SelectTrigger className="h-8 w-[170px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="terbuka">Terbuka</SelectItem><SelectItem value="ditutup">Ditutup owner</SelectItem><SelectItem value="selesai_otomatis">Selesai otomatis</SelectItem><SelectItem value="semua">Semua</SelectItem></SelectContent></Select>
        {isOwner ? (<><Button size="sm" variant="outline" className="gap-1" onClick={() => jalankan(false)} disabled={sibuk}><Play className="h-3.5 w-3.5" /> Jalankan</Button><Button size="sm" className="gap-1" onClick={() => jalankan(true)} disabled={sibuk}><Send className="h-3.5 w-3.5" /> Jalankan + Telegram</Button></>) : null}
      </div>}>
      <KartuRekap judul={`${rows.length} temuan`}>
        {rows.length === 0 ? <Kosong teks={status === "terbuka" ? "Tidak ada temuan terbuka — bersih." : "Tidak ada"} /> : (
          <div className="flex flex-col gap-3">{rows.map((t) => (
            <div key={t.id} className="flex flex-col gap-2 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2"><Badge variant={TINGKAT[t.tingkat] ?? "outline"}>{t.kode}</Badge><span className="text-sm font-medium">{t.nama_cek}</span><span className="ml-auto text-xs text-muted-foreground">ditemukan {fmtTgl(t.tanggal_audit)}{t.terakhir_dilihat !== t.tanggal_audit ? ` · terakhir ${fmtTgl(t.terakhir_dilihat)}` : ""}</span></div>
              <p className="text-sm">{t.pesan}</p>
              {t.penjelasan ? <p className="rounded-md bg-muted p-2 text-xs"><b>Penjelasan lapangan:</b> {t.penjelasan}</p> : null}
              {t.catatan_tutup ? <p className="text-xs text-muted-foreground">{t.status === "ditutup" ? "Ditutup" : "Selesai"}: {t.catatan_tutup}</p> : null}
              <Aksi t={t} onDone={temuan.reload} />
            </div>))}</div>)}
      </KartuRekap>
    </Halaman>
  );
}
