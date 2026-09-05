"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth-context";
import { ApiError, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

// 5 Sep 2026 -- SALINAN MODEL CANTABILE (keputusan owner):
// Ketik USERNAME saja, lalu tekan "Masuk dengan Google". Username hanya dikirim
// sebagai login_hint (saran akun di halaman Google); identitas sesungguhnya
// ditentukan Google lewat email. Password tidak pernah singgah di cocopeat.
//
// Kata sandi = JALUR DARURAT TERSEMBUNYI (di Cantabile perannya dipegang PIN).
// Akun dengan izin Google menyala akan ditolak backend kalau memakai password,
// kecuali peran Owner. Karena itu kolom sandi disembunyikan di balik tautan.

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [pakaiSandi, setPakaiSandi] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  // Backend mengembalikan JWT lewat FRAGMENT (#gtoken=...) -- fragment tidak
  // pernah dikirim ke server, jadi tidak masuk log akses/proxy.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash;
    if (hash.startsWith("#gtoken=")) {
      setToken(decodeURIComponent(hash.slice("#gtoken=".length)));
      window.history.replaceState(null, "", window.location.pathname);
      window.location.assign("/pilih");
      return;
    }
    const gerr = new URLSearchParams(window.location.search).get("google_error");
    if (gerr) {
      toast.error(gerr);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  function masukGoogle() {
    const u = username.trim();
    if (!u) {
      toast.error("Ketik username Anda dulu.");
      return;
    }
    window.location.assign(`/api/auth/google/mulai?username=${encodeURIComponent(u)}`);
  }

  async function handleSandi(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      router.replace("/pilih");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Gagal masuk. Periksa koneksi Anda.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Masuk</CardTitle>
          <CardDescription>Dashboard manajemen PO, BAP, dan Invoice.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSandi} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !pakaiSandi) {
                    e.preventDefault();
                    masukGoogle();
                  }
                }}
              />
            </div>

            {pakaiSandi ? (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="password">Kata sandi</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Memproses..." : "Masuk"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setPakaiSandi(false);
                    setPassword("");
                  }}
                >
                  Kembali
                </Button>
              </>
            ) : (
              <>
                <Button type="button" onClick={masukGoogle}>
                  Masuk dengan Google
                </Button>
                <Button type="button" variant="ghost" onClick={() => setPakaiSandi(true)}>
                  Gunakan kata sandi
                </Button>
                <p className="text-xs text-muted-foreground">
                  Kata sandi hanya untuk akun Owner. Akun lain masuk lewat Google — kalau
                  bermasalah, hubungi Owner.
                </p>
              </>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
