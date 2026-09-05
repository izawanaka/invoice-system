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

// 5 Sep 2026 (keputusan owner): login PIN + OTP email DIMATIKAN. Yang diketik
// hanya USERNAME (di belakang layar tetap email, gaya Cantabile). Jalur kedua:
// "Masuk dengan Google" -- identitas Google tetap dari email akun, tidak perlu
// username. Untuk staff & viewer, begitu Google pernah sukses, password tidak
// berlaku lagi (ditolak backend dengan pesan yang jelas).

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  // Login Google (4 Sep 2026, meniru Cantabile): backend mengembalikan JWT lewat
  // FRAGMENT (#gtoken=...) -- fragment tidak pernah dikirim ke server, jadi tidak
  // masuk log akses/proxy. Pesan gagal datang lewat ?google_error=.
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

  async function handlePassword(e: React.FormEvent) {
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
          <form onSubmit={handlePassword} className="flex flex-col gap-4">
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
              />
            </div>
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
            <Button type="submit" disabled={submitting} className="mt-2">
              {submitting ? "Memproses..." : "Masuk"}
            </Button>
            <div className="relative my-1 text-center text-xs text-muted-foreground">
              <span className="bg-card px-2">atau</span>
              <div className="absolute inset-x-0 top-1/2 -z-10 border-t border-border" />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => window.location.assign("/api/auth/google/mulai")}
            >
              Masuk dengan Google
            </Button>
            <p className="text-xs text-muted-foreground">
              Username diatur oleh Owner di menu Pengaturan. Lupa kata sandi? Minta Owner mereset.
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
