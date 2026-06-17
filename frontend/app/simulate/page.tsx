"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, RotateCcw, GitMerge, Navigation, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import {
  getCriticality, ablateNodes, runCascade, computeRoute,
  getRecommendations, simulateInvestment, getFragilityCurve, runScenarios,
  simulateFlood, getReliefCamps,
  type AblationResponse, type CriticalityResponse, type Recommendation, type FragilityResponse, type MultiScenarioResponse
} from "@/lib/api";
import { resilienceColor, centralityColor, formatDistance, formatDuration } from "@/lib/utils";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine, CartesianGrid, Legend } from "recharts";
import { Waves, Tent } from "lucide-react";

type Tab = "ablate" | "cascade" | "route" | "recommend" | "fragility" | "scenarios" | "flood" | "relief";

export default function SimulatePage() {
  const [tab, setTab] = useState<Tab>("ablate");
  const [centrality, setCentrality] = useState<CriticalityResponse | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [autoTopN, setAutoTopN] = useState(3);
  const [ablation, setAblation] = useState<AblationResponse | null>(null);
  const [cascade, setCascade] = useState<any | null>(null);
  const [route, setRoute] = useState<any | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null);
  const [investmentSim, setInvestmentSim] = useState<any | null>(null);
  const [fragility, setFragility] = useState<FragilityResponse | null>(null);
  const [scenarios, setScenarios] = useState<MultiScenarioResponse | null>(null);
  const [flood, setFlood] = useState<any | null>(null);
  const [relief, setRelief] = useState<any | null>(null);
  const [waterLevel, setWaterLevel] = useState(880);
  const [elevationBounds, setElevationBounds] = useState({ min: 850, max: 950 });
  const [graphGeojson, setGraphGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [srcNode, setSrcNode] = useState("");
  const [tgtNode, setTgtNode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCriticality(20).then(setCentrality).catch(console.error);
    getGraphGeoJSON().then(setGraphGeojson).catch(console.error);
  }, []);

  const handleAblate = async () => {
    setLoading(true); setError(null);
    try {
      const res = await ablateNodes(selectedNodes, selectedNodes.length === 0 ? autoTopN : 0);
      setAblation(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleCascade = async () => {
    setLoading(true); setError(null);
    try {
      const seeds = selectedNodes.length > 0 ? selectedNodes :
        (centrality?.gatekeepers.slice(0, autoTopN).map(g => g.node_id) ?? []);
      const res = await runCascade(seeds, 3, 0.7);
      setCascade(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleRoute = async () => {
    if (!srcNode || !tgtNode) { setError("Please enter source and target node IDs"); return; }
    setLoading(true); setError(null);
    try {
      const res = await computeRoute(srcNode, tgtNode, ablation?.ablated_nodes ?? []);
      setRoute(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleRecommend = async () => {
    setLoading(true); setError(null);
    try {
      const res = await getRecommendations();
      setRecommendations(res.recommendations);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleSimulateInvestment = async (idx: number) => {
    setLoading(true); setError(null);
    try {
      const res = await simulateInvestment(idx);
      setInvestmentSim(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleFragility = async () => {
    setLoading(true); setError(null);
    try {
      const res = await getFragilityCurve();
      setFragility(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleScenarios = async () => {
    setLoading(true); setError(null);
    try {
      const gatekeepers = centrality?.gatekeepers.map(g => g.node_id) || [];
      const predefinedScenarios = [
        { name: "Baseline", description: "Normal operations, no disruptions", ablated_node_ids: [] },
        { name: "Minor Incident", description: "Isolated road closure", ablated_node_ids: gatekeepers.slice(0, 1) },
        { name: "Major Flood", description: "Corridor flooding", ablated_node_ids: gatekeepers.slice(0, 5) },
        { name: "Targeted Attack", description: "Coordinated failure of key intersections", ablated_node_ids: gatekeepers.slice(0, 10) }
      ];
      const res = await runScenarios(predefinedScenarios);
      setScenarios(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleFlood = async () => {
    setLoading(true); setError(null);
    try {
      const res = await simulateFlood(waterLevel);
      setFlood(res);
      if (res.elevation_bounds) {
        setElevationBounds(res.elevation_bounds);
      }
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleRelief = async () => {
    setLoading(true); setError(null);
    try {
      const res = await getReliefCamps(ablation?.ablated_nodes ?? [], 3);
      setRelief(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const reset = () => { setAblation(null); setCascade(null); setRoute(null); setRecommendations(null); setInvestmentSim(null); setFragility(null); setScenarios(null); setFlood(null); setRelief(null); setError(null); setSelectedNodes([]); setSrcNode(""); setTgtNode(""); };

  const handleMapClick = (nodeId: string) => {
    if (tab === "ablate" || tab === "cascade") {
      setSelectedNodes(prev => prev.includes(nodeId) ? prev.filter(n => n !== nodeId) : [...prev, nodeId]);
    } else if (tab === "route") {
      if (!srcNode) setSrcNode(nodeId);
      else if (!tgtNode && nodeId !== srcNode) setTgtNode(nodeId);
      else { setSrcNode(nodeId); setTgtNode(""); } // Reset and start over
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0F1A] p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-[#FFB400]/10 flex items-center justify-center">
              <Zap className="w-4 h-4 text-[#FFB400]" />
            </div>
            <h1 className="font-display text-2xl font-bold">Disaster Simulation</h1>
          </div>
          <p className="text-[#6B7280] text-sm">
            Ablate nodes, propagate cascading failures, and reroute emergency services.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-[#111827] p-1 rounded-xl border border-white/8 mb-6 w-fit">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id as Tab)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                tab === t.id ? "bg-[#00E5B4]/10 text-[#00E5B4] font-medium" : "text-[#6B7280] hover:text-white"
              }`}>
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
          <button onClick={reset} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-[#6B7280] hover:text-white ml-2">
            <RotateCcw className="w-4 h-4" /> Reset
          </button>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Control Panel */}
          <div className="lg:col-span-1 space-y-4">
            <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
              <h2 className="font-display font-semibold mb-4 text-sm uppercase tracking-widest text-[#6B7280]">
                Node Selection
              </h2>

              {/* Auto top-N */}
              <div className="mb-4">
                <label className="text-xs text-[#6B7280] mb-2 block">Auto-select top-N by centrality</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range" min={1} max={10} value={autoTopN}
                    onChange={e => setAutoTopN(+e.target.value)}
                    className="flex-1 accent-[#00E5B4]"
                  />
                  <span className="font-mono text-white w-4 text-center">{autoTopN}</span>
                </div>
              </div>

              {/* Manual node IDs */}
              <div className="mb-4">
                <label className="text-xs text-[#6B7280] mb-2 block">Or enter node IDs manually (comma-separated)</label>
                <textarea
                  className="w-full bg-[#0B0F1A] border border-white/8 rounded-lg p-3 text-xs font-mono text-white resize-none h-20 focus:outline-none focus:border-[#00E5B4]/40"
                  placeholder="e.g. 42, 17, 88"
                  value={selectedNodes.join(", ")}
                  onChange={e => setSelectedNodes(e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                />
              </div>

              {/* Gatekeeper quick-select */}
              {tab !== "recommend" && centrality && (
                <div>
                  <label className="text-xs text-[#6B7280] mb-2 block">Quick-select from gatekeepers</label>
                  <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                    {centrality.gatekeepers.slice(0, 10).map((g, i) => (
                      <button
                        key={g.node_id}
                        onClick={() => setSelectedNodes(prev =>
                          prev.includes(g.node_id) ? prev.filter(n => n !== g.node_id) : [...prev, g.node_id]
                        )}
                        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
                          selectedNodes.includes(g.node_id)
                            ? "bg-[#FF4444]/15 border border-[#FF4444]/30 text-white"
                            : "bg-[#0B0F1A] border border-white/5 text-[#6B7280] hover:border-white/15"
                        }`}
                      >
                        <span className="text-[#6B7280] w-4">#{i + 1}</span>
                        <div className="flex-1 h-1 bg-white/8 rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${g.score * 100}%`, background: centralityColor(g.score) }} />
                        </div>
                        <span className="font-mono">{(g.score * 100).toFixed(1)}%</span>
                        <span className="text-white font-mono text-[10px]">#{g.node_id.slice(-4)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Route inputs (only on route tab) */}
            {tab === "route" && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
                <h2 className="font-display font-semibold mb-4 text-sm uppercase tracking-widest text-[#6B7280]">Route Endpoints</h2>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-[#6B7280] mb-1 block">Source Node ID</label>
                    <input className="w-full bg-[#0B0F1A] border border-white/8 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-[#00E5B4]/40"
                      placeholder="e.g. 42" value={srcNode} onChange={e => setSrcNode(e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs text-[#6B7280] mb-1 block">Target Node ID</label>
                    <input className="w-full bg-[#0B0F1A] border border-white/8 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-[#00E5B4]/40"
                      placeholder="e.g. 99" value={tgtNode} onChange={e => setTgtNode(e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            {tab === "flood" && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
                <h2 className="font-display font-semibold mb-4 text-sm uppercase tracking-widest text-[#6B7280]">Water Level (m ASL)</h2>
                <input type="range" min={Math.floor(elevationBounds.min)} max={Math.ceil(elevationBounds.max)} step={1} value={waterLevel} onChange={e => setWaterLevel(+e.target.value)} className="w-full accent-[#00E5B4]" />
                <div className="text-white text-center mt-2 font-mono">{waterLevel}m</div>
                <p className="text-xs text-[#6B7280] mt-4 text-center">Slide to simulate rising floodwaters. Any road below this elevation will fail.</p>
              </div>
            )}

            {tab === "relief" && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
                <h2 className="font-display font-semibold mb-4 text-sm uppercase tracking-widest text-[#6B7280]">Optimal Relief Camps</h2>
                <p className="text-xs text-[#6B7280]">This uses a K-Center algorithm to compute 3 optimal relief camp locations on the currently surviving road network.</p>
                {ablation && (
                  <div className="mt-3 px-3 py-2 bg-[#FFB400]/10 border border-[#FFB400]/20 rounded-lg text-xs text-[#FFB400]">
                    Current Ablation applied: {ablation.ablated_nodes.length} nodes removed.
                  </div>
                )}
              </div>
            )}

            {/* Run button */}
            <button
              onClick={tab === "ablate" ? handleAblate : tab === "cascade" ? handleCascade : tab === "route" ? handleRoute : tab === "recommend" ? handleRecommend : tab === "fragility" ? handleFragility : tab === "flood" ? handleFlood : tab === "relief" ? handleRelief : handleScenarios}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-[#00E5B4] text-[#0B0F1A] font-display font-bold rounded-xl hover:bg-[#00B38A] transition-colors disabled:opacity-50"
            >
              {loading ? <span className="w-4 h-4 border-2 border-[#0B0F1A]/30 border-t-[#0B0F1A] rounded-full animate-spin" />
                : <Zap className="w-4 h-4" />}
              {loading ? "Running…" : TAB_ACTIONS[tab]}
            </button>

            {error && (
              <div className="bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-xl p-4 text-[#FF4444] text-xs">{error}</div>
            )}
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-2 space-y-4">
            <SimulateResults
              tab={tab}
              result={ablation}
              ablation={ablation}
              cascade={cascade}
              route={route}
              centrality={centrality}
              graphGeojson={graphGeojson}
              srcNode={srcNode}
              tgtNode={tgtNode}
              selectedNodes={selectedNodes}
              onMapClick={handleMapClick}
              recommendations={recommendations}
              investmentSim={investmentSim}
              fragility={fragility}
              scenarios={scenarios}
              flood={flood}
              relief={relief}
              handleSimulateInvestment={handleSimulateInvestment}
              loading={loading}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Result components ─────────────────────────────────────────────────────────

import dynamic from "next/dynamic";
import { getGraphGeoJSON } from "@/lib/api";

const RoadMap = dynamic(() => import("@/components/RoadMap"), { ssr: false });

function SimulateResults({ tab, result, ablation, cascade, route, centrality, graphGeojson, srcNode, tgtNode, selectedNodes, onMapClick, recommendations, investmentSim, fragility, scenarios, flood, relief, handleSimulateInvestment, loading }: any) {
  return (
    <div className="space-y-4">
      {/* Interactive Map view always available in simulation to select nodes */}
      <div className={`h-[400px] w-full rounded-xl overflow-hidden border border-white/8 relative bg-[#111827] ${tab === 'fragility' || tab === 'scenarios' ? 'hidden' : ''}`}>
        {graphGeojson ? (
          <RoadMap
            centrality={centrality}
            hospitals={null}
            equity={null}
            activeLayer="simulate"
            graphGeojson={graphGeojson}
            routeResult={route}
            srcNodeId={srcNode}
            tgtNodeId={tgtNode}
            selectedNodes={selectedNodes}
            onMapClick={onMapClick}
            floodNodes={flood?.ablated_nodes}
            reliefCamps={relief?.camps}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[#6B7280] text-sm flex-col gap-2">
            <div className="w-6 h-6 border-2 border-[#00E5B4]/30 border-t-[#00E5B4] rounded-full animate-spin" />
            Loading Map Data...
          </div>
        )}
        <div className="absolute top-4 left-4 z-[1000] bg-[#111827]/90 px-3 py-2 rounded shadow text-xs text-white pointer-events-none">
          {tab === "route" 
            ? "Click map to set Source/Target." 
            : "Click map to select nodes for ablation."}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {tab === "ablate" && ablation && (
          <motion.div key="ablation" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <AblationResults result={ablation} />
          </motion.div>
        )}
        {tab === "cascade" && cascade && (
          <motion.div key="cascade" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <CascadeResults result={cascade} />
          </motion.div>
        )}
        {tab === "route" && route && (
          <motion.div key="route" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <RouteResults result={route} />
          </motion.div>
        )}
        {tab === "recommend" && recommendations && (
          <motion.div key="recommend" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <RecommendationsResults recommendations={recommendations} investmentSim={investmentSim} onSimulate={handleSimulateInvestment} loading={loading} />
          </motion.div>
        )}
        {tab === "fragility" && fragility && (
          <motion.div key="fragility" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <FragilityResults fragility={fragility} />
          </motion.div>
        )}
        {tab === "scenarios" && scenarios && (
          <motion.div key="scenarios" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <ScenariosResults scenarios={scenarios} />
          </motion.div>
        )}
        {tab === "flood" && flood && (
          <motion.div key="flood" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="bg-[#111827] border border-[#0099FF]/30 rounded-xl p-6">
              <h3 className="font-display font-semibold text-lg text-[#0099FF] flex items-center gap-2 mb-2"><Waves className="w-5 h-5"/> Flood Simulation Active</h3>
              <p className="text-sm text-[#6B7280]">Water level: <span className="text-white font-mono">{flood.water_level}m</span>. <span className="text-[#FF4444] font-bold">{flood.ablated_nodes.length}</span> nodes flooded.</p>
              <p className="text-xs text-[#6B7280] mt-2">See map for visual overlay of flooded roads.</p>
            </div>
          </motion.div>
        )}
        {tab === "relief" && relief && (
          <motion.div key="relief" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="bg-[#111827] border border-[#00E5B4]/30 rounded-xl p-6">
              <h3 className="font-display font-semibold text-lg text-[#00E5B4] flex items-center gap-2 mb-4"><Tent className="w-5 h-5"/> Optimal Relief Camps Deployed</h3>
              <div className="grid grid-cols-3 gap-4">
                {relief.camps.map((c: any, i: number) => (
                  <div key={i} className="bg-[#0B0F1A] border border-white/8 rounded-lg p-4">
                    <div className="text-xs text-[#6B7280] uppercase mb-1">Camp {i+1}</div>
                    <div className="font-mono text-sm text-white">{Number(c.lat).toFixed(4)}, {Number(c.lng).toFixed(4)}</div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
        {!ablation && !cascade && !route && !recommendations && !fragility && !scenarios && !flood && !relief && (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="bg-[#111827] border border-white/8 rounded-xl p-8 text-center">
            <p className="text-[#6B7280] text-sm">Configure nodes and run a simulation to see results.</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AblationResults({ result }: { result: AblationResponse }) {
  const ri = result.resilience_index;
  const riColor = resilienceColor(ri);

  const chartData = [
    { name: "Nodes", before: result.baseline_metrics.num_nodes, after: result.perturbed_metrics.num_nodes },
    { name: "Edges", before: result.baseline_metrics.num_edges, after: result.perturbed_metrics.num_edges },
    { name: "LCC Size", before: result.baseline_metrics.largest_component_size, after: result.perturbed_metrics.largest_component_size },
  ];

  return (
    <div className="space-y-4">
      {/* Resilience Index hero */}
      <div className="bg-[#111827] border border-white/8 rounded-xl p-6 flex items-center justify-between">
        <div>
          <div className="text-xs text-[#6B7280] mb-1 font-mono uppercase tracking-widest">Resilience Index</div>
          <div className="font-display text-5xl font-bold" style={{ color: riColor }}>
            {ri !== null ? ri.toFixed(3) : "N/A"}
          </div>
          <div className="text-xs text-[#6B7280] mt-1">
            {result.disconnected
              ? "⚠ Network partitioned — graph disconnected after ablation"
              : ri !== null && ri < 0.8
              ? "⚠ High vulnerability — paths severely degraded"
              : "Network degradation within acceptable range"}
          </div>
        </div>
        <div className="text-right space-y-1">
          <div className="text-xs text-[#6B7280]">Ablated nodes</div>
          <div className="font-display text-2xl text-white">{result.ablated_nodes.length}</div>
          <div className="text-xs text-[#6B7280]">{result.disconnected ? "Disconnected" : `${result.perturbed_metrics.num_components} components`}</div>
        </div>
      </div>

      {/* Path length comparison */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Baseline Avg Path</div>
          <div className="font-display text-xl text-white">
            {result.baseline_avg_path_length?.toFixed(4) ?? "N/A"}
          </div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Perturbed Avg Path</div>
          <div className="font-display text-xl" style={{ color: resilienceColor(ri) }}>
            {result.perturbed_avg_path_length?.toFixed(4) ?? "N/A"}
          </div>
        </div>
      </div>

      {/* Before/After chart */}
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-4">Before vs After Ablation</h3>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} barGap={4}>
            <XAxis dataKey="name" tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ background: "#1C2333", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="before" name="Baseline" fill="#00E5B4" radius={[4, 4, 0, 0]} />
            <Bar dataKey="after"  name="Perturbed" fill="#FF4444" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Ablated node list */}
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-3">Ablated Nodes</h3>
        <div className="flex flex-wrap gap-2">
          {result.ablated_nodes.map(nid => (
            <span key={nid} className="px-2 py-1 bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-md text-xs font-mono text-[#FF4444]">
              #{nid}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function CascadeResults({ result }: { result: { cascade_steps: any[] } }) {
  const [expanded, setExpanded] = useState<number | null>(0);
  return (
    <div className="space-y-3">
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-1">Cascading Failure Propagation</h3>
        <p className="text-[#6B7280] text-xs">{result.cascade_steps.length} iteration(s) simulated</p>
      </div>
      {result.cascade_steps.map((step: any) => (
        <div key={step.iteration} className="bg-[#111827] border border-white/8 rounded-xl overflow-hidden">
          <button
            onClick={() => setExpanded(expanded === step.iteration ? null : step.iteration)}
            className="w-full flex items-center justify-between px-5 py-4 text-left"
          >
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 rounded-full bg-[#FFB400]/15 text-[#FFB400] text-xs flex items-center justify-center font-bold">
                {step.iteration + 1}
              </span>
              <span className="text-sm font-medium">Iteration {step.iteration + 1}</span>
              <span className="text-xs text-[#6B7280]">{step.newly_stressed.length} newly stressed</span>
              <span className="text-xs text-[#6B7280]">{step.component_count} components</span>
            </div>
            {expanded === step.iteration ? <ChevronUp className="w-4 h-4 text-[#6B7280]" /> : <ChevronDown className="w-4 h-4 text-[#6B7280]" />}
          </button>
          {expanded === step.iteration && (
            <div className="px-5 pb-4 border-t border-white/8 pt-4 space-y-3">
              <div>
                <div className="text-xs text-[#6B7280] mb-2">Ablated in this iteration</div>
                <div className="flex flex-wrap gap-1">
                  {step.ablated.map((nid: string) => (
                    <span key={nid} className="px-2 py-0.5 bg-[#FF4444]/10 border border-[#FF4444]/20 rounded text-xs font-mono text-[#FF4444]">#{nid}</span>
                  ))}
                </div>
              </div>
              {step.newly_stressed.length > 0 && (
                <div>
                  <div className="text-xs text-[#FFB400] mb-2">Newly stressed nodes (near-failure)</div>
                  <div className="space-y-1">
                    {step.newly_stressed.slice(0, 8).map((n: any) => (
                      <div key={n.node_id} className="flex items-center gap-2 text-xs">
                        <AlertTriangle className="w-3 h-3 text-[#FFB400]" />
                        <span className="font-mono text-white">#{n.node_id}</span>
                        <div className="flex-1 h-1 bg-white/8 rounded-full overflow-hidden">
                          <div className="h-full bg-[#FFB400] rounded-full" style={{ width: `${n.centrality * 100}%` }} />
                        </div>
                        <span className="text-[#6B7280]">{(n.centrality * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {step.note && <div className="text-xs text-[#6B7280] italic">{step.note}</div>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function RouteResults({ result }: { result: any }) {
  const baseline = result.baseline;
  const rerouted = result.rerouted;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <RouteCard title="Baseline Route" route={baseline} color="#00E5B4" />
        {rerouted && <RouteCard title="Rerouted (Post-Ablation)" route={rerouted} color="#FFB400" />}
      </div>
      {result.delta_distance_m !== null && (
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <h3 className="font-display font-semibold text-sm mb-3">Impact Delta</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-[#6B7280] mb-1">Extra Distance</div>
              <div className="font-display text-xl text-[#FFB400]">+{formatDistance(result.delta_distance_m)}</div>
            </div>
            <div>
              <div className="text-xs text-[#6B7280] mb-1">Extra Travel Time</div>
              <div className="font-display text-xl text-[#FFB400]">+{formatDuration(result.delta_time_s)}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RouteCard({ title, route, color }: { title: string; route: any; color: string }) {
  return (
    <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
      <h3 className="font-display font-semibold text-sm mb-3" style={{ color }}>{title}</h3>
      {route.reachable ? (
        <div className="space-y-2">
          <div><span className="text-xs text-[#6B7280]">Distance: </span><span className="font-mono text-white">{formatDistance(route.distance_m)}</span></div>
          <div><span className="text-xs text-[#6B7280]">Est. time: </span><span className="font-mono text-white">{formatDuration(route.travel_time_s)}</span></div>
          <div><span className="text-xs text-[#6B7280]">Nodes: </span><span className="font-mono text-white">{route.path_nodes.length}</span></div>
        </div>
      ) : (
        <div className="text-[#FF4444] text-xs">{route.reason ?? "No path found"}</div>
      )}
    </div>
  );
}

import { Shield, Waypoints } from "lucide-react";

function RecommendationsResults({ recommendations, investmentSim, onSimulate, loading }: { recommendations: Recommendation[], investmentSim: any, onSimulate: (idx: number) => void, loading: boolean }) {
  return (
    <div className="space-y-4">
      {investmentSim && (
        <div className="bg-[#111827] border border-[#00E5B4]/30 rounded-xl p-6">
          <h3 className="font-display font-semibold text-sm mb-4">Investment Simulation Results</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-[#6B7280] mb-1">Baseline RI</div>
              <div className="font-display text-xl text-white">{investmentSim.baseline_ri.toFixed(3)}</div>
            </div>
            <div>
              <div className="text-xs text-[#6B7280] mb-1">Projected RI</div>
              <div className="font-display text-xl text-[#00E5B4]">{investmentSim.projected_ri.toFixed(3)}</div>
            </div>
            <div>
              <div className="text-xs text-[#6B7280] mb-1">Resilience Gain</div>
              <div className="font-display text-xl text-[#FFB400]">+{investmentSim.rgs.toFixed(3)}</div>
            </div>
          </div>
        </div>
      )}

      {recommendations.map((rec, idx) => (
        <div key={idx} className="bg-[#111827] border border-white/8 rounded-xl p-5 flex flex-col gap-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${rec.type === 'bypass' ? 'bg-[#FFB400]/10' : 'bg-[#00E5B4]/10'}`}>
                {rec.type === 'bypass' ? <Waypoints className="w-5 h-5 text-[#FFB400]" /> : <Shield className="w-5 h-5 text-[#00E5B4]" />}
              </div>
              <div>
                <h3 className="font-display font-semibold text-sm">{rec.title}</h3>
                <p className="text-xs text-[#6B7280] mt-1">{rec.description}</p>
              </div>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-3">
              <div className="text-[10px] text-[#6B7280] uppercase tracking-wider mb-1">Est. Cost</div>
              <div className="font-mono text-sm">{rec.cost_estimate}</div>
            </div>
            <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-3">
              <div className="text-[10px] text-[#6B7280] uppercase tracking-wider mb-1">Resilience Gain Score</div>
              <div className="font-mono text-sm text-[#00E5B4]">+{rec.rgs.toFixed(3)}</div>
            </div>
          </div>
          
          <button 
            onClick={() => onSimulate(idx)}
            disabled={loading}
            className="w-full py-2 bg-white/5 hover:bg-white/10 rounded-lg text-xs font-medium transition-colors border border-white/8"
          >
            Simulate Investment
          </button>
        </div>
      ))}
    </div>
  );
}

function FragilityResults({ fragility }: { fragility: FragilityResponse }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#111827] border border-white/8 rounded-xl p-6">
          <div className="text-xs text-[#6B7280] mb-1">Percolation Threshold</div>
          <div className="font-display text-4xl font-bold text-[#FF4444]">
            {(fragility.percolation_threshold * 100).toFixed(1)}%
          </div>
          <div className="text-xs text-[#6B7280] mt-2">Critical fraction of removed nodes causing total network collapse.</div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-6">
          <div className="text-xs text-[#6B7280] mb-1">Robustness Integral (R)</div>
          <div className="font-display text-4xl font-bold text-[#00E5B4]">
            {fragility.robustness_integral.toFixed(3)}
          </div>
          <div className="text-xs text-[#6B7280] mt-2">Area under the LCC curve. Higher is more robust.</div>
        </div>
      </div>

      <div className="bg-[#111827] border border-white/8 rounded-xl p-6">
        <h3 className="font-display font-semibold text-sm mb-4">Fragility Curve</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={fragility.curve} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2A3441" vertical={false} />
            <XAxis 
              dataKey="fraction_ablated" 
              type="number" 
              domain={[0, 1]} 
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              stroke="#6B7280" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false} 
            />
            <YAxis 
              domain={[0, 1]} 
              stroke="#6B7280" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false} 
            />
            <Tooltip 
              contentStyle={{ background: "#1C2333", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8 }} 
              labelFormatter={(v) => `Ablated: ${(Number(v) * 100).toFixed(1)}%`}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#6B7280" }} />
            
            <ReferenceLine 
              x={fragility.percolation_threshold} 
              stroke="#FF4444" 
              strokeDasharray="3 3" 
              label={{ position: "top", value: "Percolation Threshold", fill: "#FF4444", fontSize: 10 }} 
            />
            
            <Line 
              type="monotone" 
              dataKey="lcc_fraction" 
              name="LCC Size Fraction" 
              stroke="#00E5B4" 
              strokeWidth={3} 
              dot={{ r: 3, fill: "#00E5B4" }} 
              activeDot={{ r: 5 }} 
            />
            <Line 
              type="monotone" 
              dataKey="efficiency" 
              name="Global Efficiency" 
              stroke="#FFB400" 
              strokeWidth={2} 
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

import { Download } from "lucide-react";

function ScenariosResults({ scenarios }: { scenarios: MultiScenarioResponse }) {
  const data = scenarios.scenarios;
  // Worst case has lowest RI
  const worstCase = [...data].sort((a, b) => a.ri - b.ri)[0];

  const handleExportCSV = () => {
    if (!data.length) return;
    const headers = ["Scenario Name", "Description", "Ablated Nodes", "Resilience Index", "LCC Fraction", "Global Efficiency"];
    const rows = data.map(s => [
      `"${s.name}"`, 
      `"${s.description}"`, 
      s.ablated_count, 
      s.ri, 
      s.lcc_fraction, 
      s.efficiency
    ]);
    const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "scenarios_export.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-display font-semibold text-lg">Multi-Scenario Comparison</h3>
        <button onClick={handleExportCSV} className="flex items-center gap-2 px-3 py-1.5 bg-[#111827] border border-white/8 rounded-lg text-xs hover:bg-white/5 transition-colors">
          <Download className="w-3 h-3" /> Export CSV
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {data.map((s, i) => {
          const isWorst = s === worstCase && data.length > 1 && s.ri < 1;
          return (
            <div key={i} className={`bg-[#111827] border rounded-xl p-5 ${isWorst ? 'border-[#FF4444]' : 'border-white/8'}`}>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h4 className="font-display font-semibold text-sm flex items-center gap-2">
                    {s.name}
                    {isWorst && <span className="px-1.5 py-0.5 bg-[#FF4444]/10 text-[#FF4444] text-[10px] uppercase rounded">Worst Case</span>}
                  </h4>
                  <p className="text-xs text-[#6B7280] mt-1">{s.description}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-1">Resilience Index</div>
                  <div className="font-mono text-lg" style={{ color: resilienceColor(s.ri) }}>
                    {s.ri.toFixed(3)}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-1">Efficiency</div>
                  <div className="font-mono text-lg text-white">
                    {(s.efficiency * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import { Activity, LayoutGrid } from "lucide-react";

const TABS = [
  { id: "ablate",  label: "Node Ablation",     icon: Zap },
  { id: "cascade", label: "Cascade Failure",   icon: GitMerge },
  { id: "route",   label: "Emergency Route",   icon: Navigation },
  { id: "flood",   label: "Flood Sim",         icon: Waves },
  { id: "relief",  label: "Relief Camps",      icon: Tent },
  { id: "recommend", label: "Recommendations", icon: Shield },
  { id: "fragility", label: "Fragility Curve", icon: Activity },
  { id: "scenarios", label: "Compare Scenarios", icon: LayoutGrid },
];

const TAB_ACTIONS: Record<Tab, string> = {
  ablate:  "Run Ablation",
  cascade: "Run Cascade",
  route:   "Compute Route",
  recommend: "Get Recommendations",
  fragility: "Generate Curve",
  scenarios: "Compare Scenarios",
  flood: "Simulate Flood",
  relief: "Deploy Camps"
};
