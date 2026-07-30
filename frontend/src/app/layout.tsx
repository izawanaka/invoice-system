import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { BadanUsahaProvider } from "@/lib/badan-usaha-context";
import { Toaster } from "@/components/ui/sonner";

// Catatan: sengaja TIDAK memakai next/font/google (Geist) karena butuh akses
// jaringan ke fonts.googleapis.com saat build. Sandbox ini (dan kemungkinan
// VM produksi via proxy yang sama) memblokir domain tsb -- lihat catatan
// serupa soal shadcn CLI di 05_web_platform_plan.md. Pakai font-stack sistem
// saja supaya build selalu bisa jalan offline/di balik proxy terbatas.

export const metadata: Metadata = {
  title: "Invoice System",
  description: "Dashboard manajemen PO, BAP, dan Invoice",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-background text-foreground font-sans">
        <AuthProvider>
          <BadanUsahaProvider>
            {children}
            <Toaster />
          </BadanUsahaProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
