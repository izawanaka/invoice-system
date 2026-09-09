// pabrik-menu.ts -- registri modul & fungsi workspace PABRIK (PABRIK_FE_B2B7_9SEP2026).
// Pola tampilan mengikuti Accurate: sidebar modul -> grid kartu fungsi.
// warna: hijau = transaksi/input, biru = master, ungu = laporan/rekap.
import type { LucideIcon } from "lucide-react";
import {
  Truck, Layers, Package, ShoppingBag, ClipboardCheck, Warehouse, Wallet, HandCoins, Calculator,
  Send, Link2, AlertTriangle, MinusCircle, FileText, Coins, CalendarCheck, CloudSun, ShieldAlert,
  Users, Boxes, Factory, Settings2, BarChart3,
} from "lucide-react";

export type Warna = "hijau" | "biru" | "ungu";
export type Fungsi = { href: string; label: string; desc: string; icon: LucideIcon; warna: Warna; owner?: boolean };
export type Modul = { slug: string; label: string; icon: LucideIcon; desc: string; fungsi: Fungsi[] };

export const MODUL: Modul[] = [
  {
    slug: "bahan", label: "Bahan & Lot", icon: Layers, desc: "Sabut masuk, lot per petak, tahap pengolahan.",
    fungsi: [
      { href: "/pabrik/terima", label: "Terima Truk", desc: "Catat truk sabut masuk, p×l×t → kubik", icon: Truck, warna: "hijau" },
      { href: "/pabrik/lot", label: "Lot & Tahap", desc: "Buka lot, majukan tahap curah→habis", icon: Layers, warna: "hijau" },
      { href: "/pabrik/master", label: "Petak & Pemasok", desc: "Master petak lapangan dan pemasok", icon: Boxes, warna: "biru" },
      { href: "/pabrik/lot?tab=ringkas", label: "Ringkasan Lot", desc: "Kubik masuk, sak jadi, rendemen berjalan", icon: BarChart3, warna: "ungu" },
    ],
  },
  {
    slug: "produksi", label: "Produksi & Stok", icon: Package, desc: "Produksi sak, sak kosong, stok jadi, opname.",
    fungsi: [
      { href: "/pabrik/produksi", label: "Produksi Sak", desc: "Sak jadi per lot + 5 sampel berat (QC)", icon: Package, warna: "hijau" },
      { href: "/pabrik/sak", label: "Sak Kosong", desc: "Beli, rusak, retur sak bekas", icon: ShoppingBag, warna: "hijau" },
      { href: "/pabrik/opname", label: "Stock Opname", desc: "Hitung fisik vs sistem (owner)", icon: ClipboardCheck, warna: "hijau", owner: true },
      { href: "/pabrik/stok", label: "Saldo & Mutasi Stok", desc: "Saldo sak kosong dan stok jadi", icon: Warehouse, warna: "ungu" },
    ],
  },
  {
    slug: "kas", label: "Kas & Upah", icon: Wallet, desc: "Kas kecil, upah harian, HPP.",
    fungsi: [
      { href: "/pabrik/kas", label: "Kas Kecil", desc: "Kas keluar + isi ulang (owner)", icon: Wallet, warna: "hijau" },
      { href: "/pabrik/upah", label: "Upah Harian", desc: "Buruh, langsir, supir — otomatis kas keluar", icon: HandCoins, warna: "hijau" },
      { href: "/pabrik/hpp", label: "HPP Bulanan", desc: "Biaya ÷ sak lolos QC (owner)", icon: Calculator, warna: "ungu", owner: true },
    ],
  },
  {
    slug: "kirim", label: "Pengiriman & Bonus", icon: Send, desc: "Surat jalan, BAP versi pabrik, klaim, bonus kepala.",
    fungsi: [
      { href: "/pabrik/kirim", label: "Surat Jalan", desc: "Kirim sak, tujuan kode T1/T2", icon: Send, warna: "hijau" },
      { href: "/pabrik/kirim?tab=taut", label: "Tautkan BAP", desc: "Owner menautkan SJ ke BAP", icon: Link2, warna: "hijau", owner: true },
      { href: "/pabrik/klaim", label: "Klaim & Potongan", desc: "Klaim mutu/angkut → potongan bonus (owner)", icon: AlertTriangle, warna: "hijau", owner: true },
      { href: "/pabrik/bap-pabrik", label: "BAP Versi Pabrik", desc: "BAP tertaut: no, tanggal, volume, klaim", icon: FileText, warna: "ungu" },
      { href: "/pabrik/bonus", label: "Rekap Bonus", desc: "Sak netto, jenjang, pengali klaim, triwulan", icon: Coins, warna: "ungu" },
    ],
  },
  {
    slug: "harian", label: "Harian & Audit", icon: CalendarCheck, desc: "Tutup hari, cuaca, temuan audit otomatis.",
    fungsi: [
      { href: "/pabrik/tutup-hari", label: "Tutup Hari", desc: "Penanda disiplin: ringkasan input hari ini", icon: CalendarCheck, warna: "hijau" },
      { href: "/pabrik/cuaca", label: "Cuaca", desc: "Otomatis Open-Meteo + catatan manual", icon: CloudSun, warna: "hijau" },
      { href: "/pabrik/audit", label: "Temuan Audit", desc: "A1–A10: rendemen, opname, nota, SJ, rekap", icon: ShieldAlert, warna: "ungu" },
      { href: "/pabrik/karyawan", label: "Karyawan", desc: "Kepala & gaji effective-dated (owner)", icon: Users, warna: "biru", owner: true },
      { href: "/pabrik/parameter", label: "Parameter", desc: "kg/sak, rendemen, tarif, upah (owner)", icon: Settings2, warna: "biru", owner: true },
    ],
  },
];

export const BERANDA = { href: "/pabrik", label: "Beranda", icon: Factory };
export const MINUS = MinusCircle;
