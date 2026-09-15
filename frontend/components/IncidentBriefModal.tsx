"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ShieldAlert, Zap, AlertTriangle, Crosshair, Navigation, Lightbulb, Map, Hospital, Anchor, TrendingUp, Info } from "lucide-react";
import { generateBriefNarrative } from "@/lib/api";

interface IncidentBriefProps {
  onClose: () => void;
  flood: any;
  floodImpact: any;
  wardReport: any;
}

export function IncidentBriefModal({ onClose, flood, floodImpact, wardReport }: IncidentBriefProps) {
  const [narrative, setNarrative] = useState<string>("Generating operational narrative from structured verified data...");

  useEffect(() => {
    // Generate AI Narrative
    let mounted = true;
    if (flood && floodImpact && wardReport) {
      generateBriefNarrative(flood, floodImpact, wardReport)
        .then(res => {
          if (mounted) setNarrative(res.narrative);
        })
        .catch(err => {
          if (mounted) setNarrative("AI narrative generation failed. Please refer to structured data.");
        });
    } else {
      setNarrative("Insufficient data to generate operational narrative.");
    }
    return () => { mounted = false; };
  }, [flood, floodImpact, wardReport]);

  const popAffected = floodImpact?.population?.affected;
  const wardsHit = floodImpact?.ward_breakdown?.total_wards_affected;
  const criticalWards = wardReport?.critical_wards_count || 0;
  
  // Calculate recommended actions based ONLY on derived data
  const actions: { icon: any; text: string; urgent: boolean }[] = [];
  
  const hospImpact = floodImpact?.facility_impact?.hospitals?.impact;
  const fireAltRoute = floodImpact?.facility_impact?.fire_stations?.best_alternative_route;

  if (criticalWards > 0) {
    actions.push({ icon: Map, text: `[System Heuristic] Top ${criticalWards} wards exceed 60% infrastructural inundation. Consider prioritizing Search and Rescue (SAR) deployments to these boundaries.`, urgent: true });
  }
  
  if (hospImpact && hospImpact.facilities_disconnected > 0) {
    actions.push({ icon: Hospital, text: `[Computed] ${hospImpact.facilities_disconnected} hospitals are physically isolated from the surviving road graph. Airlift/Medevac protocols may be required.`, urgent: true });
  } else if (hospImpact && hospImpact.avg_travel_time_increase_min > 15) {
    actions.push({ icon: TrendingUp, text: `[System Heuristic] Citywide hospital travel times increased by >15 minutes. Consider pre-positioning BLS/ALS ambulances in disconnected zones.`, urgent: true });
  }

  if (fireAltRoute) {
    actions.push({ icon: Navigation, text: `[Computed] Primary fire station routes severed. An alternative ${(fireAltRoute.distance_m / 1000).toFixed(1)}km bypass route is active; relay coordinates to dispatch.`, urgent: false });
  }

  if (actions.length === 0) {
    actions.push({ icon: Info, text: "Insufficient computed severity for automated recommendations.", urgent: false });
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-4xl max-h-[90vh] bg-[#0B0F1A] border border-[#00E5B4]/30 rounded-2xl shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-[#111827]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#00E5B4]/20 flex items-center justify-center border border-[#00E5B4]/50">
              <ShieldAlert className="w-5 h-5 text-[#00E5B4]" />
            </div>
            <div>
              <h2 className="text-xl font-display font-bold text-white tracking-wide uppercase">Incident Commander Brief</h2>
              <div className="text-xs text-[#00E5B4] font-mono mt-0.5">PRIORITY 3 ?" AUTOMATED SITUATION REPORT</div>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-[#6B7280] hover:text-white transition-colors rounded-lg hover:bg-white/5">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-white/10">
          
          {/* Situation Summary & Narrative */}
          <section className="bg-[#111827] border border-white/5 rounded-xl p-5">
            <h3 className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-3 flex items-center gap-1.5 font-bold">
              <Crosshair className="w-3 h-3 text-[#FFB400]" /> AI Situation Narrative (Generated from verified telemetry)
            </h3>
            <p className="text-sm leading-relaxed text-[#D1D5DB] font-medium">
              {narrative}
            </p>
          </section>

          {/* Key Metrics Dashboard */}
          <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#111827] border border-[#FF4444]/20 rounded-xl p-4">
              <div className="text-[10px] text-[#FF4444] uppercase tracking-widest mb-1">Pop Physically Submerged</div>
              <div className="font-mono text-2xl font-bold text-white">{popAffected !== undefined ? popAffected.toLocaleString() : "N/A"}</div>
              <div className="text-[9px] text-[#6B7280] mt-1">Derived from WorldPop Raster</div>
            </div>
            <div className="bg-[#111827] border border-[#FFB400]/20 rounded-xl p-4">
              <div className="text-[10px] text-[#FFB400] uppercase tracking-widest mb-1">Total Wards Degraded</div>
              <div className="font-mono text-2xl font-bold text-white">{wardsHit !== undefined ? wardsHit : "N/A"}</div>
              <div className="text-[9px] text-[#6B7280] mt-1">BBMP Boundaries</div>
            </div>
            <div className="bg-[#111827] border border-white/10 rounded-xl p-4">
              <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1">Road Infrastructure Lost</div>
              <div className="font-mono text-2xl font-bold text-[#0099FF]">{floodImpact?.flood_summary?.road_length_flooded_km !== undefined ? `${floodImpact.flood_summary.road_length_flooded_km.toFixed(1)} km` : "N/A"}</div>
              <div className="text-[9px] text-[#6B7280] mt-1">OSMnx Geometric Sum</div>
            </div>
            <div className="bg-[#111827] border border-white/10 rounded-xl p-4">
              <div className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-1">Derived Flood Threshold</div>
              <div className="font-mono text-2xl font-bold text-white">{flood?.water_level !== undefined ? `${flood.water_level}m` : "N/A"}</div>
              <div className="text-[9px] text-[#6B7280] mt-1">NASA SRTMGL1 DEM</div>
            </div>
          </section>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Priority Wards */}
            <section className="bg-[#111827] border border-white/5 rounded-xl p-5">
              <h3 className="text-[10px] text-[#6B7280] uppercase tracking-widest mb-4 flex items-center gap-1.5 font-bold">
                <AlertTriangle className="w-3 h-3 text-[#FF4444]" /> Critical Priority Wards (&gt;60% Submersion)
              </h3>
              {criticalWards > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto pr-2">
                  {(wardReport?.ward_forecasts || []).filter((w: any) => w.status === 'critical').map((w: any) => (
                    <div key={w.ward_name} className="flex justify-between items-center bg-black/40 p-2.5 rounded border border-[#FF4444]/10">
                      <span className="text-sm text-white font-medium">{w.ward_name}</span>
                      <span className="text-xs text-[#FF4444] font-mono bg-[#FF4444]/10 px-2 py-0.5 rounded">{w.flood_fraction_pct !== undefined ? `${w.flood_fraction_pct}% Flooded` : "Critical"}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-[#6B7280]">No critical wards identified in this scenario.</div>
              )}
            </section>

            {/* Recommended Actions */}
            <section className="bg-[#111827] border border-[#00E5B4]/20 rounded-xl p-5">
              <h3 className="text-[10px] text-[#00E5B4] uppercase tracking-widest mb-4 flex items-center gap-1.5 font-bold">
                <Lightbulb className="w-3 h-3" /> Algorithmically Derived Actions
              </h3>
              <div className="space-y-3">
                {actions.map((act, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-3 bg-black/40 rounded-lg border border-white/5">
                    <act.icon className={`w-4 h-4 mt-0.5 ${act.urgent ? 'text-[#FF4444]' : 'text-[#00E5B4]'}`} />
                    <div className={`text-sm ${act.urgent ? 'text-white' : 'text-[#D1D5DB]'}`}>{act.text}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {/* Data Provenance Accordion */}
          <details className="group bg-[#111827] border border-white/5 rounded-xl [&_summary::-webkit-details-marker]:hidden">
            <summary className="flex items-center justify-between p-4 cursor-pointer">
              <div className="flex items-center gap-2">
                <Info className="w-4 h-4 text-[#6B7280]" />
                <span className="text-xs font-semibold text-[#6B7280] uppercase tracking-widest">Data Provenance & Limitations</span>
              </div>
              <span className="transition group-open:rotate-180 text-[#6B7280]">
                <svg fill="none" height="24" shapeRendering="geometricPrecision" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" viewBox="0 0 24 24" width="24"><path d="M6 9l6 6 6-6"></path></svg>
              </span>
            </summary>
            <div className="p-4 pt-0 text-xs text-[#9CA3AF] space-y-3 border-t border-white/5 mt-2">
              <p><strong>OBSERVED:</strong> Topography (NASA SRTM 30m DEM), Road Network (OpenStreetMap), Ward Boundaries (BBMP 2011), Facilities (Overpass API).</p>
              <p><strong>SIMULATED:</strong> Inundation extent is calculated using a static "bathtub" model. It does not account for complex hydrological flow, stormwater drainage capacities, or dynamic temporal pooling.</p>
              <p><strong>DERIVED:</strong> Population physically affected is derived via strict spatial raster-masking of the WorldPop 2020 100m grid.</p>
              <p className="text-[#FFB400]"><strong>LIMITATIONS:</strong> No hardcoded casualties, financial losses, or heuristic damage multipliers are applied. The AI narrative is strictly constrained to rephrase structured topological output and is not an independent forecasting model.</p>
            </div>
          </details>
          
        </div>
      </motion.div>
    </div>
  );
}
