/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Route Resilience design system
        surface:  { DEFAULT: "#0B0F1A", 100: "#111827", 200: "#1C2333" },
        accent:   { DEFAULT: "#00E5B4", dim: "#00B38A" },
        danger:   { DEFAULT: "#FF4444", dim: "#CC2222" },
        warning:  { DEFAULT: "#FFB400", dim: "#CC8F00" },
        safe:     { DEFAULT: "#22C55E", dim: "#16A34A" },
        muted:    { DEFAULT: "#6B7280" },
        border:   { DEFAULT: "rgba(255,255,255,0.08)" },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body:    ["'Inter'", "sans-serif"],
        mono:    ["'JetBrains Mono'", "monospace"],
      },
      backgroundImage: {
        "grid-pattern": "linear-gradient(rgba(0,229,180,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,180,0.03) 1px, transparent 1px)",
      },
      backgroundSize: {
        "grid-pattern": "32px 32px",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan": "scan 2.5s linear infinite",
        "fade-in": "fadeIn 0.4s ease-out",
      },
      keyframes: {
        scan: {
          "0%":   { transform: "translateY(0%)" },
          "100%": { transform: "translateY(100%)" },
        },
        fadeIn: {
          "0%":   { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
