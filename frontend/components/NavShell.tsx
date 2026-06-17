"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Network, Map, Zap, Eye, MessageSquare, Home, BarChart, FileText } from "lucide-react";

const NAV = [
  { href: "/",         label: "Overview",  icon: Home },
  { href: "/map",      label: "Map",       icon: Map },
  { href: "/simulate", label: "Simulate",  icon: Zap },
  { href: "/explain",  label: "Explain",   icon: Eye },
  { href: "/copilot",  label: "Copilot",   icon: MessageSquare },
  { href: "/analytics",label: "Analytics", icon: BarChart },
  { href: "/reports",  label: "Reports",   icon: FileText },
];

export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex h-screen bg-[#0B0F1A]">
      {/* Sidebar */}
      <aside className="w-14 flex flex-col items-center py-4 gap-2 border-r border-white/8 bg-[#111827] shrink-0">
        <div className="w-8 h-8 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center mb-3">
          <Network className="w-4 h-4 text-[#00E5B4]" />
        </div>
        {NAV.map(item => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}
              title={item.label}
              className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${
                active ? "bg-[#00E5B4]/15 text-[#00E5B4]" : "text-[#6B7280] hover:text-white hover:bg-white/5"
              }`}>
              <item.icon className="w-4 h-4" />
            </Link>
          );
        })}
      </aside>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
