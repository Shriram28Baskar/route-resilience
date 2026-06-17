import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "danger" | "warning" | "success" | "muted";
  className?: string;
}

const VARIANTS = {
  default: "bg-[#00E5B4]/10 text-[#00E5B4] border-[#00E5B4]/20",
  danger:  "bg-[#FF4444]/10 text-[#FF4444] border-[#FF4444]/20",
  warning: "bg-[#FFB400]/10 text-[#FFB400] border-[#FFB400]/20",
  success: "bg-[#22C55E]/10 text-[#22C55E] border-[#22C55E]/20",
  muted:   "bg-white/5 text-[#6B7280] border-white/8",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border",
      VARIANTS[variant],
      className,
    )}>
      {children}
    </span>
  );
}
