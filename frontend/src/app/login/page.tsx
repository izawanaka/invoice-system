"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth-context";
import { ApiError, loginStart, loginVerify, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Langkah = "kredensial" | "otp";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [langkah, setLangkah] = React.useState<Langkah>("kredensial");
  const [pakaiPassword, setPakaiPassword] = React.useState(false);

  const [email, setEmail] = React.useState("");
  const [pin, setPin] = React.useState("");
  const [kode, setKode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [info, setInfo] = React.useState("");

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

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await loginStart(email, pin);
      setLangkah("otp");
      if (res.otp_terkirim) {
        setInfo(`Kode OTP dikirim ke ${res.email}. Berlaku ${res.ttl_menit} menit.`);
        toast.success("Kode OTP dikirim ke email Anda.");
      } else {
        setInfo(res.pesan || "OTP belum dapat dikirim. Hubungi admin.");
        toast.message(res.pesan || "OTP belum terkirim.");
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Gagal memproses. Periksa koneksi Anda.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await loginVerify(email, kode);
      setToken(res.access_token);
      window.location.assign("/pilih");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Verifikasi gagal. Coba lagi.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(email, password);
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
          {pakaiPassword ? (
            <form onSubmit={handlePassword} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">Kata sandi</Label>
                <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <Button type="submit" disabled={submitting} className="mt-2">
                {submitting ? "Memproses..." : "Masuk"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setPakaiPassword(false)}>
                Kembali ke login Email + PIN
              </Button>
            </form>
          ) : langkah === "kredensial" ? (
            <form onSubmit={handleStart} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pin">PIN</Label>
                <Input id="pin" type="password" inputMode="numeric" autoComplete="off" required value={pin} onChange={(e) => setPin(e.target.value)} />
              </div>
              <Button type="submit" disabled={submitting} className="mt-2">
                {submitting ? "Memproses..." : "Kirim Kode OTP"}
              </Button>
              <Button type="button" variant="outline" onClick={() => window.location.assign("/api/auth/google/mulai")}>
                Masuk dengan Google
              </Button>
              <Button type="button" variant="ghost" onClick={() => setPakaiPassword(true)}>
                Gunakan kata sandi
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerify} className="flex flex-col gap-4">
              {info ? <p className="text-sm text-muted-foreground">{info}</p> : null}
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="kode">Kode OTP</Label>
                <Input id="kode" inputMode="numeric" autoComplete="one-time-code" required value={kode} onChange={(e) => setKode(e.target.value)} />
              </div>
              <Button type="submit" disabled={submitting} className="mt-2">
                {submitting ? "Memverifikasi..." : "Verifikasi & Masuk"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => { setLangkah("kredensial"); setKode(""); setInfo(""); }}>
                Kembali
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
