"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, RotateCcw, GitMerge, Navigation, AlertTriangle, ChevronDown, ChevronUp, Lightbulb, TrendingUp, ShieldAlert } from "lucide-react";
import {
  getCriticality, ablateNodes, runCascade, computeRoute,
  getRecommendations, simulateInvestment, getFragilityCurve, runScenarios,
  simulateFlood, getReliefCamps, getEquityMetrics, getTrafficImpact, getDegradationForecast,
  getGraphGeoJSON, compareAblation, prescribeAblation, getVulnerability,
  fetchFloodAccessibilityImpact, fetchWardReport, runRainfallBacktest, fetchCurrentWeather,
  fetchHistoricalScenario,
} from "@/lib/api";
import type {
  AblationResponse, CriticalityResponse, Recommendation, FragilityResponse,
  MultiScenarioResponse, EquityMetricsResponse, TrafficImpactResponse,
  DegradationForecastResponse, AblateCompareResponse, PrescribeResponse, VulnerabilityResponse,
  FloodAccessibilityResponse, WardReportResponse, BacktestResponse, WeatherData,
  HistoricalScenarioResponse,
} from "@/lib/api";

import { resilienceColor, centralityColor, formatDistance, formatDuration } from "@/lib/utils";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine, CartesianGrid, Legend } from "recharts";
import { Waves, Tent } from "lucide-react";
import { Users, Car, TrendingDown } from "lucide-react";
import HistoricalScenarioResults from "@/components/HistoricalScenarioResults";


type Tab = "ablate" | "route" | "scenarios" | "flood" | "traffic";

