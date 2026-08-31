"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { ApiError, clearToken, getToken, login as apiLogin, me as apiMe, setToken } from "./api";
import type { MeResponse } from "./types";

interface AuthState {
  user: MeResponse | null;
  loading: boolean; // true selama pengecekan token awal berlangsung
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<MeResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const router = useRouter();

  React.useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    apiMe()
      .then((u) => setUser(u))
      .catch((err) => {
        // Hanya hapus token kalau server BENAR-BENAR menolak (401 = sesi habis).
        // Untuk error sementara (API sedang restart / jaringan / 5xx) JANGAN hapus
        // token -- kalau tidak, gangguan sesaat memaksa login ulang padahal token
        // masih sah. Reload setelah API pulih akan memulihkan sesi otomatis.
        if (isUnauthorized(err)) {
          clearToken();
          setUser(null);
          if (typeof window !== "undefined") window.sessionStorage.removeItem("invoice_app_bu_chosen");
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const login = React.useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = React.useCallback(() => {
    clearToken();
    setUser(null);
    if (typeof window !== "undefined") window.sessionStorage.removeItem("invoice_app_bu_chosen");
    router.push("/login");
  }, [router]);

  const value = React.useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus dipakai di dalam <AuthProvider>");
  return ctx;
}

// Helper: apakah error dari api client adalah 401 (dipakai komponen fetch data
// per-halaman untuk redirect ke /login kalau sesi kadaluarsa di tengah jalan).
export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
