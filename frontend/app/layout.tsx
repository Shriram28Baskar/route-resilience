import type { Metadata } from "next";
import NavShell from "@/components/NavShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Route Resilience — Urban Road Network Analysis",
  description: "Occlusion-robust road extraction, graph criticality analysis, and disaster simulation for urban mobility.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        {/* Leaflet CSS */}
        <link
          rel="stylesheet"
          href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          crossOrigin=""
        />
      </head>
      <body className="bg-surface text-white font-body antialiased min-h-screen">
        <NavShell>{children}</NavShell>
      </body>
    </html>
  );
}
