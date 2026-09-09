"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  ClipboardList,
  Receipt,
  FileCheck2,
  LogOut,
  ArrowLeftRight,
  Settings,
  User,
  Users,
  Send,
  Settings2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { PERAN_PABRIK, WORKSPACE_PABRIK, useBadanUsaha } from "@/lib/badan-usaha-context";
import { BERANDA, MODUL } from "@/lib/pabrik-menu";
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

function isGroup(e: NavEntry): e is NavGroup {
  return "items" in e;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { list, selected, chosen, hydrated, resetWorkspace } = useBadanUsaha();
  const selectedBu = list.find((bu) => bu.kode === selected);
  const isOwner = user?.role === "owner";
  // Peran "viewer" (Pengamat, 4 Sep 2026): pengamat murni. Dua halaman di bawah
  // ini SELURUHNYA berisi aksi tulis (unggah BAP, terbitkan invoice, kirim
  // dokumen), jadi tidak ada gunanya ditampilkan -- server menolak semuanya.
  const isViewer = user?.role === "viewer";
  // PABRIK_B1_9SEP2026: workspace Pabrik (DESIGN-PABRIK K1-K3). admin/kepala dikunci di /pabrik/*.
  const isPabrikRole = PERAN_PABRIK.includes(user?.role ?? "");
  const isPabrikWs = selected === WORKSPACE_PABRIK || (pathname?.startsWith("/pabrik") ?? false);
  const wsLabel = isPabrikWs ? "PABRIK" : selectedBu?.kode;

  const isActive = (href: string) => {
    if (pathname === href || pathname?.startsWith(href + "/")) return true;
    const m = href.match(/^\/pabrik\/modul\/(\w+)$/);
    if (m) return !!MODUL.find((x) => x.slug === m[1])?.fungsi.some((f) => pathname === f.href.split("?")[0]);
    return false;
  };

  const doLogout = React.useCallback(() => {
    resetWorkspace();
    logout();
  }, [resetWorkspace, logout]);

  // Menu bertahap (permintaan owner 30 Jul 2026):
  // - Awal (belum pilih workspace): Mitra, Dashboard, + Pengaturan (owner saja).
  // - Setelah pilih DKP/KKS: muncul Terbit Invoice + Laporan (Rekap Invoice, PO).
  const navItems: NavEntry[] = isPabrikWs
    ? [BERANDA, { section: "Modul", items: MODUL.map((m) => ({ href: `/pabrik/modul/${m.slug}`, label: m.label, icon: m.icon })) }]  // PABRIK_FE_B2B7_9SEP2026: pola Accurate
    : [
        { href: "/mitra", label: "Mitra", icon: Users },
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      ];
  if (isPabrikWs && isOwner) {
    navItems.push({ href: "/pabrik/parameter", label: "Parameter", icon: Settings2 });
  }
  // Highlight modul saat berada di halaman fungsi di dalamnya
  if (chosen && !isPabrikWs) {
    if (!isViewer) {
      navItems.push({ href: "/bap", label: "Terbit Invoice", icon: FileText });
      navItems.push({ href: "/invoice-gantung", label: "Invoice Gantung", icon: Send });
    }
    navItems.push({
      section: "Laporan",
      items: [
        { href: "/invoices", label: "Rekap Invoice", icon: Receipt },
        { href: "/po", label: "Purchase Order", icon: ClipboardList },
        { href: "/faktur-pajak", label: "Faktur Pajak", icon: FileCheck2 },
      ],
    });
  }
  if (isOwner) {
    navItems.push({ href: "/pengaturan", label: "Pengaturan", icon: Settings });
  }
  const flatItems: NavLink[] = navItems.flatMap((e) => (isGroup(e) ? e.items : [e]));

  // Belum pilih workspace -> arahkan ke layar pilih (satu-satunya tempat ganti workspace).
  React.useEffect(() => {
    if (!hydrated) return;
    if (!chosen) router.replace("/pilih");
  }, [hydrated, chosen, router]);

  // PABRIK_B1_9SEP2026: admin/kepala tidak boleh keluar dari /pabrik/* (server pun 403);
  // siapa pun yang memilih workspace Pabrik diarahkan dari /dashboard ke /pabrik.
  React.useEffect(() => {
    if (!hydrated || !pathname) return;
    if (isPabrikRole && !pathname.startsWith("/pabrik")) router.replace("/pabrik");
    else if (isPabrikWs && pathname === "/dashboard") router.replace("/pabrik");
  }, [hydrated, pathname, isPabrikRole, isPabrikWs, router]);

  if (hydrated && !chosen) {
    return (
      <div className="flex min-h-screen flex-1 items-center justify-center text-sm text-muted-foreground">
        Mengalihkan ke pilih workspace...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card px-3 py-4 md:flex">
        <div className="mb-6 px-2">
          <p className="text-sm font-semibold leading-tight">{isPabrikWs ? "Pabrik Cocopeat" : "Invoice System"}</p>
          <p className="text-xs text-muted-foreground">{isPabrikWs ? "Hulu · Produksi" : "PO · BAP · Invoice"}</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {navItems.map((entry) => {
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

          <div className="hidden items-center gap-2 md:flex">
            {chosen && wsLabel ? (
              <>
                <span className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                  Workspace: {wsLabel}
                </span>
                {isPabrikRole ? null : (
                <Link
                  href="/pilih"
                  className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                >
                  Ganti Workspace
                </Link>
                )}
              </>
            ) : null}
          </div>

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
                  <p className="text-xs font-normal text-muted-foreground">
                    {isViewer ? "Pengamat — hanya melihat" : user?.role === "kepala" ? "Kepala pabrik" : user?.role === "admin" ? "Admin pabrik" : <span className="capitalize">{user?.role}</span>}
                  </p>
                  {chosen && wsLabel ? (
                    <p className="mt-1 text-xs font-medium text-primary">Workspace: {wsLabel}</p>
                  ) : null}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {chosen && !isPabrikRole ? (
                  <DropdownMenuItem onClick={() => router.push("/pilih")} className="gap-2">
                    <ArrowLeftRight className="h-4 w-4" />
                    Pindah Workspace
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem onClick={doLogout} className="gap-2 text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4" />
                  Keluar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <nav className="flex items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 py-1 md:hidden">
          {flatItems.map((item) => {
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
