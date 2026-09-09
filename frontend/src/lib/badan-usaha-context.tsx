"use client";

import * as React from "react";

import { listBadanUsaha, getToken } from "./api";
import { useAuth } from "./auth-context";
import type { BadanUsahaOut } from "./types";

const STORAGE_KEY = "invoice_app_bu_filter";
const CHOSEN_KEY = "invoice_app_bu_chosen";
const DEFAULT_KODE = "DKP";

const DASHBOARD_BU = ["DKP", "KKS"];
// PABRIK_B1_9SEP2026: workspace ketiga "PABRIK" (bukan badan usaha; tidak ada di tabel
// badan_usaha). Boleh dipilih owner/viewer; admin & kepala OTOMATIS masuk ke sini.
export const WORKSPACE_PABRIK = "PABRIK";
const WORKSPACE_VALID = [...DASHBOARD_BU, WORKSPACE_PABRIK];
export const PERAN_PABRIK = ["admin", "kepala"];

interface BadanUsahaState {
  list: BadanUsahaOut[];
  loading: boolean;
  selected: string;
  chosen: boolean;
  hydrated: boolean;
  setSelected: (kode: string) => void;
  resetWorkspace: () => void;
  refresh: () => void;
}

const BadanUsahaContext = React.createContext<BadanUsahaState | null>(null);

export function BadanUsahaProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = React.useState<BadanUsahaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelectedState] = React.useState<string>(DEFAULT_KODE);
  const [chosen, setChosen] = React.useState(false);
  const [hydrated, setHydrated] = React.useState(false);
  const { user, loading: authLoading } = useAuth();

  const load = React.useCallback(() => {
    // Tanpa token (mis. masih di halaman /login) endpoint /badan-usaha PASTI 401.
    // Jangan dipanggil; effect di bawah akan memuat ulang begitu sesi siap.
    if (!getToken()) {
      setList([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    listBadanUsaha()
      .then((all) => setList(all.filter((bu) => DASHBOARD_BU.includes(bu.kode))))
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved && WORKSPACE_VALID.includes(saved)) setSelectedState(saved);
      // "chosen" per-sesi: bertahan saat refresh (sessionStorage), hilang saat
      // tab ditutup atau Log out. Login berikutnya mulai dari kondisi awal.
      if (window.sessionStorage.getItem(CHOSEN_KEY) === "1") setChosen(true);
    }
    setHydrated(true);
  }, []);

  // BUGFIX 18 Agu 2026: dulu daftar badan usaha ditarik SEKALI saat provider
  // mount. Provider ini ada di root layout, jadi mount terjadi di halaman
  // /login KETIKA TOKEN BELUM ADA -> 401 -> list kosong; navigasi setelah
  // login bersifat client-side (provider tidak remount) sehingga list tetap
  // kosong sepanjang sesi. Akibatnya dropdown "Badan Usaha" di dialog Tambah
  // PO / Tambah PO dari Foto-Scan tidak bisa diisi sampai halaman di-reload
  // manual. Kini list dimuat ulang tiap status auth berubah (mis. login sukses).
  React.useEffect(() => {
    if (!authLoading) load();
  }, [authLoading, user, load]);

  const setSelected = React.useCallback((kode: string) => {
    setSelectedState(kode);
    setChosen(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, kode);
      window.sessionStorage.setItem(CHOSEN_KEY, "1");
    }
  }, []);

  // PABRIK_B1_9SEP2026: admin/kepala tidak punya pilihan workspace lain.
  React.useEffect(() => {
    if (!hydrated || !user) return;
    if (PERAN_PABRIK.includes(user.role) && (!chosen || selected !== WORKSPACE_PABRIK)) {
      setSelected(WORKSPACE_PABRIK);
    }
  }, [hydrated, user, chosen, selected, setSelected]);

  const resetWorkspace = React.useCallback(() => {
    setChosen(false);
    if (typeof window !== "undefined") window.sessionStorage.removeItem(CHOSEN_KEY);
  }, []);

  const value = React.useMemo(
    () => ({ list, loading, selected, chosen, hydrated, setSelected, resetWorkspace, refresh: load }),
    [list, loading, selected, chosen, hydrated, setSelected, resetWorkspace, load],
  );

  return <BadanUsahaContext.Provider value={value}>{children}</BadanUsahaContext.Provider>;
}

export function useBadanUsaha(): BadanUsahaState {
  const ctx = React.useContext(BadanUsahaContext);
  if (!ctx) throw new Error("useBadanUsaha harus dipakai di dalam <BadanUsahaProvider>");
  return ctx;
}
