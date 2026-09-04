"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Copy, KeyRound, Plus, ShieldCheck, UserCog } from "lucide-react";

import { RequireAuth } from "@/components/require-auth";
import { AppShell } from "@/components/app-shell";
import { isUnauthorized, useAuth } from "@/lib/auth-context";
import {
  ApiError,
  changePassword,
  createUser,
  listUsers,
  resetUserPassword,
  updateUser,
} from "@/lib/api";
import type { Role, UserOut } from "@/lib/types";
import { formatDate } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/** Password sementara hanya bisa dilihat SEKALI (backend tidak menyimpan versi
 * mentahnya). Dialog ini sengaja tidak bisa ditutup tanpa sadar: tombolnya
 * bertuliskan konfirmasi bahwa password sudah disalin. */
function PasswordSekaliDialog({
  data,
  onClose,
}: {
  data: { nama: string; email: string; password: string } | null;
  onClose: () => void;
}) {
  async function salin() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.password);
      toast.success("Password disalin ke clipboard.");
    } catch {
      toast.error("Browser menolak akses clipboard — salin manual dari kotak di atas.");
    }
  }

  return (
    <Dialog open={data !== null} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Password untuk {data?.nama}</DialogTitle>
          <DialogDescription>
            Salin sekarang dan kirimkan ke yang bersangkutan lewat jalur pribadi. Password ini
            <strong> tidak bisa dilihat lagi</strong> setelah dialog ditutup — kalau hilang, terbitkan
            ulang lewat tombol Reset Password.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <Label className="text-xs text-muted-foreground">Email login</Label>
            <p className="font-mono text-sm">{data?.email}</p>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Password sementara</Label>
            <div className="flex items-center gap-2">
              <code className="flex-1 select-all rounded-md border border-border bg-muted px-3 py-2 font-mono text-base tracking-wide">
                {data?.password}
              </code>
              <Button type="button" variant="outline" size="icon" onClick={salin} title="Salin">
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Minta yang bersangkutan segera menggantinya sendiri lewat menu Pengaturan → Ganti
            Password setelah login pertama.
          </p>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Sudah saya salin</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BuatAkunDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (hasil: { nama: string; email: string; password: string }) => void;
}) {
  const [email, setEmail] = React.useState("");
  const [nama, setNama] = React.useState("");
  const [role, setRole] = React.useState<Role>("staff");
  const [submitting, setSubmitting] = React.useState(false);

  function reset() {
    setEmail("");
    setNama("");
    setRole("staff");
  }

  async function submit() {
    if (!email.trim() || !nama.trim()) {
      toast.error("Nama dan email wajib diisi.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await createUser({ email: email.trim(), nama: nama.trim(), role });
      onOpenChange(false);
      reset();
      onCreated({
        nama: res.user.nama,
        email: res.user.email,
        password: res.password_sementara,
      });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal membuat akun.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Buat Akun Baru</DialogTitle>
          <DialogDescription>
            Password dibuat otomatis oleh sistem dan ditampilkan sekali setelah akun jadi.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nama">Nama</Label>
            <Input
              id="nama"
              value={nama}
              onChange={(e) => setNama(e.target.value)}
              placeholder="Nama lengkap"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email (dipakai untuk login)</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nama@contoh.com"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role">Peran</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="staff">Staf — input data, tidak melihat pelunasan</SelectItem>
                <SelectItem value="viewer">Pengamat — hanya melihat & membaca, termasuk pelunasan</SelectItem>
                <SelectItem value="owner">Owner — akses penuh termasuk pelunasan & akun</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Staf boleh mencatat PO, mengunggah scan PO & BAP, menerbitkan invoice, mengunggah
              faktur pajak, dan mencetak paket. Yang tidak bisa dilihat/diubah staf: status
              pelunasan invoice dan pengelolaan akun.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Batal
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? "Menyimpan..." : "Buat Akun"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditAkunDialog({
  target,
  onOpenChange,
  onSaved,
}: {
  target: UserOut | null;
  onOpenChange: (v: boolean) => void;
  onSaved: () => void;
}) {
  const [nama, setNama] = React.useState("");
  const [role, setRole] = React.useState<Role>("staff");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (target) {
      setNama(target.nama);
      setRole(target.role);
    }
  }, [target]);

  async function submit() {
    if (!target) return;
    setSubmitting(true);
    try {
      await updateUser(target.id, { nama: nama.trim(), role });
      toast.success("Akun diperbarui.");
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal memperbarui akun.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ubah Akun</DialogTitle>
          <DialogDescription>{target?.email}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-nama">Nama</Label>
            <Input id="edit-nama" value={nama} onChange={(e) => setNama(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-role">Peran</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger id="edit-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="staff">Staf</SelectItem>
                <SelectItem value="viewer">Pengamat</SelectItem>
                <SelectItem value="owner">Owner</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Batal
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? "Menyimpan..." : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GantiPasswordCard() {
  const [lama, setLama] = React.useState("");
  const [baru, setBaru] = React.useState("");
  const [ulang, setUlang] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  async function submit() {
    if (baru.length < 8) {
      toast.error("Password baru minimal 8 karakter.");
      return;
    }
    if (baru !== ulang) {
      toast.error("Ketikan ulang password baru tidak sama.");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(lama, baru);
      toast.success("Password berhasil diganti.");
      setLama("");
      setBaru("");
      setUlang("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengganti password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4" /> Ganti Password Saya
        </CardTitle>
        <CardDescription>
          Berlaku untuk akun yang sedang login sekarang. Minimal 8 karakter.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:max-w-sm">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-lama">Password lama</Label>
          <Input
            id="pw-lama"
            type="password"
            value={lama}
            onChange={(e) => setLama(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-baru">Password baru</Label>
          <Input
            id="pw-baru"
            type="password"
            value={baru}
            onChange={(e) => setBaru(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-ulang">Ketik ulang password baru</Label>
          <Input
            id="pw-ulang"
            type="password"
            value={ulang}
            onChange={(e) => setUlang(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div>
          <Button onClick={submit} disabled={submitting || !lama || !baru}>
            {submitting ? "Menyimpan..." : "Ganti Password"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function PengaturanContent() {
  const { user } = useAuth();
  const router = useRouter();
  const isOwner = user?.role === "owner";

  const [users, setUsers] = React.useState<UserOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [buatOpen, setBuatOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<UserOut | null>(null);
  const [passwordBaru, setPasswordBaru] = React.useState<
    { nama: string; email: string; password: string } | null
  >(null);

  const load = React.useCallback(() => {
    if (!isOwner) {
      setLoading(false);
      return;
    }
    setLoading(true);
    listUsers()
      .then(setUsers)
      .catch((err) => {
        if (isUnauthorized(err)) router.replace("/login");
        else toast.error(err instanceof ApiError ? err.message : "Gagal memuat daftar akun.");
      })
      .finally(() => setLoading(false));
  }, [isOwner, router]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function toggleAktif(u: UserOut) {
    try {
      await updateUser(u.id, { aktif: !u.aktif });
      toast.success(u.aktif ? `Akun ${u.nama} dinonaktifkan.` : `Akun ${u.nama} diaktifkan.`);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengubah status akun.");
    }
  }

  async function reset(u: UserOut) {
    try {
      const res = await resetUserPassword(u.id);
      setPasswordBaru({
        nama: res.user.nama,
        email: res.user.email,
        password: res.password_sementara,
      });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mereset password.");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Pengaturan</h1>
        <p className="text-sm text-muted-foreground">
          {isOwner
            ? "Kelola akun pengguna dan password Anda sendiri."
            : "Kelola password akun Anda sendiri."}
        </p>
      </div>

      {isOwner ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <UserCog className="h-4 w-4" /> Akun Pengguna
              </CardTitle>
              <CardDescription>
                Akun tidak pernah dihapus — cukup dinonaktifkan, supaya jejak audit &quot;siapa
                mengubah apa&quot; tetap utuh.
              </CardDescription>
            </div>
            <Button onClick={() => setBuatOpen(true)} className="gap-2">
              <Plus className="h-4 w-4" /> Buat Akun
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nama</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Peran</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Login Terakhir</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      Memuat...
                    </TableCell>
                  </TableRow>
                ) : users.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      Belum ada akun lain.
                    </TableCell>
                  </TableRow>
                ) : (
                  users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">
                        {u.nama}
                        {u.id === user?.id ? (
                          <span className="ml-2 text-xs text-muted-foreground">(Anda)</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{u.email}</TableCell>
                      <TableCell>
                        {u.role === "owner" ? (
                          <Badge variant="default" className="gap-1">
                            <ShieldCheck className="h-3 w-3" /> Owner
                          </Badge>
                        ) : u.role === "viewer" ? (
                          <Badge variant="outline">Pengamat</Badge>
                        ) : (
                          <Badge variant="secondary">Staf</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {u.aktif ? (
                          <Badge variant="success">Aktif</Badge>
                        ) : (
                          <Badge variant="outline">Nonaktif</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {u.last_login_at ? formatDate(u.last_login_at) : "belum pernah"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button variant="outline" size="sm" onClick={() => setEditTarget(u)}>
                            Ubah
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => reset(u)}>
                            Reset Password
                          </Button>
                          <Button
                            variant={u.aktif ? "outline" : "default"}
                            size="sm"
                            disabled={u.id === user?.id}
                            title={
                              u.id === user?.id
                                ? "Tidak bisa menonaktifkan akun sendiri"
                                : undefined
                            }
                            onClick={() => toggleAktif(u)}
                          >
                            {u.aktif ? "Nonaktifkan" : "Aktifkan"}
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
      ) : null}

      <GantiPasswordCard />

      <BuatAkunDialog
        open={buatOpen}
        onOpenChange={setBuatOpen}
        onCreated={(hasil) => {
          setPasswordBaru(hasil);
          load();
        }}
      />
      <EditAkunDialog
        target={editTarget}
        onOpenChange={(v) => !v && setEditTarget(null)}
        onSaved={load}
      />
      <PasswordSekaliDialog data={passwordBaru} onClose={() => setPasswordBaru(null)} />
    </div>
  );
}

export default function PengaturanPage() {
  return (
    <RequireAuth>
      <AppShell>
        <PengaturanContent />
      </AppShell>
    </RequireAuth>
  );
}
