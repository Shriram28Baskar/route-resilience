import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: LucideIcon;
  color?: "accent" | "danger" | "warning" | "success" | "muted";
  className?: string;
}

const COLORS = {
  accent:  "text-[#00E5B4]",
  danger:  "text-[#FF4444]",
  warning: "text-[#FFB400]",
  success: "text-[#22C55E]",
  muted:   "text-[#6B7280]",
};

export function MetricCard({ label, value, sub, icon: Icon, color = "accent", className }: MetricCardProps) {
  return (
    <div className={cn("bg-[#111827] border border-white/8 rounded-xl p-5", className)}>
      {Icon && (
        <div className={cn("w-7 h-7 rounded-md flex items-center justify-center mb-3",
          color === "accent" ? "bg-[#00E5B4]/10" :
          color === "danger" ? "bg-[#FF4444]/10" :
          color === "warning" ? "bg-[#FFB400]/10" :
          color === "success" ? "bg-[#22C55E]/10" : "bg-white/5"
        )}>
          <Icon className={cn("w-4 h-4", COLORS[color])} />
        </div>
      )}
      <div className="text-xs text-[#6B7280] mb-1 font-mono uppercase tracking-widest">{label}</div>
      <div className={cn("font-display text-2xl font-bold", COLORS[color])}>{value}</div>
      {sub && <div className="text-xs text-[#6B7280] mt-1">{sub}</div>}
    </div>
  );
}
