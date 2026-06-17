"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Network, Zap, Hospital, MessageSquare, Map, FileText, BarChart } from "lucide-react";
import Link from "next/link";
import { getGraphMetrics, type GraphMetrics } from "@/lib/api";
import { formatDistance } from "@/lib/utils";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<GraphMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGraphMetrics()
      .then(setMetrics)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#0B0F1A] bg-grid-pattern [background-size:32px_32px]">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="border-b border-white/8 bg-[#0B0F1A]/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-[#00E5B4]/10 flex items-center justify-center">
              <Network className="w-4 h-4 text-[#00E5B4]" />
            </div>
            <span className="font-display font-semibold text-sm tracking-wide">Route Resilience</span>
            <span className="text-xs text-[#6B7280] hidden sm:block">/ ISRO NNRMS PS4</span>
          </div>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-[#6B7280] hover:text-white hover:bg-white/5 transition-colors"
              >
                <item.icon className="w-3.5 h-3.5" />
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        {/* ── Hero ──────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#00E5B4]/10 border border-[#00E5B4]/20 text-[#00E5B4] text-xs font-mono mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00E5B4] animate-pulse" />
            Bengaluru AOI · Live Graph Active
          </div>
          <h1 className="font-display text-4xl md:text-5xl font-bold leading-tight mb-3">
            Urban Road Network<br />
            <span className="text-[#00E5B4]">Resilience Intelligence</span>
          </h1>
          <p className="text-[#6B7280] text-base max-w-2xl leading-relaxed">
            Occlusion-robust road extraction · MST topological healing · Betweenness criticality ·
            Disaster simulation · Emergency routing
          </p>
        </motion.div>

        {/* ── Metric Cards ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-28 rounded-xl bg-white/4 animate-pulse" />
            ))
          ) : error ? (
            <div className="col-span-4 text-[#FF4444] text-sm bg-[#FF4444]/10 rounded-xl p-4">
              Backend unreachable: {error}. Start the FastAPI server to see live data.
            </div>
          ) : metrics ? (
            METRIC_CARDS(metrics).map((card, i) => (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                className="bg-[#111827] border border-white/8 rounded-xl p-5"
              >
                <div className="text-[#6B7280] text-xs mb-2 font-mono uppercase tracking-widest">{card.label}</div>
                <div className="font-display text-2xl font-bold text-white">{card.value}</div>
                <div className="text-xs text-[#6B7280] mt-1">{card.sub}</div>
              </motion.div>
            ))
          ) : null}
        </div>

        {/* ── Feature Grid ───────────────────────────────────────── */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURE_CARDS.map((card, i) => (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + i * 0.06 }}
            >
              <Link href={card.href} className="group block h-full">
                <div className="h-full bg-[#111827] border border-white/8 rounded-xl p-6 hover:border-[#00E5B4]/30 hover:bg-[#1C2333] transition-all duration-200">
                  <div className="w-9 h-9 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center mb-4 group-hover:bg-[#00E5B4]/20 transition-colors">
                    <card.icon className="w-5 h-5 text-[#00E5B4]" />
                  </div>
                  <h2 className="font-display font-semibold text-base mb-2 text-white">{card.title}</h2>
                  <p className="text-[#6B7280] text-sm leading-relaxed">{card.description}</p>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </main>
    </div>
  );
}

// ── Static data ─────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { href: "/map",      label: "Map",       icon: Map },
  { href: "/simulate", label: "Simulate",  icon: Zap },
  { href: "/explain",  label: "Explain",   icon: Activity },
  { href: "/copilot",  label: "Copilot",   icon: MessageSquare },
  { href: "/analytics",label: "Analytics", icon: BarChart },
  { href: "/reports",  label: "Reports",   icon: FileText },
];

const FEATURE_CARDS = [
  {
    href: "/map",
    icon: Map,
    title: "Criticality Heatmap",
    description: "Road network colored by betweenness centrality. Identify gatekeeper nodes and systemic bottlenecks in real time.",
  },
  {
    href: "/simulate",
    icon: Zap,
    title: "Disaster Simulation",
    description: "Ablate flood-prone nodes, compute Resilience Index, run cascading failure analysis, and plan emergency routes.",
  },
  {
    href: "/explain",
    icon: Activity,
    title: "Segmentation & Explainability",
    description: "Upload satellite tiles, run inference, and inspect Grad-CAM saliency maps showing what drove road detection.",
  },
  {
    href: "/map",
    icon: Hospital,
    title: "Hospital Accessibility",
    description: "Visualise which areas lose emergency access after a road closure, with per-node nearest-hospital distances.",
  },
  {
    href: "/copilot",
    icon: MessageSquare,
    title: "Urban Planning Copilot",
    description: "Ask natural-language questions grounded in live graph metrics. Powered by Groq LLM with context injection.",
  },
  {
    href: "/map",
    icon: Network,
    title: "Graph Topology",
    description: "Inspect connected components, MST healing stats, and raw vs. healed graph overlays on an interactive map.",
  },
  {
    href: "/analytics",
    icon: BarChart,
    title: "Advanced Analytics",
    description: "Global Resilience Score, Population Impact Analysis, and Disaster Progression Timeline modeling.",
  },
  {
    href: "/reports",
    icon: FileText,
    title: "Automated Reports",
    description: "Generate and download comprehensive PDF situation reports summarizing network health and disaster impact.",
  },
];

function METRIC_CARDS(m: GraphMetrics) {
  return [
    { label: "Road Nodes",      value: m.num_nodes.toLocaleString(),                       sub: "intersection graph" },
    { label: "Road Edges",      value: m.num_edges.toLocaleString(),                       sub: "weighted segments" },
    { label: "Components",      value: m.num_components.toLocaleString(),                  sub: `LCC: ${(m.largest_component_fraction * 100).toFixed(0)}% of nodes` },
    { label: "Avg Path Length", value: m.avg_shortest_path_length?.toFixed(3) ?? "N/A",    sub: "graph distance units" },
  ];
}
