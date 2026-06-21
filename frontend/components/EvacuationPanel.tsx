"use client";

import { useState } from "react";

interface EvacuationAssignment {
  zone: string;
  population: number;
  served_population?: number;
  priority: string;
  shelter: string | null;
  reachable: boolean;
  distance_m: number | null;
  eta_minutes: number | null;
  within_time_horizon?: boolean;
  note?: string;
}

interface EvacuationSummary {
  total_zones: number;
  total_shelters: number;
  total_population: number;
  total_evacuated: number;
  total_unserved: number;
  coverage_pct: number;
  isolated_zones: number;
  max_eta_minutes: number | null;
  time_horizon_hours: number;
}

interface EvacuationResult {
  assignments: EvacuationAssignment[];
  summary: EvacuationSummary;
  bottleneck_edges: Array<{ edge: [string, string]; route_count: number; criticality: string }>;
  shelter_utilization: Array<{ name: string; capacity: number; allocated: number; utilization_pct: number }>;
}

interface EvacuationPanelProps {
  result: EvacuationResult | null;
  loading: boolean;
  onRun: (ablatedNodes: string[]) => void;
  ablatedNodes: string[];
}

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "#FF4444",
  HIGH: "#FF8C00",
  MEDIUM: "#FFB400",
  LOW: "#9CA3AF",
};

export default function EvacuationPanel({ result, loading, onRun, ablatedNodes }: EvacuationPanelProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white">Evacuation Planner</h3>
          <p className="text-xs text-gray-400 mt-0.5">NDMA/Sendai Framework — multi-zone routing</p>
        </div>
        <button
          id="run-evacuation-btn"
          onClick={() => onRun(ablatedNodes)}
          disabled={loading}
          className="px-3 py-1.5 rounded text-xs font-bold transition-all duration-200 disabled:opacity-50"
          style={{ background: loading ? "#374151" : "linear-gradient(135deg, #00E5B4, #00B4D8)", color: "#0B0F1A" }}
        >
          {loading ? "Planning..." : "▶ Run Evacuation"}
        </button>
      </div>

      {result && (
        <>
          {/* Summary tiles */}
          <div className="grid grid-cols-2 gap-2">
            {[
              {
                label: "Coverage",
                value: `${result.summary.coverage_pct}%`,
                color: result.summary.coverage_pct >= 80 ? "#00E5B4" : result.summary.coverage_pct >= 50 ? "#FFB400" : "#FF4444",
              },
              { label: "Evacuated", value: result.summary.total_evacuated.toLocaleString(), color: "#00E5B4" },
              {
                label: "Unserved",
                value: result.summary.total_unserved.toLocaleString(),
                color: result.summary.total_unserved > 0 ? "#FF4444" : "#9CA3AF",
              },
              {
                label: "Max ETA",
                value: result.summary.max_eta_minutes ? `${result.summary.max_eta_minutes} min` : "N/A",
                color: "#FFB400",
              },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                className="rounded-lg p-2 text-center"
                style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}
              >
                <div className="text-lg font-bold" style={{ color }}>{value}</div>
                <div className="text-xs text-gray-400">{label}</div>
              </div>
            ))}
          </div>

          {/* Coverage bar */}
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Population Coverage</span>
              <span>
                {result.summary.total_evacuated.toLocaleString()} / {result.summary.total_population.toLocaleString()}
              </span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.1)" }}>
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${result.summary.coverage_pct}%`,
                  background:
                    result.summary.coverage_pct >= 80
                      ? "linear-gradient(90deg,#00E5B4,#00B4D8)"
                      : result.summary.coverage_pct >= 50
                      ? "linear-gradient(90deg,#FFB400,#FF8C00)"
                      : "linear-gradient(90deg,#FF4444,#FF8C00)",
                }}
              />
            </div>
          </div>

          {/* Zone assignments */}
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Zone Assignments</div>
            {result.assignments.map((a, i) => (
              <div
                key={i}
                className="rounded-lg p-2 cursor-pointer transition-all duration-200"
                style={{
                  background: expanded === i ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${a.reachable ? "rgba(255,255,255,0.08)" : "rgba(255,68,68,0.3)"}`,
                }}
                onClick={() => setExpanded(expanded === i ? null : i)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ background: PRIORITY_COLORS[a.priority] || "#9CA3AF" }}
                    />
                    <span className="text-xs font-medium text-white">{a.zone}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {!a.reachable ? (
                      <span
                        className="text-xs px-1.5 py-0.5 rounded"
                        style={{ background: "rgba(255,68,68,0.2)", color: "#FF4444" }}
                      >
                        ISOLATED
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">{a.eta_minutes} min</span>
                    )}
                    <svg
                      className="w-3 h-3 text-gray-500"
                      style={{
                        transform: expanded === i ? "rotate(180deg)" : "none",
                        transition: "transform 0.2s",
                      }}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>

                {expanded === i && (
                  <div className="mt-2 pt-2 border-t border-white/10 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="text-gray-400">Population</div>
                    <div className="text-white">{a.population.toLocaleString()}</div>
                    <div className="text-gray-400">Shelter</div>
                    <div className="text-white truncate">{a.shelter || "None available"}</div>
                    <div className="text-gray-400">Distance</div>
                    <div className="text-white">
                      {a.distance_m ? `${(a.distance_m / 1000).toFixed(1)} km` : "N/A"}
                    </div>
                    <div className="text-gray-400">ETA</div>
                    <div className="text-white">{a.eta_minutes ? `${a.eta_minutes} min` : "N/A"}</div>
                    {a.note && <div className="col-span-2 text-[#FF4444] mt-1">{a.note}</div>}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Bottlenecks */}
          {result.bottleneck_edges.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
                Evacuation Bottlenecks
              </div>
              {result.bottleneck_edges.slice(0, 5).map((b, i) => (
                <div key={i} className="flex items-center justify-between py-1 border-b border-white/5">
                  <span className="text-xs text-gray-300">
                    Edge {b.edge[0].slice(-4)}↔{b.edge[1].slice(-4)}
                  </span>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs"
                      style={{
                        color:
                          b.criticality === "CRITICAL"
                            ? "#FF4444"
                            : b.criticality === "HIGH"
                            ? "#FF8C00"
                            : "#FFB400",
                      }}
                    >
                      {b.criticality}
                    </span>
                    <span className="text-xs text-gray-500">{b.route_count} routes</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* NDMA/Sendai badge */}
          <div
            className="rounded-lg p-2 text-center text-xs"
            style={{ background: "rgba(0,229,180,0.05)", border: "1px solid rgba(0,229,180,0.2)" }}
          >
            <span style={{ color: "#00E5B4" }}>🌐 Sendai Framework Priority 4</span>
            <span className="text-gray-400 ml-1">— NDMA Compliant</span>
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="text-center py-6">
          <div className="text-2xl mb-2">🚨</div>
          <div className="text-xs text-gray-400">
            Click ▶ Run Evacuation to compute optimal routes
            <br />
            for all population zones to designated shelters.
          </div>
        </div>
      )}
    </div>
  );
}
