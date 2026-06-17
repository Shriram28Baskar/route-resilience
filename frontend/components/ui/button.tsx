import { cn } from "@/lib/utils";
import { forwardRef } from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

const VARIANTS = {
  primary:   "bg-[#00E5B4] text-[#0B0F1A] hover:bg-[#00B38A] font-bold",
  secondary: "bg-white/5 text-white hover:bg-white/10 border border-white/8",
  danger:    "bg-[#FF4444]/10 text-[#FF4444] hover:bg-[#FF4444]/20 border border-[#FF4444]/20",
  ghost:     "text-[#6B7280] hover:text-white hover:bg-white/5",
};

const SIZES = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2.5 text-sm rounded-xl",
  lg: "px-6 py-3 text-base rounded-xl",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 font-display transition-colors",
        "disabled:opacity-40 disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading && (
        <span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />
      )}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
