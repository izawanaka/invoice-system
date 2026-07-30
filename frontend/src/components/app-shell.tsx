"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  ClipboardList,
  Receipt,
  LogOut,
  Settings,
  User,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { useBadanUsaha } from "@/lib/badan-usaha-context";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type NavLink = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };
type NavGroup = { section: string; items: NavLink[] };
type NavEntry = NavLink | NavGroup;

// Susunan menu (permintaan owner 30 Jul 2026):
// - Mitra paling atas (dipakai utk tracking PO aktif + invoice di dalamnya).
// - "BAP" diganti nama jadi "Terbit Invoice".
// - "Invoice" diganti nama jadi "Rekap Invoice".
// - "Rekap Invoice" + "Purchase Order" dikelompokkan dalam bagian "Laporan".
const NAV_ITEMS: NavEntry[] = [
  { href: "/mitra", label: "Mitra", icon: Users },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/bap", label: "Terbit Invoice", icon: FileText },
  {
    section: "Laporan",
    items: [
      { href: "/invoices", label: "Rekap Invoice", icon: Receipt },
      { href: "/po", label: "Purchase Order", icon: ClipboardList },
    ],
  },
  // Terlihat utk semua peran: staf memakainya utk mengganti password sendiri,
  // owner memakainya utk mengelola akun (daftar akun hanya dimuat kalau owner).
  { href: "/pengaturan", label: "Pengaturan", icon: Settings },
];

const FLAT_ITEMS: NavLink[] = NAV_ITEMS.flatMap((e) => ("items" in e ? e.items : [e]));

function isGroup(e: NavEntry): e is NavGroup {
  return "items" in e;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { list, selected, setSelected } = useBadanUsaha();
  const selectedBu = list.find((bu) => bu.kode === selected);

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + "/");

  // Tab DKP/KKS global disembunyikan di halaman Laporan (Rekap Invoice & PO):
  // halaman itu punya filter Semua/DKP/KKS sendiri & default menampilkan SEMUA.
  const hideBuTab =
    isActive("/invoices") || isActive("/po");

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card px-3 py-4 md:flex">
        <div className="mb-6 px-2">
          <p className="text-sm font-semibold leading-tight">Invoice System</p>
          <p className="text-xs text-muted-foreground">PO · BAP · Invoice</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map((entry) => {
            if (isGroup(entry)) {
              return (
                <div key={entry.section} className="mt-3 flex flex-col gap-1">
                  <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {entry.section}
                  </p>
                  {entry.items.map((item) => {
                    const active = isActive(item.href);
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                          active
                            ? "bg-accent text-accent-foreground"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                        )}
                      >
                        <Icon className="h-4 w-4" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              );
            }
            const active = isActive(entry.href);
            const Icon = entry.icon;
            return (
              <Link
                key={entry.href}
                href={entry.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {entry.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-border bg-card px-4">
          <div className="flex items-center gap-2 md:hidden">
            <p className="text-sm font-semibold">Invoice System</p>
          </div>

          <p className="hidden truncate text-sm text-muted-foreground md:block">
            {!hideBuTab && selectedBu ? `${selectedBu.kode} — ${selectedBu.nama}` : ""}
          </p>

          <div className="flex items-center gap-3">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2">
                  <User className="h-4 w-4" />
                  <span className="hidden sm:inline">{user?.nama}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>
                  <p className="text-sm font-medium">{user?.nama}</p>
                  <p className="text-xs font-normal text-muted-foreground">{user?.email}</p>
                  <p className="text-xs font-normal text-muted-foreground capitalize">{user?.role}</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="gap-2 text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4" />
                  Keluar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Tab pemisah badan usaha (DKP/KKS). Disembunyikan di halaman Laporan yang
            punya filter Semua/DKP/KKS sendiri. */}
        {!hideBuTab ? (
          <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-card px-4 py-2">
            {list.map((bu) => (
              <button
                key={bu.kode}
                type="button"
                onClick={() => setSelected(bu.kode)}
                className={cn(
                  "whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  selected === bu.kode
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
                title={bu.nama}
              >
                {bu.kode}
              </button>
            ))}
          </div>
        ) : null}

        <nav className="flex items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 py-1 md:hidden">
          {FLAT_ITEMS.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium",
                  active ? "bg-accent text-accent-foreground" : "text-muted-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main className="flex-1 bg-background p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