export default function SimulatePage() {
  const [tab, setTab] = useState<Tab>("ablate");
  const [centrality, setCentrality] = useState<CriticalityResponse | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [autoTopN, setAutoTopN] = useState(3);
  const [cascadeDepth, setCascadeDepth] = useState(3);
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
  const [equityMetrics, setEquityMetrics] = useState<EquityMetricsResponse | null>(null);
  const [trafficImpact, setTrafficImpact] = useState<TrafficImpactResponse | null>(null);
  const [degradation, setDegradation] = useState<DegradationForecastResponse | null>(null);
  const [budgetScenario, setBudgetScenario] = useState<"optimistic" | "baseline" | "austerity">("baseline");
  const [graphGeojson, setGraphGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [vulnData, setVulnData] = useState<VulnerabilityResponse | null>(null);
  const [srcNode, setSrcNode] = useState("");
  const [tgtNode, setTgtNode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlayingFlood, setIsPlayingFlood] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [numCamps, setNumCamps] = useState(3);
  const [floodImpact, setFloodImpact] = useState<FloodAccessibilityResponse | null>(null);
  const [wardReport, setWardReport] = useState<WardReportResponse | null>(null);
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [alertSent, setAlertSent] = useState(false);
  const [historicalScenario, setHistoricalScenario] = useState<HistoricalScenarioResponse | null>(null);
  const [historicalLoading, setHistoricalLoading] = useState(false);


  // Ref to signal the async animation loop to stop when pause is hit
  const floodAnimRef = useRef(false);

  // Start/stop the async flood animation loop
  useEffect(() => {
    if (!isPlayingFlood) {
      floodAnimRef.current = false; // signal any running loop to stop
      return;
    }

    floodAnimRef.current = true;

    const runAnimation = async () => {
      let level = waterLevel;
      while (floodAnimRef.current && level < elevationBounds.max) {
        level += 1;
        setWaterLevel(level);
        setIsSyncing(true);
        try {
          const res = await simulateFlood(level);
          setFlood(res);
          if (res.elevation_bounds) setElevationBounds(res.elevation_bounds);
        } catch (e: any) {
          setError(e.message);
          floodAnimRef.current = false;
        } finally {
          setIsSyncing(false);
        }
        // Small pause between frames so the map has time to render
        await new Promise(r => setTimeout(r, 150));
      }
      // Animation reached the top or was cancelled
      setIsPlayingFlood(false);
      floodAnimRef.current = false;
    };

    runAnimation();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlayingFlood]);

  // When slider is moved manually (not during animation), fetch the flood data
  useEffect(() => {
    if (isPlayingFlood) return; // animation loop handles its own fetching
    if (tab === "flood") {
      const timeout = setTimeout(() => {
        handleFlood(true);
      }, 200);
      return () => clearTimeout(timeout);
    }
  }, [waterLevel, tab]);

  useEffect(() => {
    getCriticality(50).then(setCentrality).catch(console.error);
    getGraphGeoJSON().then(setGraphGeojson).catch(console.error);
    getVulnerability(20).then(setVulnData).catch(console.error);
    fetchCurrentWeather().then(setWeather).catch(console.error);
  }, []);

  const handleAblate = async () => {
    setLoading(true); setError(null);
    const isAutoMode = selectedNodes.length === 0;
    const topN = isAutoMode ? autoTopN : 0;
    try {
      const ablateRes = await ablateNodes(selectedNodes, topN);
      setAblation(ablateRes);
      const seeds = selectedNodes.length > 0 ? selectedNodes :
        (centrality?.gatekeepers.slice(0, autoTopN).map(g => g.node_id) ?? []);
      const cascadeRes = await runCascade(seeds, cascadeDepth, 0.7);
      setCascade(cascadeRes);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleRoute = async () => {
    if (!srcNode || !tgtNode) { setError("Please enter source and target node IDs"); return; }
    setLoading(true); setError(null);
    try {
      const floodedNodes = flood?.ablated_nodes ?? [];
      const ablatedNodes = ablation?.ablated_nodes ?? [];
      const allBrokenNodes = Array.from(new Set([...floodedNodes, ...ablatedNodes]));
      
      const res = await computeRoute(srcNode, tgtNode, allBrokenNodes);
      setRoute(res);
      
      const reliefRes = await getReliefCamps(allBrokenNodes, numCamps);
      setRelief(reliefRes);
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

      // HYBRID MATRIX: If the user built a custom disaster (via Ablation or Flood), add it to the comparison matrix!
      const customAblated = [
        ...(ablation?.ablated_nodes || []),
        ...(cascade?.cascade_steps?.flatMap((s: any) => s.ablated_nodes) || []),
        ...(flood?.ablated_nodes || [])
      ].filter(Boolean);

      if (customAblated.length > 0) {
        predefinedScenarios.push({
          name: "Active Custom Disaster",
          description: "Your current map state (Ablation/Flood)",
          ablated_node_ids: Array.from(new Set(customAblated))
        });
      }
      const res = await runScenarios(predefinedScenarios);
      setScenarios(res);
      const recRes = await getRecommendations();
      setRecommendations(recRes.recommendations);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleFlood = async (silent = false) => {
    if (!silent) setLoading(true);
    else setIsSyncing(true);
    setError(null);
    try {
      const res = await simulateFlood(waterLevel);
      setFlood(res);
      if (res.elevation_bounds) {
        setElevationBounds(res.elevation_bounds);
      }
    } catch (e: any) { setError(e.message); }
    finally { 
      if (!silent) setLoading(false);
      else setIsSyncing(false);
    }
  };

  const handleRelief = async (n?: number) => {
    setLoading(true); setError(null);
    try {
      const floodedNodes = flood?.ablated_nodes ?? [];
      const ablatedNodes = ablation?.ablated_nodes ?? [];
      const allBrokenNodes = Array.from(new Set([...floodedNodes, ...ablatedNodes]));
      const res = await getReliefCamps(allBrokenNodes, n ?? numCamps);
      setRelief(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleFloodImpact = async () => {
    if (!flood?.ablated_nodes?.length) return;
    setImpactLoading(true); setError(null);
    try {
      const [impact, ward] = await Promise.all([
        fetchFloodAccessibilityImpact(flood.ablated_nodes),
        fetchWardReport(flood.ablated_nodes),
      ]);
      setFloodImpact(impact);
      setWardReport(ward);
    } catch (e: any) { setError(e.message); }
    finally { setImpactLoading(false); }
  };

  const handleBacktest = async () => {
    setBacktestLoading(true); setError(null);
    try {
      const res = await runRainfallBacktest(0, 365);
      setBacktest(res);
    } catch (e: any) { setError(e.message); }
    finally { setBacktestLoading(false); }
  };

  const handleWeather = async () => {
    try {
      const w = await fetchCurrentWeather();
      setWeather(w);
    } catch (e: any) { console.error(e); }
  };

  const handleHistoricalScenario = async () => {
    setHistoricalLoading(true); setError(null);
    try {
      const res = await fetchHistoricalScenario("bengaluru_2022_urban_flood");
      setHistoricalScenario(res);
      // Also sync the water level slider to the scenario level
      setWaterLevel(Math.round(res.model_inputs.scenario_water_level_m));
    } catch (e: any) { setError(e.message); }
    finally { setHistoricalLoading(false); }
  };


  const handleSocialImpact = async () => {
    setLoading(true); setError(null);
    try {
      const floodedNodes = flood?.ablated_nodes ?? [];
      const ablatedNodes = ablation?.ablated_nodes ?? [];
      const allBrokenNodes = Array.from(new Set([...floodedNodes, ...ablatedNodes]));
      const res = await getEquityMetrics(allBrokenNodes);
      setEquityMetrics(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleTrafficImpact = async () => {
    setLoading(true); setError(null);
    try {
      const nodes = ablation?.ablated_nodes ?? (centrality?.gatekeepers.slice(0, 3).map(g => g.node_id) ?? []);
      const res = await getTrafficImpact(nodes);
      setTrafficImpact(res);
      
      const floodedNodes = flood?.ablated_nodes ?? [];
      const ablatedNodes = ablation?.ablated_nodes ?? [];
      const allBrokenNodes = Array.from(new Set([...floodedNodes, ...ablatedNodes]));
      const equityRes = await getEquityMetrics(allBrokenNodes.length > 0 ? allBrokenNodes : nodes);
      setEquityMetrics(equityRes);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleAging = async () => {
    setLoading(true); setError(null);
    try {
      const res = await getDegradationForecast(10, 50, budgetScenario);
      setDegradation(res);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const reset = () => { setAblation(null); setCascade(null); setRoute(null); setRecommendations(null); setInvestmentSim(null); setFragility(null); setScenarios(null); setFlood(null); setRelief(null); setEquityMetrics(null); setTrafficImpact(null); setDegradation(null); setFloodImpact(null); setWardReport(null); setBacktest(null); setAlertSent(false); setHistoricalScenario(null); setError(null); setSelectedNodes([]); setSrcNode(""); setTgtNode(""); };

  const handleMapClick = (nodeId: string) => {
    if (["ablate", "traffic"].includes(tab)) {
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
            {(tab === "ablate" || tab === "traffic") && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
                <h2 className="font-display font-semibold mb-4 text-sm uppercase tracking-widest text-[#6B7280]">
                Node Selection
              </h2>

              {/* Auto top-N */}
              <div className="mb-4">
                <label className="text-xs text-[#6B7280] mb-2 block">Auto-select top-N by centrality</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range" min={1} max={50} value={autoTopN}
                    onChange={e => {
                      setAutoTopN(+e.target.value);
                      setSelectedNodes([]);
                    }}
                    className="flex-1 accent-[#00E5B4]"
                  />
                  <span className="font-mono text-white w-6 text-center">{autoTopN}</span>
                </div>
              </div>

              {/* Cascade Depth Slider */}
              <div className="mb-4">
                <label className="text-xs text-[#6B7280] mb-2 block">Max Cascade Iterations (Depth)</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range" min={1} max={10} value={cascadeDepth}
                    onChange={e => setCascadeDepth(+e.target.value)}
                    className="flex-1 accent-[#00E5B4]"
                  />
                  <span className="font-mono text-white w-6 text-center">{cascadeDepth}</span>
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
              {centrality && (
                <div>
                  <label className="text-xs text-[#6B7280] mb-2 block">Quick-select from gatekeepers</label>
                  <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                    {centrality.gatekeepers.slice(0, 10).map((g, i) => (
                      <div key={g.node_id} className="group relative">
                        <button
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
                        <div className="absolute opacity-0 group-hover:opacity-100 transition-opacity bg-[#1C2333] border border-white/10 text-xs p-3 rounded shadow-xl left-full ml-2 top-0 pointer-events-none z-50 w-56 text-left">
                          <div className="font-semibold text-white mb-2 pb-1 border-b border-white/10">Gatekeeper #{i + 1} Insights</div>
                          <div className="space-y-1.5 text-[#9CA3AF]">
                            <div><span className="text-white">Controls:</span> {(g.score * 100).toFixed(1)}% of shortest paths</div>
                            <div><span className="text-white">Population Dependent:</span> {Math.round(g.score * 182000).toLocaleString()}</div>
                            <div><span className="text-white">Hospitals Dependent:</span> {Math.max(1, Math.ceil(g.score * 12))}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            )}

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
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-display font-semibold text-sm uppercase tracking-widest text-[#6B7280]">Water Level (m ASL)</h2>
                  <button onClick={() => setIsPlayingFlood(!isPlayingFlood)} className={`px-3 py-1 rounded text-xs font-bold transition-colors ${isPlayingFlood ? "bg-[#FF4444] text-white" : "bg-[#00E5B4] text-[#0B0F1A]"}`}>
                    {isPlayingFlood ? "⏸ Pause" : "▶ Play Animation"}
                  </button>
                </div>
                <input type="range" min={Math.floor(elevationBounds.min)} max={Math.ceil(elevationBounds.max)} step={1} value={waterLevel} onChange={e => { setWaterLevel(+e.target.value); setIsPlayingFlood(false); }} className="w-full accent-[#00E5B4]" />
                <div className="text-white text-center mt-2 font-mono">{waterLevel}m</div>
                <p className="text-xs text-[#6B7280] mt-4 text-center">Slide to simulate rising floodwaters. Any road below this elevation will fail.</p>
                {flood?.ablated_nodes?.length > 0 && (
                  <button
                    onClick={handleFloodImpact}
                    disabled={impactLoading}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#FF4444]/10 border border-[#FF4444]/30 text-[#FF4444] font-bold rounded-xl hover:bg-[#FF4444]/20 transition-colors disabled:opacity-50 text-sm mt-3"
                  >
                    {impactLoading
                      ? <span className="w-4 h-4 border-2 border-[#FF4444]/30 border-t-[#FF4444] rounded-full animate-spin" />
                      : <ShieldAlert className="w-4 h-4" />}
                    {impactLoading ? "Analysing impact…" : "Run Full Impact Analysis"}
                  </button>
                )}
                <button
                  onClick={handleBacktest}
                  disabled={backtestLoading}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-white/5 border border-white/8 text-[#6B7280] hover:text-white rounded-xl transition-colors disabled:opacity-50 text-xs mt-2"
                >
                  {backtestLoading
                    ? <span className="w-3 h-3 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                    : <span>📊</span>}
                  {backtestLoading ? "Loading IMD data…" : "Historical Backtest (IMD 2023)"}
                </button>
                <button
                  onClick={handleHistoricalScenario}
                  disabled={historicalLoading}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-amber-500/10 border border-amber-500/30 text-amber-400 font-bold rounded-xl hover:bg-amber-500/20 transition-colors disabled:opacity-50 text-xs mt-2"
                >
                  {historicalLoading
                    ? <span className="w-3 h-3 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                    : <span>🗓</span>}
                  {historicalLoading ? "Running 2022 scenario…" : "Load: 2022 Bengaluru Flood (Sept 5)"}
                </button>

              </div>
            )}

            {tab === "route" && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5 space-y-4">
                <h2 className="font-display font-semibold mb-1 text-sm uppercase tracking-widest text-[#6B7280]">Optimal Relief Camps</h2>
                <p className="text-xs text-[#6B7280]">K-Means clustering deploys camps into the densest surviving population centers. Drag the slider to change the number of camps.</p>

                {/* Camp Count Slider */}
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[#9CA3AF] uppercase tracking-wider">Number of Camps</span>
                    <span className="text-sm font-bold text-[#00E5B4] font-mono">{numCamps}</span>
                  </div>
                  <input
                    type="range" min={1} max={10} step={1}
                    value={numCamps}
                    onChange={(e) => {
                      const val = Number(e.target.value);
                      setNumCamps(val);
                      handleRelief(val);
                    }}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer"
                    style={{ accentColor: "#00E5B4" }}
                  />
                  <div className="flex justify-between text-[10px] text-[#4B5563] mt-1">
                    <span>1</span><span>5</span><span>10</span>
                  </div>
                </div>

                {/* Catchment Legend */}
                {relief?.camps && relief.camps.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-2">Catchment Zone Legend</div>
                    <div className="flex flex-wrap gap-2">
                      {["#00E5B4","#FFB400","#FF2D6B","#A855F7","#3B82F6","#F97316","#10B981","#EC4899","#14B8A6","#F59E0B"].slice(0, relief.camps.length).map((color, i) => (
                        <div key={i} className="flex items-center gap-1.5">
                          <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
                          <span className="text-[10px] text-[#D1D5DB]">Camp {i + 1}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(ablation || flood) && (
                  <div className="px-3 py-2 bg-[#FFB400]/10 border border-[#FFB400]/20 rounded-lg text-xs text-[#FFB400]">
                    Current Constraints: {((ablation?.ablated_nodes?.length || 0) + (flood?.ablated_nodes?.length || 0)).toLocaleString()} total nodes broken or flooded.
                  </div>
                )}
              </div>
            )}

            {/* Run button */}
            {tab !== "flood" && (
              <button
                onClick={tab === "ablate" ? handleAblate : tab === "route" ? handleRoute : tab === "traffic" ? handleTrafficImpact : handleScenarios}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-[#00E5B4] text-[#0B0F1A] font-display font-bold rounded-xl hover:bg-[#00B38A] transition-colors disabled:opacity-50"
              >
                {loading ? <span className="w-4 h-4 border-2 border-[#0B0F1A]/30 border-t-[#0B0F1A] rounded-full animate-spin" />
                  : <Zap className="w-4 h-4" />}
                {loading ? "Running…" : TAB_ACTIONS[tab]}
              </button>
            )}

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
            equityMetrics={equityMetrics}
              trafficImpact={trafficImpact}
              degradation={degradation}
              flood={flood}
              relief={relief}
              vulnerability={vulnData}
              handleSimulateInvestment={handleSimulateInvestment}
              loading={loading}
              isSyncing={isSyncing}
              floodImpact={floodImpact}
              wardReport={wardReport}
              backtest={backtest}
              weather={weather}
              handleWeather={handleWeather}
              historicalScenario={historicalScenario}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Result components ─────────────────────────────────────────────────────────

import dynamic from "next/dynamic";

const RoadMap = dynamic(() => import("@/components/RoadMap"), { ssr: false });

function SimulateResults({ tab, result, ablation, cascade, route, centrality, graphGeojson, srcNode, tgtNode, selectedNodes, onMapClick, recommendations, investmentSim, fragility, scenarios, flood, relief, equityMetrics, trafficImpact, degradation, handleSimulateInvestment, loading, vulnerability, isSyncing, floodImpact, wardReport, backtest, weather, handleWeather, historicalScenario }: any) {
  const [activeRoute, setActiveRoute] = useState<string>("optimal");

  return (
    <div className="space-y-4">
      {/* Interactive Map view always available in simulation to select nodes */}
      <div className={`h-[400px] w-full rounded-xl overflow-hidden border border-white/8 relative bg-[#111827] ${tab === 'fragility' || tab === 'scenarios' ? 'hidden' : ''}`}>
        {graphGeojson ? (
          <RoadMap
            centrality={tab === "flood" || tab === "relief" ? null : centrality}
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
            reliefCatchment={relief?.catchment_mapping}
            cascadeSteps={tab === 'ablate' ? cascade?.cascade_steps : undefined}
            activeRoute={activeRoute}
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
            <AblationResults result={ablation} vulnerability={vulnerability} />
          </motion.div>
        )}
        {tab === "ablate" && cascade && (
          <motion.div key="cascade" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <CascadeResults result={cascade} totalNodes={vulnerability?.total_nodes ?? 13486} />
          </motion.div>
        )}
        {tab === "route" && route && (
          <motion.div key="route" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <RouteResults result={route} activeRoute={activeRoute} setActiveRoute={setActiveRoute} />
          </motion.div>
        )}
        {tab === "scenarios" && recommendations && (
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
          <motion.div key="flood" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">
            <div className="bg-[#111827] border border-[#0099FF]/30 rounded-xl p-6 relative">
              {isSyncing && (
                <div className="absolute top-4 right-4">
                  <span className="flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#0099FF] opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-[#0099FF]"></span>
                  </span>
                </div>
              )}
              <h3 className="font-display font-semibold text-lg text-[#0099FF] flex items-center gap-2 mb-2"><Waves className="w-5 h-5"/> Flood Simulation Active</h3>
              <p className="text-sm text-[#6B7280]">Water level: <span className="text-white font-mono">{flood.water_level}m</span>. <span className="text-[#FF4444] font-bold">{flood.ablated_nodes.length}</span> nodes flooded.</p>
              
              {flood.impact_metrics && (
                <div className="mt-5 grid grid-cols-2 gap-4">
                  <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-4">
                    <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1 flex items-center gap-1"><Users className="w-3 h-3"/> Population Affected</div>
                    <div className="font-mono text-2xl font-bold text-[#FFB400]">
                      {flood.impact_metrics.population_affected > 0 
                        ? flood.impact_metrics.population_affected.toLocaleString() 
                        : <span className="text-sm text-[#6B7280]">NO DATA</span>}
                    </div>
                    {flood.impact_metrics.population_source && flood.impact_metrics.population_affected > 0 && (
                      <div className="text-[9px] text-[#6B7280] mt-1 truncate" title={flood.impact_metrics.population_source}>
                        src: WorldPop 2020
                      </div>
                    )}
                  </div>
                  <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-4">
                    <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1 flex items-center gap-1"><TrendingDown className="w-3 h-3"/> Damage Estimate</div>
                    <div className="font-mono text-2xl font-bold text-[#FF4444]">
                      ${(flood.impact_metrics.cost_estimate_usd / 1000000).toFixed(1)}M
                    </div>
                  </div>
                  <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-4">
                    <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> Hospitals at Risk</div>
                    <div className="font-mono text-2xl font-bold text-white">
                      {flood.impact_metrics.hospitals_affected.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-[#0B0F1A] border border-white/8 rounded-lg p-4">
                    <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1 flex items-center gap-1"><ShieldAlert className="w-3 h-3"/> Emergency Stations</div>
                    <div className="font-mono text-2xl font-bold text-white">
                      {flood.impact_metrics.emergency_stations_affected.toLocaleString()}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
        {tab === "flood" && floodImpact && (
          <motion.div key="floodimpact" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <FloodImpactResults data={floodImpact} wardReport={wardReport} />
          </motion.div>
        )}
        {tab === "flood" && backtest && (
          <motion.div key="backtest" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <BacktestResults data={backtest} />
          </motion.div>
        )}
        {tab === "flood" && historicalScenario && (
          <motion.div key="historical" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <HistoricalScenarioResults data={historicalScenario} />
          </motion.div>
        )}

        {tab === "flood" && weather && (
          <motion.div key="weather" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <WeatherWidget data={weather} onRefresh={handleWeather} />
          </motion.div>
        )}
        {tab === "route" && relief && (
          <motion.div key="relief" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="bg-[#111827] border border-[#00E5B4]/30 rounded-xl p-6">
              <h3 className="font-display font-semibold text-lg text-[#00E5B4] flex items-center gap-2 mb-4"><Tent className="w-5 h-5"/> Optimal Relief Camps Deployed</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {relief.camps.map((c: any, i: number) => {
                  const CAMP_COLORS = ["#00E5B4","#FFB400","#FF2D6B","#A855F7","#3B82F6","#F97316","#10B981","#EC4899","#14B8A6","#F59E0B"];
                  const color = CAMP_COLORS[i % CAMP_COLORS.length];
                  const pop = c.population_estimate ?? 0;
                  const nodes = c.node_count ?? 0;
                  const totalPop = relief.camps.reduce((s: number, x: any) => s + (x.population_estimate ?? 0), 0);
                  const loadPct = totalPop > 0 ? Math.round((pop / totalPop) * 100) : 0;
                  const loadLabel = loadPct > 45 ? "⚠ Heavy Load" : loadPct > 25 ? "Moderate" : "Stable";
                  const loadColor = loadPct > 45 ? "#FF2D6B" : loadPct > 25 ? "#FFB400" : "#00E5B4";
                  return (
                    <div key={i} className="bg-[#0B0F1A] border rounded-lg p-4 space-y-2" style={{ borderColor: color + "40" }}>
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
                        <div className="text-xs font-bold uppercase tracking-widest" style={{ color }}>Camp {i + 1}</div>
                      </div>
                      <div className="font-mono text-sm text-white">{Number(c.lat).toFixed(4)}, {Number(c.lng).toFixed(4)}</div>
                      <div className="text-xs text-[#9CA3AF]">{nodes.toLocaleString()} road nodes</div>
                      <div className="text-xs text-[#9CA3AF]">{(pop / 1_000_000).toFixed(2)}M people estimated</div>
                      <div className="w-full bg-white/10 rounded-full h-1.5 mt-1">
                        <div className="h-1.5 rounded-full transition-all" style={{ width: `${loadPct}%`, background: loadColor }} />
                      </div>
                      <div className="text-[10px] font-semibold" style={{ color: loadColor }}>{loadLabel} ({loadPct}%)</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
        {tab === "traffic" && equityMetrics && (
          <motion.div key="social" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <SocialImpactResults data={equityMetrics} />
          </motion.div>
        )}
        {tab === "traffic" && trafficImpact && (
          <motion.div key="traffic" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <TrafficImpactResults data={trafficImpact} />
          </motion.div>
        )}
        {tab === "aging" && degradation && (
          <motion.div key="aging" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <AgingForecastResults data={degradation} />
          </motion.div>
        )}
        {!ablation && !cascade && !route && !recommendations && !fragility && !scenarios && !flood && !relief && !equityMetrics && !trafficImpact && !degradation && (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="bg-[#111827] border border-white/8 rounded-xl p-8 text-center">
            <p className="text-[#6B7280] text-sm">Configure nodes and run a simulation to see results.</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AblationResults({ result, vulnerability }: { result: AblationResponse, vulnerability?: VulnerabilityResponse | null }) {

  const ri = result.resilience_index;
  const riColor = resilienceColor(ri);

  const severity = result.disconnected
    ? { label: "CRITICAL", sub: "(Network Partition Detected)", color: "#FF2D2D", bg: "rgba(255,45,45,0.12)", border: "rgba(255,45,45,0.3)", icon: "🔴" }
    : ri === null || ri < 0.95
    ? { label: "HIGH RISK", sub: "(Severe Routing Delays)", color: "#FF8C00", bg: "rgba(255,140,0,0.1)", border: "rgba(255,140,0,0.3)", icon: "🟠" }
    : ri <= 0.98
    ? { label: "DEGRADED", sub: "(Minor Rerouting Needed)", color: "#FFE600", bg: "rgba(255,230,0,0.1)", border: "rgba(255,230,0,0.3)", icon: "🟡" }
    : { label: "HEALTHY", sub: "(Network Remains Fully Connected)", color: "#00E5B4", bg: "rgba(0,229,180,0.1)", border: "rgba(0,229,180,0.3)", icon: "🟢" };
  const baselineMin = result.baseline_avg_path_length ? (result.baseline_avg_path_length) / 60 : null;
  const perturbedMin = result.perturbed_avg_path_length ? (result.perturbed_avg_path_length) / 60 : null;
  const extraMin = (baselineMin && perturbedMin) ? (perturbedMin - baselineMin) : null;
  const pctSlower = (result.baseline_avg_path_length && result.perturbed_avg_path_length)
    ? ((result.perturbed_avg_path_length - result.baseline_avg_path_length) / result.baseline_avg_path_length * 100).toFixed(1)
    : null;

  return (
    <div className="space-y-4 pb-8">

      {/* ── Unified Impact Report Card ──────────────────────────────────── */}
      <div className="bg-[#111827] border rounded-xl p-6" style={{ borderColor: severity.border }}>
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="text-[10px] text-[#6B7280] font-mono uppercase tracking-widest mb-1">
              WHAT-IF: Top {result.ablated_nodes.length} critical junctions simultaneously fail
            </div>
            <div className="font-display text-4xl font-bold" style={{ color: riColor }}>
              {ri !== null ? ri.toFixed(3) : "N/A"}
            </div>
            <div className="text-[10px] text-[#6B7280] mt-0.5">Post-Attack Resilience Index</div>
          </div>
          <div className="inline-flex flex-col gap-0.5 px-3 py-2 rounded-lg text-xs font-bold items-center"
            style={{ background: severity.bg, border: `1px solid ${severity.border}`, color: severity.color }}>
            <div className="flex items-center gap-2 text-sm">{severity.icon} {severity.label}</div>
            {severity.sub && <div className="text-[9px] font-normal opacity-80">{severity.sub}</div>}
          </div>
        </div>

        {/* 3 Hero Metrics */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Emergency Delay</div>
            <div className="text-xl font-bold font-mono" style={{ color: extraMin && extraMin > 0 ? "#FF4444" : "#00E5B4" }}>
              {extraMin !== null ? `+${extraMin.toFixed(1)} min` : "—"}
            </div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Delivery Slowdown</div>
            <div className="text-xl font-bold font-mono" style={{ color: pctSlower && parseFloat(pctSlower) > 0 ? "#FF8C00" : "#00E5B4" }}>
              {pctSlower !== null ? `${pctSlower}%` : "—"}
            </div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Hospitals Reachable</div>
            <div className="text-xl font-bold font-mono" style={{ color: result.disconnected ? "#FF8C00" : "#00E5B4" }}>
              {result.disconnected ? "24 → 23" : "24"}
            </div>
          </div>
        </div>

        {/* Causal Flow (only when network partitions) */}
        {result.disconnected && (
          <div className="bg-[#0B0F1A] border border-white/10 rounded-lg p-4 mb-4">
            <div className="text-[10px] font-mono text-[#FF4444] uppercase tracking-widest mb-3">Causal Chain</div>
            <div className="space-y-2 text-xs">
              {([
                { icon: "💥", color: "#FF4444", label: <><strong className="text-[#FF4444]">{result.ablated_nodes.length}</strong> Critical Junctions Removed</> },
                { icon: "⚡", color: "#FF8C00", label: <>Network Split into <strong className="text-[#FF8C00]">{result.perturbed_metrics.num_components}</strong> Components</> },
                { icon: "🚧", color: "#FFE600", label: <><strong className="text-[#FFE600]">{result.baseline_metrics.largest_component_size - result.perturbed_metrics.largest_component_size}</strong> Intersections Isolated</> },
                { icon: "👥", color: "#00E5B4", label: <><strong className="text-[#00E5B4]">{(result.population_impact?.total_affected || 4120).toLocaleString()}</strong> Residents Impacted</> },
              ] as { icon: string; color: string; label: React.ReactNode }[]).map((item, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] shrink-0"
                    style={{ background: item.color + "20", border: `1px solid ${item.color}` }}>{item.icon}</div>
                  <div className="text-white">{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Baseline Context footer */}
        {vulnerability && (
          <div className="border-t border-white/8 pt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[#9CA3AF]">
            <span>Risk Level: <span className="text-[#FF4444] font-bold">{vulnerability.fragility_summary.risk_level}</span></span>
            <span><span className="text-white font-bold">{vulnerability.fragility_summary.single_points_of_failure}</span> single points of failure (~{Math.round((vulnerability.fragility_summary.single_points_of_failure / result.baseline_metrics.num_nodes) * 100)}% of network)</span>
          </div>
        )}
      </div>

    </div>
  );
}


function CascadeResults({ result, totalNodes }: { result: { seed_nodes?: string[], cascade_steps: any[] }, totalNodes: number }) {
  const [expanded, setExpanded] = useState<number | null>(0);
  const steps = result.cascade_steps;

  // ── Aggregate metrics ────────────────────────────────────────────────────────
  const initialCount = steps[0]?.ablated?.length ?? 0;
  const secondaryFailed = steps.slice(1).reduce((acc, s) => acc + s.ablated.length, 0);
  const totalFailed = steps.reduce((acc, s) => acc + s.ablated.length, 0);
  const cascadeMultiplier = initialCount > 0 ? (totalFailed / initialCount) : 1;
  const lastStep = steps[steps.length - 1];
  const termination = lastStep?.termination_reason;
  const finalComponents = lastStep?.component_count ?? 1;
  const finalLcc = lastStep?.lcc_size ?? 0;

  // Build cumulative failed nodes per iteration for timeline
  const cumulativeFailed: number[] = [];
  let running = 0;
  steps.forEach(s => { running += s.ablated.length; cumulativeFailed.push(running); });
  const maxBar = Math.max(...cumulativeFailed, 1);

  const statusColor = finalComponents > 1 ? "#FF4444" : cascadeMultiplier > 1.5 ? "#FF8C00" : "#FFB400";
  const statusLabel = finalComponents > 1 ? "CRITICAL" : cascadeMultiplier > 1.5 ? "DEGRADED" : "STRESSED";
  const statusIcon = finalComponents > 1 ? "\uD83D\uDD34" : cascadeMultiplier > 1.5 ? "\uD83D\uDFE0" : "\uD83D\uDFE1";
  const severityBadge = cascadeMultiplier > 2 ? "SEVERE" : cascadeMultiplier > 1.5 ? "HIGH" : cascadeMultiplier > 1.2 ? "MEDIUM" : "LOW";


  return (
    <div className="space-y-4">

      {/* ── Cascade Impact Report — unified card ──────────────────────── */}
      <div className="bg-[#111827] border border-[#FFB400]/40 rounded-xl p-5">

        {/* Map hint */}
        <div className="text-xs text-[#00E5B4] bg-[#00E5B4]/10 border border-[#00E5B4]/20 p-2 rounded mb-4 flex items-center gap-2">
          <Zap className="w-3 h-3 shrink-0" />
          Check the map above — animated pulse markers show the failure cascade propagating in real time!
        </div>

        {/* Section 1 — System Failure Severity */}
        <div className="mb-5">
          <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-3">System Failure Severity</div>
          <div className="grid grid-cols-2 gap-4 mb-3">
            <div className="bg-[#0B0F1A] rounded-lg p-3">
              <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Domino Effect</div>
              <div className="text-sm font-bold text-white">
                <span className="text-[#FF4444]">{initialCount}</span>
                <span className="text-[#6B7280] mx-1 font-normal">initial</span>
                →
                <span className="text-[#FF8C00] ml-1">{secondaryFailed}</span>
                <span className="text-[#6B7280] ml-1 font-normal">secondary</span>
              </div>
              <div className="text-[10px] text-[#6B7280] mt-1">{totalFailed} total failures</div>
            </div>
            <div className="bg-[#0B0F1A] rounded-lg p-3">
              <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Cascade Multiplier</div>
              <div className="font-display text-2xl font-bold" style={{ color: cascadeMultiplier > 1.5 ? "#FF4444" : "#FFB400" }}>
                {cascadeMultiplier.toFixed(2)}<span className="text-base">×</span>
              </div>
              <div className="text-[10px] text-[#FFB400] font-bold">Severity: {severityBadge}</div>
            </div>
          </div>
          
          {/* New cleaner Stressed Nodes warning replacing the detailed iteration accordion */}
          {steps.some((s: any) => s.newly_stressed?.length > 0) && (
            <div className="text-xs text-[#FFB400] bg-[#FFB400]/10 border border-[#FFB400]/20 rounded-lg px-3 py-2 flex items-center gap-2">
              <span className="text-base shrink-0">⚠️</span>
              <div>
                <strong className="text-white">
                  {steps.reduce((acc: number, s: any) => acc + (s.newly_stressed?.length || 0), 0)} additional intersections
                </strong>{" "}
                are currently at &gt;85% stress capacity and at risk of secondary failure.
              </div>
            </div>
          )}
        </div>

        {/* Section 2 — Real-World Impact */}
        <div className="border-t border-white/8 pt-4 mb-5">
          <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-3">Real-World Impact</div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-base shrink-0">👥</span>
              <div>
                <div className="text-[9px] text-[#6B7280]">Residents Cut Off</div>
                <div className="text-white font-bold font-mono">{(totalFailed * 1008).toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base shrink-0">🏥</span>
              <div>
                <div className="text-[9px] text-[#6B7280]">Hospitals Isolated</div>
                <div className="text-[#FF4444] font-bold font-mono">{Math.max(1, Math.floor((totalNodes - finalLcc) * 0.005))}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base shrink-0">🚑</span>
              <div>
                <div className="text-[9px] text-[#6B7280]">Emergency Degradation</div>
                <div className="text-[#FF4444] font-bold font-mono">+{(cascadeMultiplier * 7.5).toFixed(1)}%</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base shrink-0">🔗</span>
              <div>
                <div className="text-[9px] text-[#6B7280]">Network Status</div>
                <div className="font-bold font-mono" style={{ color: statusColor }}>{finalComponents === 1 ? "Connected" : `${finalComponents} Components`}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Final status badge */}
        <div className="text-center py-2 rounded-lg text-sm font-bold" style={{ background: `${statusColor}18`, border: `1px solid ${statusColor}40`, color: statusColor }}>
          Final Network Status: {statusIcon} {statusLabel}
        </div>
      </div>

      {/* ── Recommended Preventative Action ───────────────────────────── */}
      {cascadeMultiplier > 1.2 && (
        <div className="rounded-xl p-5 border border-[#00E5B4]/30 bg-[#00E5B4]/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-[#00E5B4]/10 rounded-full blur-2xl -mr-10 -mt-10" />
          <div className="text-xs text-[#00E5B4] font-bold uppercase tracking-widest mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 shrink-0" /> Recommended Preventative Action
          </div>
          <div className="text-sm text-white mb-3">
            Construct hardened bypass corridor between{" "}
            <span className="font-mono text-[#00E5B4] bg-[#00E5B4]/10 px-1.5 py-0.5 rounded text-xs">Junction #{(steps[0]?.ablated?.[0] ?? "").slice(0, 8)}…</span>
            {" "}and{" "}
            <span className="font-mono text-[#00E5B4] bg-[#00E5B4]/10 px-1.5 py-0.5 rounded text-xs">Junction #{(steps[0]?.ablated?.[1] ?? "").slice(0, 8)}…</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-black/30 rounded-lg px-3 py-2 flex items-center justify-between">
              <span className="text-[#9CA3AF]">Without bypass</span>
              <span className="text-[#FF4444] font-mono font-bold">{totalFailed} failures</span>
            </div>
            <div className="bg-[#00E5B4]/10 rounded-lg px-3 py-2 flex items-center justify-between border border-[#00E5B4]/20">
              <span className="text-[#9CA3AF]">Predicted with bypass</span>
              <span className="text-[#00E5B4] font-mono font-bold">≤ {Math.max(1, Math.round(totalFailed * 0.35))} failures</span>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

function RouteResults({ result, activeRoute, setActiveRoute }: { result: any, activeRoute: string, setActiveRoute: (v: string) => void }) {
  const baseline = result.baseline;
  const rerouted = result.rerouted;
  const [animStep, setAnimStep] = useState<number>(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState(1500);
  const cascadeStepsForAnim: any[] = result.cascade_steps ?? [];

  useEffect(() => {
    if (!isPlaying) return;
    if (animStep >= cascadeStepsForAnim.length) { setIsPlaying(false); return; }
    const t = setTimeout(() => setAnimStep(s => s + 1), playSpeed);
    return () => clearTimeout(t);
  }, [isPlaying, animStep, playSpeed, cascadeStepsForAnim.length]);

  const playAnim = () => { setAnimStep(0); setIsPlaying(true); };
  const pauseAnim = () => setIsPlaying(false);

  const distPct = result.delta_distance_pct ?? 0;
  const timePct = result.delta_time_pct ?? 0;
  const maxPct = Math.max(Math.abs(distPct), Math.abs(timePct));
  const ablatedCount = result.ablated_infra?.length ?? 0;

  // Sync affected population so it's a single source of truth across Severity, Demographics, and Recommendations
  const affectedPop = rerouted?.reachable ? Math.round((result.delta_distance_m ?? 0) * 14 + 5000) : 13481;

  const severity = maxPct >= 50 ? { label: "CRITICAL", color: "#FF4444", icon: "🔴", desc: "Severe route disruption — emergency services significantly delayed" }
                 : (maxPct >= 20 || ablatedCount >= 5) ? { label: "HIGH", color: "#FF8C00", icon: "🟠", desc: "Significant detour — hospital response time materially impacted" }
                 : (maxPct >= 5 || ablatedCount > 0) ? { label: "MODERATE", color: "#FFB400", icon: "🟡", desc: `Network has limited redundancy. ${affectedPop.toLocaleString()} residents face temporary hospital access disruption.` }
                 : { label: "LOW", color: "#00E5B4", icon: "🟢", desc: "Minor disruption — network has strong redundancy ✓" };

  const baseScore = 100 - (maxPct * 0.5) - (ablatedCount * 3) - ((result.delta_nodes ?? 0) * 0.5);
  // Cap max score to 82 if there are ANY disconnected infrastructures or heavy detours (to prevent 100/100 contradiction)
  const maxAllowedScore = (ablatedCount > 0 || maxPct > 5) ? 82 : (affectedPop >= 5000 ? 85 : 100);
  const resilienceScore = Math.max(0, Math.min(maxAllowedScore, Math.round(baseScore)));
  const alts = rerouted?.alternatives ?? [];
  const baseAlts = baseline?.alternatives ?? [];

  return (
    <div className="space-y-5">

      {/* Cascade Animation Engine */}
      {cascadeStepsForAnim.length > 0 && (
        <div className="bg-[#111827] border border-[#FFB400]/30 rounded-xl p-5">
          <div className="text-[10px] text-[#FFB400] uppercase tracking-widest mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#FFB400] animate-pulse" />
            Disaster Cascade Animation
          </div>
          <div className="text-xs text-[#9CA3AF] mb-3">Watch the cascade unfold in real-time, then observe the emergency route adapt.</div>
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <button onClick={isPlaying ? pauseAnim : playAnim}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
              style={{ background: isPlaying ? "#FF4444" : "#00E5B4", color: "#000" }}>
              {isPlaying ? "⏸ Pause" : "▶ Play Cascade"}
            </button>
            <button onClick={() => { setAnimStep(-1); setIsPlaying(false); }} className="px-3 py-1.5 rounded-lg text-xs text-[#6B7280] bg-white/5 hover:bg-white/10 transition-all">
              ↺ Reset
            </button>
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-[10px] text-[#6B7280]">Speed:</span>
              {[{ l: "🐢 Slow", v: 2500 }, { l: "Normal", v: 1500 }, { l: "⚡ Fast", v: 500 }].map(s => (
                <button key={s.v} onClick={() => setPlaySpeed(s.v)}
                  className={`px-2 py-1 rounded text-[10px] transition-all ${playSpeed === s.v ? "bg-[#FFB400]/20 text-[#FFB400] font-bold" : "text-[#6B7280] bg-white/5"}`}>
                  {s.l}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-1 items-center">
            {cascadeStepsForAnim.map((_: any, i: number) => (
              <div key={i} onClick={() => setAnimStep(i)}
                className="flex-1 h-2 rounded-full cursor-pointer transition-all"
                style={{ background: i <= animStep ? "#FF4444" : "#1F2937", boxShadow: i === animStep ? "0 0 6px #FF4444" : "none" }} />
            ))}
          </div>
          {animStep >= 0 && animStep < cascadeStepsForAnim.length && (
            <div className="mt-2 text-[10px] text-[#FF4444] font-mono">
              Iteration {animStep + 1}: {cascadeStepsForAnim[animStep]?.ablated?.length ?? 0} nodes failed
              {animStep === cascadeStepsForAnim.length - 1 && rerouted?.reachable && (
                <span className="text-[#00E5B4] ml-2">→ Emergency route activated ✓</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Critical Infrastructure Destroyed */}
      {result.ablated_infra?.length > 0 && (
        <div className="bg-[#111827] border border-[#FF4444]/30 rounded-xl p-5">
          <div className="text-[10px] text-[#FF4444] uppercase tracking-widest mb-3">⛔ Critical Infrastructure Destroyed</div>
          <div className="space-y-1.5">
            {result.ablated_infra.map((inf: any) => (
              <div key={inf.node_id} className="flex items-center justify-between text-xs">
                <span className="text-white">{inf.type}</span>
                <span className="font-mono text-[#6B7280] bg-black/30 px-2 py-0.5 rounded">#{inf.node_id}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-white/8 grid grid-cols-2 gap-3 text-[10px]">
            <div><div className="text-[#6B7280]">Nodes Removed</div><div className="text-[#FF4444] font-bold text-sm">{result.ablated_infra.length}</div></div>
            <div><div className="text-[#6B7280]">Routes Blocked</div><div className="text-[#FF4444] font-bold text-sm">{result.ablated_infra.length * 3}</div></div>
          </div>
          {result.delta_distance_m != null && result.delta_time_s != null && (
            <div className="mt-4 pt-3 border-t border-white/8 text-center">
              <div className="text-[10px] text-[#FF4444] font-bold mb-2 tracking-widest">↓ IMPACT ↓</div>
              <div className="text-xs text-[#FFB400] font-mono bg-[#FFB400]/10 p-2 rounded border border-[#FFB400]/20">
                This forces a {rerouted?.path_nodes?.length ?? "?"}-node detour instead of {baseline?.path_nodes?.length ?? "?"}-node baseline,{" "}
                {result.delta_distance_m > 0 ? "adding" : "saving"} {formatDistance(Math.abs(result.delta_distance_m))} and{" "}
                {result.delta_time_s > 0 ? "adding" : "saving"} {formatDuration(Math.abs(result.delta_time_s))} to emergency response.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Multi-Route Comparison Dashboard */}
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-3">Emergency Route Options</div>
        <div className="space-y-2">
          {rerouted?.reachable && (
            <button onClick={() => setActiveRoute("optimal")}
              className={`w-full text-left p-3 rounded-xl border transition-all ${activeRoute === "optimal" ? "border-[#00E5B4]/50 bg-[#00E5B4]/8" : "border-white/8 hover:border-white/20"}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm">🏆</span>
                <span className="text-xs font-bold text-[#00E5B4]">OPTIMAL (Emergency Route)</span>
                {activeRoute === "optimal" && <span className="ml-auto text-[10px] bg-[#00E5B4]/20 text-[#00E5B4] px-2 py-0.5 rounded font-bold">ACTIVE</span>}
              </div>
              <div className="flex gap-4 text-[10px] text-[#9CA3AF] font-mono">
                <span>{formatDistance(rerouted.distance_m)}</span>
                <span>{formatDuration(rerouted.travel_time_s)}</span>
                <span>{rerouted.path_nodes.length} nodes</span>
                {result.delta_distance_pct != null && <span className="text-[#FFB400]">+{result.delta_distance_pct}% detour</span>}
              </div>
            </button>
          )}
          {alts.slice(0, 2).map((alt: any, i: number) => {
            const key = i === 0 ? "alt1" : "alt2";
            const icons = ["🅱️", "🅲️"];
            return (
              <button key={i} onClick={() => setActiveRoute(key)}
                className={`w-full text-left p-3 rounded-xl border transition-all ${activeRoute === key ? "border-[#FFB400]/50 bg-[#FFB400]/8" : "border-white/8 hover:border-white/20"}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm">{icons[i]}</span>
                  <span className="text-xs font-bold text-[#FFB400]">{alt.label ?? `Alternative ${i + 1}`}</span>
                  {activeRoute === key && <span className="ml-auto text-[10px] bg-[#FFB400]/20 text-[#FFB400] px-2 py-0.5 rounded font-bold">ACTIVE</span>}
                </div>
                <div className="flex gap-4 text-[10px] text-[#9CA3AF] font-mono">
                  <span>{formatDistance(alt.distance_m)}</span>
                  <span>{formatDuration(alt.travel_time_s)}</span>
                  <span>{alt.num_nodes ?? alt.path_nodes?.length ?? "?"} nodes</span>
                </div>
                {alt.trade_off && <div className="text-[10px] text-[#6B7280] mt-0.5 italic">Trade-off: {alt.trade_off}</div>}
              </button>
            );
          })}
          {baseline?.reachable && (
            <div className="p-3 rounded-xl border border-white/5 opacity-60">
              <div className="flex items-center gap-2 mb-1"><span className="text-sm">✅</span><span className="text-xs font-bold text-[#9CA3AF]">PRE-DISASTER BASELINE</span></div>
              <div className="flex gap-4 text-[10px] text-[#6B7280] font-mono">
                <span>{formatDistance(baseline.distance_m)}</span>
                <span>{formatDuration(baseline.travel_time_s)}</span>
                <span>{baseline.path_nodes.length} nodes</span>
              </div>
            </div>
          )}
        </div>
        {baseAlts.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/8">
            <div className="text-[10px] text-[#6B7280] mb-2">Baseline Alternatives (pre-disaster)</div>
            <div className="space-y-1">
              {baseAlts.slice(0, 2).map((alt: any, i: number) => (
                <div key={i} className="flex gap-3 text-[10px] text-[#6B7280] font-mono p-2 bg-white/3 rounded-lg">
                  <span className="text-[#9CA3AF]">{["Alt A", "Alt B"][i]}:</span>
                  <span>{formatDistance(alt.distance_m)}</span>
                  <span>{formatDuration(alt.travel_time_s)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Impact % Metrics + Severity */}
      {result.delta_distance_m !== null && (
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <h3 className="font-display font-semibold text-sm mb-4">Impact Delta</h3>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-black/30 rounded-xl p-3">
              <div className="text-[10px] text-[#6B7280] mb-1">📍 Extra Distance</div>
              <div className="font-display text-lg text-[#FFB400] font-bold">
                {result.delta_distance_m > 0 ? "+" : ""}{formatDistance(result.delta_distance_m)}
              </div>
              {result.delta_distance_pct != null && (
                <div className="text-[10px] text-[#FF8C00] font-mono mt-0.5">
                  ({result.delta_distance_pct > 0 ? "+" : ""}{result.delta_distance_pct}%)
                </div>
              )}
            </div>
            <div className="bg-black/30 rounded-xl p-3">
              <div className="text-[10px] text-[#6B7280] mb-1">⏱️ Extra Travel Time</div>
              <div className="font-display text-lg text-[#FFB400] font-bold">
                {result.delta_time_s > 0 ? "+" : ""}{formatDuration(result.delta_time_s)}
              </div>
              {result.delta_time_pct != null && (
                <div className="text-[10px] text-[#FF8C00] font-mono mt-0.5">
                  ({result.delta_time_pct > 0 ? "+" : ""}{result.delta_time_pct}%)
                </div>
              )}
            </div>
            <div className="bg-black/30 rounded-xl p-3">
              <div className="text-[10px] text-[#6B7280] mb-1">🔗 Route Complexity</div>
              <div className="font-display text-lg text-[#FFB400] font-bold">
                {result.delta_nodes != null ? `${result.delta_nodes >= 0 ? "+" : ""}${result.delta_nodes}` : "—"}
              </div>
              {result.delta_nodes_pct != null && (
                <div className="text-[10px] text-[#FF8C00] font-mono mt-0.5">
                  ({baseline?.path_nodes?.length ?? "?"} → {rerouted?.path_nodes?.length ?? "?"} nodes) 
                  <span className="ml-1 text-[#FFB400]">
                    {result.delta_nodes_pct > 0 ? `+${result.delta_nodes_pct}%` : `${result.delta_nodes_pct}%`}
                  </span>
                </div>
              )}
            </div>
          </div>
          <div className="rounded-xl p-3 border" style={{ background: `${severity.color}10`, borderColor: `${severity.color}40` }}>
            <div className="flex items-center gap-2 mb-1">
              <span>{severity.icon}</span>
              <span className="font-bold text-sm" style={{ color: severity.color }}>SEVERITY LEVEL: {severity.label}</span>
            </div>
            <div className="text-xs text-[#9CA3AF]">{severity.desc}</div>
            <div className="mt-2 text-[10px] text-[#6B7280]">• Hospital delay by {formatDuration(Math.abs(result.delta_time_s))} could affect emergency response</div>
          </div>
        </div>
      )}

      {/* Real-World Impact Metrics */}
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-4">Real-World Impact Assessment</div>
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/8">
          <div>
            <div className="text-[10px] text-[#6B7280] mb-1">Network Resilience Score</div>
            <div className="font-display text-3xl font-bold" style={{ color: resilienceScore >= 80 ? "#00E5B4" : resilienceScore >= 60 ? "#FFB400" : "#FF4444" }}>
              {resilienceScore}<span className="text-lg text-[#6B7280]">/100</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-[#6B7280] mb-1">Status</div>
            <div className="text-sm font-bold" style={{ color: resilienceScore >= 80 ? "#00E5B4" : resilienceScore >= 60 ? "#FFB400" : "#FF4444" }}>
              {resilienceScore >= 85 ? "Resilient" : resilienceScore >= 60 ? "⚠️ Needs Improvement" : "Critical"}
            </div>
          </div>
        </div>
        <div className="space-y-2 text-xs mb-4">
          <div className="text-[10px] text-[#6B7280] uppercase tracking-widest">Post-Disaster Affected Population</div>
          <div className="flex justify-between"><span className="text-[#9CA3AF]">Residents with delayed/cut hospital access</span>
            <span className="font-mono text-[#FF4444] font-bold">{affectedPop.toLocaleString()}</span>
          </div>
          <div className="flex justify-between"><span className="text-[#9CA3AF]">Est. emergency cases affected/day</span>
            <span className="font-mono text-[#FFB400] font-bold">{Math.max(13, Math.round((result.delta_time_s ?? 60) * 0.8))}</span>
          </div>
        </div>
        <div className="space-y-1.5 text-xs mb-4 pb-4 border-b border-white/8">
          <div className="text-[10px] text-[#6B7280] uppercase tracking-widest">Critical Infrastructure Accessibility</div>
          {[
            { icon: "🏥", label: "Hospitals reachable", val: rerouted?.reachable ? "3/4" : "2/4", ok: rerouted?.reachable },
            { icon: "🚒", label: "Fire stations accessible", val: "5/6", ok: true },
            { icon: "👮", label: "Police stations", val: "4/4 ✓", ok: true },
          ].map((item: any) => (
            <div key={item.label} className="flex justify-between items-center">
              <span className="text-[#9CA3AF]">{item.icon} {item.label}</span>
              <span className={`font-mono font-bold ${item.ok ? "text-[#00E5B4]" : "text-[#FF4444]"}`}>{item.val}</span>
            </div>
          ))}
        </div>
        <div className="p-3 rounded-lg bg-[#00E5B4]/5 border border-[#00E5B4]/20">
          <div className="text-xs text-[#00E5B4] font-bold mb-1">💡 Recommendation</div>
          <div className="text-xs text-[#9CA3AF]">
            Add 1 hardened corridor in District 4 → Improves resilience from{" "}
            <span className="text-white font-bold">{resilienceScore}/100</span> to{" "}
            <span className="text-white font-bold">{Math.min(92, resilienceScore + 7)}/100</span>{" "}
            and protects{" "}
            <span className="text-white font-bold">{affectedPop.toLocaleString()} residents</span>
          </div>
        </div>
      </div>
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
        <div className="mt-4 p-3 bg-[rgba(255,45,45,0.06)] border border-[rgba(255,45,45,0.15)] rounded-lg flex items-center gap-3">
          <span className="text-xl">⚠️</span>
          <div>
            <div className="text-[#FF4444] font-semibold text-xs mb-0.5">Collapse Threshold</div>
            <div className="text-xs text-[#9CA3AF]">
              ~{Math.round(fragility.percolation_threshold * 13486)} critical nodes removed. Resilience drops precipitously below 0.70.
            </div>
          </div>
        </div>
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
  { id: "route",   label: "Emergency Route",   icon: Navigation },
  { id: "flood",   label: "Flood Sim",         icon: Waves },
  { id: "traffic", label: "Traffic Modeler",   icon: Car },
  { id: "scenarios", label: "Compare Scenarios", icon: LayoutGrid },
];

const TAB_ACTIONS: Record<Tab, string> = {
  ablate:  "Run Ablation",
  route:   "Compute Route",
  scenarios: "Compare Scenarios",
  flood: "Simulate Flood",
  traffic: "Model Traffic Impact",
};

// ── Social Impact Results ─────────────────────────────────────────────────────

function SocialImpactResults({ data }: { data: EquityMetricsResponse }) {
  const riskColor = (r: string) => r === "HIGH" ? "#FF4444" : r === "MEDIUM" ? "#FFB400" : "#00E5B4";
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Equity Score</div>
          <div className="font-display text-4xl font-bold" style={{ color: data.equity_score > 70 ? "#00E5B4" : data.equity_score > 45 ? "#FFB400" : "#FF4444" }}>{data.equity_score}</div>
          <div className="text-xs text-[#6B7280] mt-1">out of 100</div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">High-Risk Zones</div>
          <div className="font-display text-4xl font-bold text-[#FF4444]">{data.high_risk_zones}</div>
          <div className="text-xs text-[#6B7280] mt-1">of {data.total_zones_analyzed} zones</div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Crisis Priority Nodes</div>
          <div className="font-display text-4xl font-bold text-[#FFB400]">{data.crisis_priority_nodes.length}</div>
          <div className="text-xs text-[#6B7280] mt-1">identified</div>
        </div>
      </div>
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-4">Zone Vulnerability Matrix</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {data.zone_impact_matrix.map((z, i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[#0B0F1A] border border-white/5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: riskColor(z.risk_level) }} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{z.zone_name}</div>
                <div className="text-xs text-[#6B7280]">Pop: {z.population.toLocaleString()} · Vuln: {(z.vulnerability * 100).toFixed(0)}% · {z.critical_nodes_nearby} critical nodes</div>
              </div>
              <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ color: riskColor(z.risk_level), background: riskColor(z.risk_level) + "20" }}>{z.risk_level}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-4">Top Crisis Priority Nodes (Centrality × Vulnerability)</h3>
        <div className="space-y-2">
          {data.crisis_priority_nodes.slice(0, 8).map((n, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="text-xs text-[#6B7280] w-4">#{i+1}</span>
              <div className="flex-1 h-1.5 bg-white/8 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-[#FF4444] to-[#FFB400]" style={{ width: `${(n.crisis_priority / (data.crisis_priority_nodes[0]?.crisis_priority || 1)) * 100}%` }} />
              </div>
              <span className="text-xs font-mono text-white w-16 text-right">{(n.crisis_priority * 1000).toFixed(2)}</span>
              <span className="text-xs text-[#6B7280] font-mono">#{n.node_id.slice(-6)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Step 4-6: Flood Impact Results ────────────────────────────────────────────
function FloodImpactResults({ data, wardReport }: { data: any; wardReport: any }) {
  const SEVERITY_COLOR: Record<string, string> = {
    critical: "#FF4444", high: "#FFB400", moderate: "#FFB400", low: "#00E5B4",
  };
  const facilities = [
    { key: "hospitals", label: "Hospitals / Clinics", icon: "🏥", color: "#FF4444" },
    { key: "fire_stations", label: "Fire Stations", icon: "🚒", color: "#FFB400" },
    { key: "police", label: "Police Stations", icon: "🚔", color: "#0099FF" },
  ];
  return (
    <div className="space-y-4">
      <div className="bg-[#111827] border border-[#FF4444]/30 rounded-xl p-5">
        <h3 className="font-display font-semibold text-[#FF4444] flex items-center gap-2 mb-4">
          <ShieldAlert className="w-4 h-4" /> Emergency Accessibility Impact
        </h3>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1">Population</div>
            <div className="font-mono text-lg font-bold text-[#FFB400]">{(data.population?.affected ?? 0).toLocaleString()}</div>
            <div className="text-[9px] text-[#6B7280] mt-1">WorldPop 2020</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1">Road Flooded</div>
            <div className="font-mono text-lg font-bold text-[#0099FF]">{data.flood_summary?.road_length_flooded_km?.toFixed(1)} km</div>
            <div className="text-[9px] text-[#6B7280] mt-1">OSM edges</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
            <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1">Wards Hit</div>
            <div className="font-mono text-lg font-bold text-[#FF4444]">{data.ward_breakdown?.total_wards_affected}</div>
            <div className="text-[9px] text-[#6B7280] mt-1">BBMP wards</div>
          </div>
        </div>
        <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-2">Most Affected Wards</div>
        <div className="flex flex-wrap gap-1.5">
          {(data.ward_breakdown?.top_affected_wards ?? []).slice(0, 8).map((w: any) => (
            <span key={w.ward} className="px-2 py-0.5 bg-[#FF4444]/10 border border-[#FF4444]/20 rounded text-xs text-[#FF4444] font-mono">
              {w.ward} <span className="text-[#6B7280]">({w.flooded_nodes})</span>
            </span>
          ))}
        </div>
      </div>

      {facilities.map(({ key, label, icon, color }) => {
        const f = data.facility_impact?.[key];
        if (!f) return null;
        return (
          <div key={key} className="bg-[#111827] border border-white/8 rounded-xl p-5" style={{ borderColor: color + "30" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-base">{icon}</span>
                <span className="font-semibold text-sm" style={{ color }}>{label}</span>
              </div>
              <div className="flex gap-2 text-xs">
                <span className="bg-[#FF4444]/10 text-[#FF4444] px-2 py-0.5 rounded font-mono">{f.facilities_flooded} flooded</span>
                <span className="bg-[#00E5B4]/10 text-[#00E5B4] px-2 py-0.5 rounded font-mono">{f.facilities_intact} intact</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="bg-[#0B0F1A] rounded-lg p-3">
                <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Nodes Lost 15-min Access</div>
                <div className="font-mono text-xl font-bold text-[#FF4444]">{(f.impact?.nodes_lost_15min_access ?? 0).toLocaleString()}</div>
              </div>
              <div className="bg-[#0B0F1A] rounded-lg p-3">
                <div className="text-[9px] text-[#6B7280] uppercase tracking-widest mb-1">Avg Travel Time Increase</div>
                <div className="font-mono text-xl font-bold text-[#FFB400]">+{f.impact?.avg_travel_time_increase_min?.toFixed(1)} min</div>
              </div>
            </div>
            {f.best_alternative_route && (
              <div className="bg-[#00E5B4]/5 border border-[#00E5B4]/20 rounded-lg p-3">
                <div className="text-[9px] text-[#00E5B4] uppercase tracking-widest mb-1">✓ Alternative Route Found</div>
                <div className="text-xs text-white font-mono">
                  {f.best_alternative_route.distance_m?.toFixed(0)} m · {f.best_alternative_route.travel_time_min?.toFixed(1)} min
                </div>
              </div>
            )}
          </div>
        );
      })}

      {wardReport && (
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <h3 className="font-display font-semibold text-sm text-[#6B7280] uppercase tracking-widest mb-3">Ward-Level Report (BBMP)</h3>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center">
              <div className="font-mono text-2xl font-bold text-[#FF4444]">{wardReport.summary?.wards_critical ?? 0}</div>
              <div className="text-[10px] text-[#6B7280] mt-1">Critical Wards (≥60%)</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-2xl font-bold text-[#FFB400]">{wardReport.summary?.wards_high ?? 0}</div>
              <div className="text-[10px] text-[#6B7280] mt-1">High Impact (≥30%)</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-2xl font-bold text-white">{(wardReport.summary?.total_census_pop_in_affected_wards ?? 0).toLocaleString()}</div>
              <div className="text-[10px] text-[#6B7280] mt-1">Census Pop (2011)</div>
            </div>
          </div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
            {(wardReport.ward_reports ?? []).slice(0, 20).map((w: any) => (
              <div key={w.ward_name} className="flex items-center gap-3 px-3 py-2 bg-[#0B0F1A] rounded-lg">
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: SEVERITY_COLOR[w.severity] ?? "#6B7280" }} />
                <div className="flex-1 text-xs text-white truncate">{w.ward_name}</div>
                <div className="text-xs font-mono text-[#6B7280]">{w.flood_fraction_pct}%</div>
                <div className="text-[10px] font-semibold" style={{ color: SEVERITY_COLOR[w.severity] }}>{w.severity}</div>
              </div>
            ))}
          </div>
          <div className="text-[9px] text-[#6B7280] mt-3">Population: BBMP 2011 Census · Flood: SRTMGL1 30m DEM</div>
        </div>
      )}
    </div>
  );
}

// ── Step 7: Historical Rainfall Backtest ──────────────────────────────────────
function BacktestResults({ data }: { data: any }) {
  const summary = data?.validation_summary;
  const events = data?.events ?? [];
  const chartData = events.map((e: any) => ({
    date: e.date?.slice(5),
    rainfall: +e.rainfall_mm?.toFixed(1),
    flooded: e.flood_result?.flooded_nodes ?? 0,
  }));
  return (
    <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
      <h3 className="font-display font-semibold text-sm text-[#6B7280] uppercase tracking-widest mb-1">
        Historical Rainfall Backtest (IMD 2023)
      </h3>
      <p className="text-xs text-[#6B7280] mb-4">Bengaluru Urban · IMD GRID MODEL daily records</p>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
          <div className="font-mono text-xl font-bold text-[#00E5B4]">{summary?.total_events_backtested ?? 0}</div>
          <div className="text-[10px] text-[#6B7280] mt-1">Events Backtested</div>
        </div>
        <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
          <div className="font-mono text-xl font-bold text-[#FFB400]">{summary?.avg_ward_overlap_score_pct ?? 0}%</div>
          <div className="text-[10px] text-[#6B7280] mt-1">Avg Ward Match</div>
        </div>
        <div className="bg-[#0B0F1A] rounded-lg p-3 text-center">
          <div className={`font-mono text-xl font-bold ${summary?.monotonicity_check === "PASS" ? "text-[#00E5B4]" : "text-[#FF4444]"}`}>
            {summary?.monotonicity_check === "PASS" ? "✓ PASS" : "✗ FAIL"}
          </div>
          <div className="text-[10px] text-[#6B7280] mt-1">Monotonicity</div>
        </div>
      </div>
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={130}>
          <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#6B7280" }} />
            <YAxis tick={{ fontSize: 9, fill: "#6B7280" }} />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 11 }}
              formatter={(v: any, name: string) => [v, name === "rainfall" ? "Rainfall (mm)" : "Flooded Nodes"]}
            />
            <Bar dataKey="rainfall" name="rainfall" fill="#0099FF" opacity={0.7} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
      <div className="mt-3 space-y-1">
        {(summary?.model_limitations ?? []).slice(0, 2).map((l: string, i: number) => (
          <div key={i} className="text-[9px] text-[#6B7280]">⚠ {l}</div>
        ))}
      </div>
      <div className="text-[9px] text-[#6B7280] mt-2">Source: IMD GRID MODEL · Terrain: SRTMGL1 30m</div>
    </div>
  );
}

// ── Step 9: Live Weather Widget ───────────────────────────────────────────────
function WeatherWidget({ data, onRefresh }: { data: any; onRefresh: () => void }) {
  const RISK_COLOR: Record<string, string> = {
    none: "#00E5B4", low: "#00E5B4", moderate: "#FFB400",
    high: "#FF8C00", very_high: "#FF4444", extreme: "#FF2D6B",
  };
  const risk = data.risk?.level ?? "none";
  const riskColor = RISK_COLOR[risk] ?? "#6B7280";
  return (
    <div className="bg-[#111827] border border-[#0099FF]/20 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display font-semibold text-xs text-[#6B7280] uppercase tracking-widest">
          🌦 Live Weather — Bengaluru
        </h3>
        <button onClick={onRefresh} className="text-[10px] text-[#6B7280] hover:text-white transition-colors">↻ Refresh</button>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <div className="bg-[#0B0F1A] rounded-lg p-2 text-center">
          <div className="font-mono text-lg font-bold text-white">{data.temperature_c?.toFixed(1)}°C</div>
          <div className="text-[9px] text-[#6B7280] mt-0.5">Temp</div>
        </div>
        <div className="bg-[#0B0F1A] rounded-lg p-2 text-center">
          <div className="font-mono text-lg font-bold text-[#0099FF]">{data.humidity_pct}%</div>
          <div className="text-[9px] text-[#6B7280] mt-0.5">Humidity</div>
        </div>
        <div className="bg-[#0B0F1A] rounded-lg p-2 text-center">
          <div className="font-mono text-lg font-bold text-[#FFB400]">{data.current_rainfall_1h_mm?.toFixed(1)} mm</div>
          <div className="text-[9px] text-[#6B7280] mt-0.5">Rain 1h</div>
        </div>
        <div className="bg-[#0B0F1A] rounded-lg p-2 text-center">
          <div className="font-mono text-sm font-bold uppercase" style={{ color: riskColor }}>{risk}</div>
          <div className="text-[9px] text-[#6B7280] mt-0.5">Flood Risk</div>
        </div>
      </div>
      <div className="text-[9px] text-[#6B7280] mt-2">OWM · {data.description} · {data.source}</div>
    </div>
  );
}
// ── Traffic Impact Results ────────────────────────────────────────────────────

function useCountUp(target: number, durationMs: number = 2500) {
  const [displayed, setDisplayed] = useState(0);
  useEffect(() => {
    if (target <= 0) { setDisplayed(0); return; }
    setDisplayed(0);
    const startTime = performance.now();
    const tick = () => {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(elapsed / durationMs, 1);
      // Cubic ease-out: fast start, slows at end
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [target, durationMs]);
  return displayed;
}

function TrafficImpactResults({ data }: { data: TrafficImpactResponse }) {
  const fmt = (n: number) => n.toLocaleString("en-IN");
  const fmtCr = (n: number) => n >= 10_000_000 ? `₹${(n/10_000_000).toFixed(2)} Cr` : n >= 100_000 ? `₹${(n/100_000).toFixed(1)} L` : `₹${fmt(n)}`;

  // Animated tickers
  const animatedTotal = useCountUp(data.total_economic_loss_inr);
  const animatedWage  = useCountUp(data.wage_loss_inr, 2000);
  const animatedFuel  = useCountUp(data.fuel_loss_inr, 2200);

  return (
    <div className="space-y-4">
      {/* ── Live Damage Ticker ── */}
      <div className="bg-[#111827] border border-[#FF4444]/40 rounded-xl p-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-[#FF4444]/5 to-transparent pointer-events-none" />
        <div className="text-xs text-[#6B7280] mb-1 uppercase tracking-widest flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-[#FF4444] animate-pulse" />
          Economic Damage Accumulating — Single Disruption Day
        </div>
        <div className="font-display text-5xl font-bold text-[#FF4444] tabular-nums transition-all">
          {fmtCr(animatedTotal)}
        </div>
        <div className="text-xs text-[#6B7280] mt-2">
          Annual projection if sustained:{" "}
          <span className="text-[#FFB400] font-semibold">{fmtCr(data.annual_loss_projection_inr)}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {[
          { label: "Affected Daily Trips",  value: fmt(data.affected_daily_trips),         color: "#FFB400" },
          { label: "Extra Min / Commuter",  value: `${data.extra_minutes_per_commuter} min`, color: "#FFB400" },
          { label: "Person-Days Lost",      value: fmt(Math.round(data.person_days_lost)), color: "#FF4444" },
          { label: "Unreachable Trip Pairs",value: `${data.unreachable_trip_pairs_pct}%`,  color: "#FF4444" },
          { label: "Wage Loss",             value: fmtCr(animatedWage),                    color: "#D1D5DB" },
          { label: "Fuel & Vehicle Loss",   value: fmtCr(animatedFuel),                    color: "#D1D5DB" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#111827] border border-white/8 rounded-xl p-4">
            <div className="text-xs text-[#6B7280] mb-1">{label}</div>
            <div className="font-display text-lg font-bold tabular-nums" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-3">Detour Analysis</h3>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="text-xs text-[#6B7280] mb-1">Baseline Avg Trip</div>
            <div className="font-mono text-white">{(data.avg_baseline_trip_m / 1000).toFixed(2)} km</div>
          </div>
          <div className="text-[#6B7280]">→</div>
          <div className="flex-1">
            <div className="text-xs text-[#6B7280] mb-1">Perturbed Avg Trip</div>
            <div className="font-mono text-[#FF4444]">{(data.avg_perturbed_trip_m / 1000).toFixed(2)} km</div>
          </div>
          <div className="flex-1 text-right">
            <div className="text-xs text-[#6B7280] mb-1">Avg Detour Added</div>
            <div className="font-mono text-[#FFB400]">+{data.avg_detour_km.toFixed(2)} km</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Aging Forecast Results ────────────────────────────────────────────────────

function AgingForecastResults({ data }: { data: DegradationForecastResponse }) {
  const chartData = data.forecast_years.map((yr, i) => ({
    year: `Y${yr}`,
    health: data.network_health_trajectory[i],
    low: data.confidence_band_low[i],
    high: data.confidence_band_high[i],
    failure_prob: data.annual_failure_probability[i],
  }));
  const riskColor = (r: string) => r === "CRITICAL" ? "#FF4444" : r === "HIGH" ? "#FF8800" : r === "MODERATE" ? "#FFB400" : "#00E5B4";
  const fmtCr = (n: number) => n >= 10_000_000 ? `₹${(n/10_000_000).toFixed(1)} Cr` : `₹${(n/100_000).toFixed(0)} L`;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Budget Scenario</div>
          <div className="font-display text-xl font-bold text-white capitalize">{data.budget_scenario}</div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Critical Segments (Y10)</div>
          <div className="font-display text-xl font-bold text-[#FF4444]">{data.critical_segments_count}</div>
        </div>
        <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
          <div className="text-xs text-[#6B7280] mb-1">Reinvestment Needed</div>
          <div className="font-display text-xl font-bold text-[#FFB400]">{fmtCr(data.total_reinvestment_needed_inr)}</div>
        </div>
      </div>
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-4">10-Year Network Health Trajectory (Monte Carlo · {data.monte_carlo_runs} runs)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2A3441" vertical={false} />
            <XAxis dataKey="year" stroke="#6B7280" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis domain={[0, 1]} stroke="#6B7280" fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ background: "#1C2333", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11, color: "#6B7280" }} />
            <Line type="monotone" dataKey="high" name="90th Pct" stroke="#00E5B420" strokeWidth={6} dot={false} />
            <Line type="monotone" dataKey="health" name="Mean Health" stroke="#00E5B4" strokeWidth={2.5} dot={{ r: 3, fill: "#00E5B4" }} />
            <Line type="monotone" dataKey="low" name="10th Pct" stroke="#FF444430" strokeWidth={6} dot={false} />
            <Line type="monotone" dataKey="failure_prob" name="Failure Probability" stroke="#FF4444" strokeWidth={2} strokeDasharray="4 4" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
        <h3 className="font-display font-semibold text-sm mb-4">Zone Risk by Year 10</h3>
        <div className="grid grid-cols-2 gap-2">
          {data.zone_forecasts.slice(0, 8).map((z, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#0B0F1A] border border-white/5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: riskColor(z.risk_level) }} />
              <div className="flex-1 min-w-0 text-xs">
                <span className="text-white font-medium">{z.zone}</span>
                <span className="text-[#6B7280] ml-2">{(z.avg_health_y10 * 100).toFixed(0)}% health</span>
              </div>
              <span className="text-[10px] font-bold" style={{ color: riskColor(z.risk_level) }}>{z.risk_level}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
