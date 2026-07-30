"use client";

import * as React from "react";

import { listBadanUsaha } from "./api";
import type { BadanUsahaOut } from "./types";

const STORAGE_KEY = "invoice_app_bu_filter";
const DEFAULT_KODE = "DKP";

// Keputusan owner (28 Jul 2026): dashboard ini KHUSUS ranah DKP & KKS —
// GBU/TBS/SSM disembunyikan dari seluruh UI (backend tetap generik 5 entitas,
// pembatasan hanya di tampilan; lihat 03_progress_log.md §16).
const DASHBOARD_BU = ["DKP", "KKS"];

interface BadanUsahaState {
  list: BadanUsahaOut[];
  loading: boolean;
  selected: string; // kode badan usaha aktif -- SELALU satu entitas, tidak pernah campur
  setSelected: (kode: string) => void;
  refresh: () => void;
}

const BadanUsahaContext = React.createContext<BadanUsahaState | null>(null);

export function BadanUsahaProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = React.useState<BadanUsahaOut[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelectedState] = React.useState<string>(DEFAULT_KODE);

  const load = React.useCallback(() => {
    setLoading(true);
    listBadanUsaha()
      .then((all) => setList(all.filter((bu) => DASHBOARD_BU.includes(bu.kode))))
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    // Permintaan owner (28 Jul): data per badan usaha DIPISAH, tidak ada mode
    // "semua campur". Nilai lama "ALL" dari localStorage dikoreksi ke default.
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (saved && DASHBOARD_BU.includes(saved)) setSelectedState(saved);
    load();
  }, [load]);

  const setSelected = React.useCallback((kode: string) => {
    setSelectedState(kode);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, kode);
  }, []);

  const value = React.useMemo(
    () => ({ list, loading, selected, setSelected, refresh: load }),
    [list, loading, selected, setSelected, load],
  );

  return <BadanUsahaContext.Provider value={value}>{children}</BadanUsahaContext.Provider>;
}

export function useBadanUsaha(): BadanUsahaState {
  const ctx = React.useContext(BadanUsahaContext);
  if (!ctx) throw new Error("useBadanUsaha harus dipakai di dalam <BadanUsahaProvider>");
  return ctx;
}
