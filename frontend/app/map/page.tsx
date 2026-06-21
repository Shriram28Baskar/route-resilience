"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Layers, Hospital, GitBranch, AlertTriangle, Users } from "lucide-react";
import { getCriticality, getGraphMetrics, getHospitalAccessibility, getEmergencyServices, getEquityAnalysis, getGraphGeoJSON, type CriticalityResponse, type GraphMetrics, type HospitalAccessibility, type EmergencyServicesResponse, type EquityResponse } from "@/lib/api";
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
  const [activeLayer, setActiveLayer] = useState<"centrality" | "hospitals" | "topology" | "equity" | "emergency">("centrality");
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
    setLoading(true);
    try {
      const h = await getHospitalAccessibility();
      if (h) setHospitals(h);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadEmergencyServices = async () => {
    if (emergencyServices) return;
    setLoading(true);
    try {
      const e = await getEmergencyServices();
      if (e) setEmergencyServices(e);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
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

const LAYERS = [
  { id: "centrality", label: "Criticality",  icon: AlertTriangle },
  { id: "hospitals",  label: "Hospitals",    icon: Hospital },
  { id: "emergency",  label: "Fire & Police",icon: ShieldAlert },
  { id: "topology",   label: "Topology",     icon: GitBranch },
];
