"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Layers, Hospital, GitBranch, AlertTriangle, Users, Zap } from "lucide-react";
import { getCriticality, getGraphMetrics, getHospitalAccessibility, getEmergencyServices, getEquityAnalysis, getGraphGeoJSON, getAccessibilityImpact, type CriticalityResponse, type GraphMetrics, type HospitalAccessibility, type EmergencyServicesResponse, type EquityResponse, type AccessibilityImpactResponse } from "@/lib/api";
import { centralityColor, resilienceColor } from "@/lib/utils";

// Dynamically import the map to avoid SSR issues with Leaflet
const RoadMap = dynamic(() => import("@/components/RoadMap"), { ssr: false, loading: () => <MapSkeleton /> });

export default function MapPage() {
  const [criticality, setCriticality] = useState<CriticalityResponse | null>(null);
  const [metrics, setMetrics] = useState<GraphMetrics | null>(null);
  const [hospitals, setHospitals] = useState<HospitalAccessibility | null>(null);
  const [emergencyServices, setEmergencyServices] = useState<EmergencyServicesResponse | null>(null);
  const [equity, setEquity] = useState<EquityResponse | null>(null);
  const [graphGeojson, setGraphGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [impactData, setImpactData] = useState<AccessibilityImpactResponse | null>(null);
  const [impactTopN, setImpactTopN] = useState(3);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);
  const [activeLayer, setActiveLayer] = useState<"centrality" | "hospitals" | "topology" | "equity" | "emergency" | "impact">("centrality");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGraphGeoJSON().then(setGraphGeojson).catch(console.error);
    getGraphMetrics().then(setMetrics).catch(console.error);
    getEquityAnalysis().then(setEquity).catch(console.error);
    getCriticality(50)
      .then(setCriticality)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const loadHospitals = async () => {
    if (hospitals) return;
    try {
      const h = await getHospitalAccessibility();
      if (h) setHospitals(h);
    } catch (e) {
      console.error(e);
    }
  };

  const loadEmergencyServices = async () => {
    if (emergencyServices) return;
    try {
      const e = await getEmergencyServices();
      if (e) setEmergencyServices(e);
    } catch (e) {
      console.error(e);
    }
  };

  const runImpactAnalysis = async () => {
    if (!criticality) return;
    setImpactLoading(true);
    setImpactError(null);
    try {
      // Use top-N gatekeeper nodes as failure scenario
      const topNodes = criticality.gatekeepers.slice(0, impactTopN).map(n => n.node_id);
      const result = await getAccessibilityImpact(topNodes);
      setImpactData(result);
    } catch (e: any) {
      setImpactError(e.message || "Impact analysis failed");
    } finally {
      setImpactLoading(false);
    }
  };

  useEffect(() => {
    if (activeLayer === "hospitals") loadHospitals();
    if (activeLayer === "emergency") loadEmergencyServices();
  }, [activeLayer]);

  return (
    <div className="h-screen flex flex-col bg-[#0B0F1A]">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 bg-[#111827] border-b border-white/8">
        <span className="font-display text-sm font-semibold mr-2">Road Network Map</span>
        <div className="flex items-center gap-1">
          {LAYERS.map((layer) => (
            <button
              key={layer.id}
              onClick={() => setActiveLayer(layer.id as typeof activeLayer)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors ${
                activeLayer === layer.id
                  ? "bg-[#00E5B4]/15 text-[#00E5B4] border border-[#00E5B4]/30"
                  : "text-[#6B7280] hover:text-white hover:bg-white/5"
              }`}
            >
              <layer.icon className="w-3.5 h-3.5" />
              {layer.label}
            </button>
          ))}
        </div>

        {/* Connectivity badge */}
        {metrics && (
          <div className="ml-auto flex items-center gap-3 text-xs text-[#6B7280]">
            <span>{metrics.num_nodes.toLocaleString()} nodes</span>
            <span>{metrics.num_edges.toLocaleString()} edges</span>
            <span className={`font-mono ${metrics.num_components > 1 ? "text-[#FFB400]" : "text-[#22C55E]"}`}>
              {metrics.num_components} component{metrics.num_components !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>

      {/* Map + Legend row */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 relative">
          {loading ? (
            <MapSkeleton />
          ) : (
            <RoadMap
              centrality={criticality}
              hospitals={hospitals}
              emergencyServices={emergencyServices}
              equity={equity}
              activeLayer={activeLayer}
              graphGeojson={graphGeojson}
              impactData={impactData}
            />
          )}
        </div>

        {/* Legend panel */}
        <aside className="w-64 bg-[#111827] border-l border-white/8 overflow-y-auto p-4 text-xs space-y-6">
          {activeLayer === "centrality" && criticality && (
            <CentralityLegend centrality={criticality} />
          )}
          {activeLayer === "hospitals" && hospitals && (
            <HospitalLegend hospitals={hospitals} />
          )}
          {activeLayer === "equity" && equity && (
            <EquityLegend equity={equity} />
          )}
          {activeLayer === "impact" && (
            <ImpactPanel
              criticality={criticality}
              impactData={impactData}
              impactTopN={impactTopN}
              setImpactTopN={setImpactTopN}
              onRun={runImpactAnalysis}
              loading={impactLoading}
              error={impactError}
            />
          )}
          {activeLayer === "emergency" && emergencyServices && (
            <EmergencyLegend emergencyServices={emergencyServices} />
          )}
          {activeLayer === "topology" && metrics && (
            <TopologyPanel metrics={metrics} />
          )}
        </aside>
      </div>
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function CentralityLegend({ centrality }: { centrality: CriticalityResponse }) {
  return (
    <>
      <div>
        <h3 className="font-display font-semibold text-white mb-3">Betweenness Centrality</h3>
        <div className="h-3 w-full rounded-full mb-1"
          style={{ background: "linear-gradient(to right, #22C55E, #FFB400, #FF4444)" }}
        />
        <div className="flex justify-between text-[#6B7280]">
          <span>Low risk</span><span>High risk</span>
        </div>
      </div>

      <div>
        <h3 className="font-display font-semibold text-white mb-2 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-[#FF4444]" />
          Top Gatekeepers
        </h3>
        <div className="space-y-2">
          {centrality.gatekeepers.slice(0, 10).map((node, i) => (
            <div key={node.node_id} className="flex items-center justify-between">
              <span className="text-[#6B7280] w-5 shrink-0">#{i + 1}</span>
              <div className="flex-1 h-1.5 bg-white/8 rounded-full mx-2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${node.score * 100}%`, background: centralityColor(node.score) }}
                />
              </div>
              <span className="font-mono text-white">{(node.score * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function HospitalLegend({ hospitals }: { hospitals: HospitalAccessibility }) {
  return (
    <>
      <div>
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Hospitals</div>
        <div className="font-display text-2xl text-white">{hospitals.hospitals.length}</div>
        <div className="text-[#6B7280] text-xs">facilities accessible in area</div>
      </div>
      <div>
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Markers</div>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-[#00E5B4] flex items-center justify-center font-bold text-[#0B0F1A] text-[9px] border border-white/10">H</span>
            <span>Hospitals & Clinics</span>
          </div>
        </div>
      </div>
    </>
  );
}

function EquityLegend({ equity }: { equity: EquityResponse }) {
  const scoreColor = equity.equity_score >= 80 ? "#00E5B4" : equity.equity_score >= 50 ? "#FFB400" : "#FF4444";
  return (
    <>
      <div>
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Overall Equity Score</div>
        <div className="font-display text-4xl font-bold" style={{ color: scoreColor }}>{equity.equity_score}</div>
        <div className="text-[#6B7280] text-xs">/ 100 based on access</div>
      </div>
      <div>
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Healthcare Deserts</div>
        <div className="font-display text-xl text-[#FF4444]">{equity.desert_count}</div>
        <div className="text-[#6B7280] text-xs">&gt; 5km to nearest facility</div>
      </div>
      <div>
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Vulnerable Clusters</div>
        <div className="font-display text-xl text-[#FFB400]">{equity.vulnerable_clusters.length}</div>
        <div className="text-[#6B7280] text-xs">populations at risk</div>
      </div>
      <div className="space-y-2">
        <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Legend</div>
        <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#FF4444]/20 border border-[#FF4444]/50 rounded-full"></div><span>Healthcare Desert</span></div>
        <div className="flex items-center gap-2"><div className="w-3 h-3 bg-transparent border-2 border-[#FFB400] border-dashed rounded-full"></div><span>Vulnerable Cluster</span></div>
      </div>
    </>
  );
}

function TopologyPanel({ metrics }: { metrics: GraphMetrics }) {
  const rows = [
    ["Nodes",          metrics.num_nodes.toLocaleString()],
    ["Edges",          metrics.num_edges.toLocaleString()],
    ["Components",     metrics.num_components.toString()],
    ["LCC Size",       metrics.largest_component_size.toLocaleString()],
    ["LCC Fraction",   `${(metrics.largest_component_fraction * 100).toFixed(1)}%`],
    ["Avg Degree",     metrics.avg_node_degree.toFixed(2)],
    ["Density",        metrics.density.toFixed(5)],
    ["Avg Path",       metrics.avg_shortest_path_length?.toFixed(3) ?? "N/A"],
  ];
  return (
    <>
      <h3 className="font-display font-semibold text-white mb-3 flex items-center gap-1.5">
        <GitBranch className="w-3.5 h-3.5 text-[#00E5B4]" />
        Graph Metrics
      </h3>
      <div className="space-y-2">
        {rows.map(([label, val]) => (
          <div key={label} className="flex justify-between">
            <span className="text-[#6B7280]">{label}</span>
            <span className="font-mono text-white">{val}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function MapSkeleton() {
  return (
    <div className="w-full h-full bg-[#0B0F1A] flex items-center justify-center">
      <div className="text-center space-y-2">
        <div className="w-8 h-8 border-2 border-[#00E5B4]/30 border-t-[#00E5B4] rounded-full animate-spin mx-auto" />
        <p className="text-[#6B7280] text-xs">Loading road network …</p>
      </div>
    </div>
  );
}

function ImpactPanel({
  criticality, impactData, impactTopN, setImpactTopN, onRun, loading, error
}: {
  criticality: CriticalityResponse | null;
  impactData: AccessibilityImpactResponse | null;
  impactTopN: number;
  setImpactTopN: (n: number) => void;
  onRun: () => void;
  loading: boolean;
  error: string | null;
}) {
  const fmt = (s: number | null | undefined) =>
    s != null ? `${Math.round(s)}s (${Math.round(s / 60)}m)` : "N/A";

  return (
    <>
      <div>
        <h3 className="font-display font-semibold text-white mb-3 flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-[#FF4444]" />
          Impact Engine
        </h3>
        <p className="text-[#6B7280] mb-3 leading-relaxed">
          Simulate failure of top critical nodes and compute emergency accessibility impact.
        </p>
        <label className="block text-[#6B7280] mb-1">Ablate top-N nodes</label>
        <select
          value={impactTopN}
          onChange={e => setImpactTopN(Number(e.target.value))}
          className="w-full bg-[#0B0F1A] border border-white/10 rounded px-2 py-1.5 text-white text-xs mb-3"
        >
          {[1, 3, 5, 10, 25, 50].map(n => (
            <option key={n} value={n}>Top {n} gatekeeper{n > 1 ? "s" : ""}</option>
          ))}
        </select>
        <button
          onClick={onRun}
          disabled={loading || !criticality}
          className="w-full py-2 rounded-md bg-[#FF4444]/15 border border-[#FF4444]/30 text-[#FF4444] text-xs font-semibold hover:bg-[#FF4444]/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading
            ? <><span className="w-3 h-3 border border-[#FF4444]/50 border-t-[#FF4444] rounded-full animate-spin" />Computing…</>
            : "Run Impact Analysis"
          }
        </button>
        {error && <p className="text-[#FF4444] mt-2 text-[10px] break-words">{error}</p>}
      </div>

      {impactData && (
        <>
          <div>
            <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Hospitals in AOI</div>
            <div className="font-display text-2xl text-[#00E5B4]">{impactData.hospital_count}</div>
          </div>

          <div className="space-y-2">
            <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">15-min Accessibility</div>
            <div className="flex justify-between">
              <span className="text-[#22C55E]">Baseline accessible</span>
              <span className="font-mono text-white">{impactData.baseline.accessible_node_count.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#FF4444]">Post-disaster accessible</span>
              <span className="font-mono text-white">{impactData.post_disaster.accessible_node_count.toLocaleString()}</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Impact</div>
            <div className="flex justify-between">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#FF4444] inline-block" />Lost access</span>
              <span className="font-mono text-[#FF4444] font-bold">{impactData.impact.nodes_lost_access_count.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#FFB400] inline-block" />Degraded</span>
              <span className="font-mono text-[#FFB400] font-bold">{impactData.impact.nodes_degraded_count.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Hospitals disconnected</span>
              <span className="font-mono text-white">{impactData.impact.disconnected_hospital_count}</span>
            </div>
            <div className="flex justify-between">
              <span>Avg time increase</span>
              <span className="font-mono text-white">{fmt(impactData.impact.avg_travel_time_increase_s)}</span>
            </div>
          </div>

          {impactData.impact.resilience_index != null && (
            <div>
              <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Resilience Index</div>
              <div className="font-display text-2xl font-bold" style={{ color: impactData.impact.resilience_index > 0.7 ? "#22C55E" : impactData.impact.resilience_index > 0.4 ? "#FFB400" : "#FF4444" }}>
                {impactData.impact.resilience_index.toFixed(3)}
              </div>
            </div>
          )}

          {impactData.best_alternative_route?.reachable && (
            <div>
              <div className="text-[#6B7280] uppercase tracking-widest mb-2 font-mono text-[10px]">Alternative Route</div>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="w-4 h-0.5 bg-[#3B82F6] rounded border-dashed border inline-block" />
                <span className="text-[#3B82F6] font-semibold">Available (blue dashed)</span>
              </div>
              <div className="flex justify-between">
                <span>Travel time</span>
                <span className="font-mono text-white">{fmt(impactData.best_alternative_route.travel_time_s)}</span>
              </div>
            </div>
          )}

          <div className="space-y-1.5 pt-2 border-t border-white/8">
            <div className="text-[#6B7280] uppercase tracking-widest mb-1 font-mono text-[10px]">Legend</div>
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-[#FF4444] inline-block" /><span>Lost 15-min hospital access</span></div>
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-[#FFB400] inline-block" /><span>Degraded accessibility (&gt;50% slower)</span></div>
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-[#00E5B4] inline-block" /><span>Hospital / Clinic</span></div>
            <div className="flex items-center gap-2"><span className="w-4 h-0.5 bg-[#3B82F6] inline-block rounded" /><span>Best alternative route</span></div>
          </div>
        </>
      )}
    </>
  );
}

const LAYERS = [
  { id: "centrality", label: "Criticality",  icon: AlertTriangle },
  { id: "hospitals",  label: "Hospitals",    icon: Hospital },
  { id: "emergency",  label: "Fire & Police",icon: ShieldAlert },
  { id: "impact",     label: "Impact",       icon: Zap },
  { id: "topology",   label: "Topology",     icon: GitBranch },
];

function EmergencyLegend({ emergencyServices }: { emergencyServices: EmergencyServicesResponse }) {
  const fireCount = emergencyServices.facilities.filter(f => f.amenity === "fire_station").length;
  const policeCount = emergencyServices.facilities.filter(f => f.amenity === "police").length;
  return (
    <>
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-widest text-[#6B7280] mb-3">
          Fire & Police Stations
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded-full flex-shrink-0" style={{ background: "#FF8C00", boxShadow: "0 0 6px rgba(255,140,0,0.6)" }} />
            <div>
              <div className="text-white text-xs font-semibold">Fire Stations</div>
              <div className="text-[#6B7280] text-[10px]">{fireCount} stations · orange circles</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded-full flex-shrink-0" style={{ background: "#0099FF", boxShadow: "0 0 6px rgba(0,153,255,0.6)" }} />
            <div>
              <div className="text-white text-xs font-semibold">Police Stations</div>
              <div className="text-[#6B7280] text-[10px]">{policeCount} stations · blue circles</div>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-white/8 text-[9px] text-[#6B7280]">
          Click any circle to see name & type · Source: OpenStreetMap
        </div>
      </div>
    </>
  );
}
