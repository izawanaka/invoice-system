import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Pemetaan status generik dipakai lintas halaman (PO/BAP/Invoice) supaya
// warna konsisten. Status string apa adanya dari backend (tidak diterjemahkan
// nilainya, hanya warnanya).
const STATUS_MAP: Record<string, { variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning"; label?: string }> = {
  aktif: { variant: "success" },
  active: { variant: "success" },
  closed: { variant: "secondary" },
  selesai: { variant: "secondary" },
  generated: { variant: "warning", label: "Generated (belum bayar)" },
  sebagian: { variant: "warning", label: "Cicilan (sebagian)" },
  paid: { variant: "success", label: "Lunas" },
  pending: { variant: "outline" },
  error: { variant: "destructive" },
  success: { variant: "success" },
};

export function StatusBadge({ status, className }: { status: string | null | undefined; className?: string }) {
  if (!status) return <Badge variant="outline" className={className}>-</Badge>;
  const cfg = STATUS_MAP[status.toLowerCase()] ?? { variant: "outline" as const };
  return (
    <Badge variant={cfg.variant} className={cn("capitalize", className)}>
      {cfg.label ?? status}
    </Badge>
  );
}

export function WarningBadge({ isWarning }: { isWarning: boolean }) {
  if (!isWarning) return null;
  return <Badge variant="warning">Sisa PO menipis</Badge>;
}
