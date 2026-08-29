"use client";

import type { HistoricalScenarioResponse } from "@/lib/api";

export default function HistoricalScenarioResults({ data }: { data: HistoricalScenarioResponse }) {
  const obs = data.observed_historical_facts;
  const inputs = data.model_inputs;
  const sim = data.simulated_results;
  const cmp = data.directional_comparison;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-amber-400 mb-1">Historical Scenario</div>
            <h2 className="font-display font-bold text-xl text-white">{data.scenario_metadata?.name}</h2>
            <div className="text-sm text-[#9CA3AF] mt-1">
              Peak date: <span className="text-amber-400 font-mono">{data.scenario_metadata?.peak_date}</span>
            </div>
          </div>
          <div className="text-3xl select-none">🗓</div>
        </div>
        <p className="text-sm text-[#9CA3AF] mt-3">{data.scenario_metadata?.description}</p>
        <p className="text-xs text-amber-400/80 mt-3 font-semibold">
          Route Resilience uses documented disaster conditions and real geospatial datasets to simulate how infrastructure failure can affect emergency connectivity.
        </p>
      </div>

      {/* OBSERVED HISTORICAL FACTS — blue */}
      <div className="bg-blue-950/40 border border-blue-500/30 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0" />
          <span className="text-xs font-bold uppercase tracking-widest text-blue-400">Observed Historical Facts</span>
        </div>
        <p className="text-[10px] text-blue-400/70 mb-4 italic">{obs?._label}</p>
        <div className="space-y-3">
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-1">Peak Rainfall (Observed)</div>
            <div className="font-mono text-2xl font-bold text-blue-400">{obs?.rainfall_mm} mm / 24h</div>
            <div className="text-xs text-[#9CA3AF] mt-1">{obs?.rainfall_precision}</div>
            <div className="text-[10px] text-[#6B7280] mt-1">Source: {obs?.rainfall_source}</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-2">
              Documented Affected Areas (Qualitative — not a surveyed flood boundary)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(obs?.known_affected_areas_qualitative ?? []).map((area: string) => (
                <span
                  key={area}
                  className="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs"
                >
                  {area}
                </span>
              ))}
            </div>
            <div className="text-[10px] text-[#6B7280] mt-2">Source: {obs?.known_affected_areas_source}</div>
          </div>
        </div>
      </div>

      {/* MODE A: Rainfall Prediction (Limitation Exposed) */}
      <div className="bg-red-950/20 border border-red-500/30 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
          <span className="text-xs font-bold uppercase tracking-widest text-red-400">
            MODE A: Rainfall → Runoff Prediction (Limitation Exposed)
          </span>
        </div>
        <div className="text-xs text-[#9CA3AF] mb-4">
          Attempting to predict the flood extent purely from the 131mm rainfall input using the baseline uniform-runoff model.
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Input Rainfall</div>
            <div className="font-mono text-lg font-bold text-white">{inputs?.rainfall_runoff_model_output?.rainfall_mm} mm</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Modeled Water Level</div>
            <div className="font-mono text-lg font-bold text-red-400">
              {inputs?.rainfall_runoff_model_output?.water_level_m?.toFixed(2)}m
            </div>
          </div>
        </div>
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-widest text-red-400 mb-1">Inundation Result</div>
          <div className="text-xs text-red-300 font-medium mb-1">
            Only {inputs?.rainfall_runoff_model_output?.flooded_nodes_at_this_level} nodes flooded.
          </div>
          <p className="text-[10px] text-red-400/80 leading-relaxed">
            {inputs?.rainfall_runoff_model_output?.limitation}
          </p>
        </div>
      </div>

      {/* MODE B: Calibrated Scenario Analysis */}
      <div className="bg-amber-950/20 border border-amber-500/40 rounded-xl p-5 shadow-[0_0_15px_rgba(245,158,11,0.1)]">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
          <span className="text-xs font-bold uppercase tracking-widest text-amber-400">
            MODE B: Infrastructure Impact Simulation
          </span>
        </div>
        <div className="text-xs font-semibold text-amber-400/90 mb-4 bg-amber-500/10 p-2 rounded border border-amber-500/20">
          Scenario Analysis — calibrated water-level input; not a rainfall prediction.
        </div>
        
        <div className="bg-[#0B0F1A] border border-amber-500/20 rounded-lg p-3 mb-4">
          <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-1">Calibrated Scenario Input</div>
          <div className="font-mono text-2xl font-bold text-amber-400">
            {inputs?.scenario_water_level_m}m ASL
          </div>
          <p className="text-[10px] text-[#6B7280] mt-1">
            Basis: {inputs?.scenario_water_level_basis?.replace(/_/g, " ")}
          </p>
        </div>

        <div className="text-[10px] uppercase tracking-widest text-amber-500 mb-2 mt-4">Dynamically Computed Network Impact</div>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Flooded Nodes</div>
            <div className="font-mono text-xl font-bold text-amber-400">
              {sim?.flooded_nodes?.toLocaleString()}
            </div>
            <div className="text-[10px] text-[#6B7280]">
              of {sim?.total_nodes?.toLocaleString()} ({sim?.flood_fraction_pct}%)
            </div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Road Length Flooded</div>
            <div className="font-mono text-xl font-bold text-amber-400">
              {sim?.road_length_flooded_km} km
            </div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Population in Flood Zone</div>
            <div className="font-mono text-xl font-bold text-[#FF4444]">
              {sim?.population_in_flood_zone?.value?.toLocaleString()}
            </div>
            <div className="text-[10px] text-[#6B7280]">WorldPop 2020 gridded estimate</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Network Fragmentation</div>
            <div className="font-mono text-xl font-bold text-[#FFB400]">
              {sim?.surviving_network?.surviving_components}
            </div>
            <div className="text-[10px] text-[#6B7280]">isolated components</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Hospitals in Flood Zone</div>
            <div className="font-mono text-xl font-bold text-[#FF4444]">
              {sim?.facility_impact?.hospitals_in_flood_zone ?? "—"}
              {" / "}
              {sim?.facility_impact?.hospitals_total_in_aoi ?? "—"}
            </div>
            <div className="text-[10px] text-[#6B7280]">OSM-sourced facilities</div>
          </div>
          <div className="bg-[#0B0F1A] rounded-lg p-3">
            <div className="text-[10px] text-[#6B7280] mb-1">Wards Affected</div>
            <div className="font-mono text-xl font-bold text-amber-400">
              {sim?.ward_impact?.wards_with_flooded_nodes}
            </div>
            <div className="text-[10px] text-[#6B7280]">BBMP ward boundaries</div>
          </div>
        </div>
      </div>

      {/* DIRECTIONAL COMPARISON — purple */}
      <div className="bg-purple-950/30 border border-purple-500/30 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full bg-purple-400 flex-shrink-0" />
          <span className="text-xs font-bold uppercase tracking-widest text-purple-400">
            Directional Comparison (Mode B vs Documented)
          </span>
        </div>
        <p className="text-[10px] text-purple-400/70 mb-4 italic">{cmp?._label}</p>
        
        {cmp?.partial_name_overlap?.length > 0 && (
          <div className="bg-[#0B0F1A] rounded-lg p-3 mb-3">
            <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-2">
              Area Name Matches (partial / substring)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cmp.partial_name_overlap.map((a: string) => (
                <span
                  key={a}
                  className="px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs"
                >
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="bg-[#0B0F1A] rounded-lg p-3 mb-3">
          <div className="text-[10px] uppercase tracking-widest text-[#6B7280] mb-2">
            Areas Outside Simulation Boundary
          </div>
          {(cmp?.areas_outside_aoi ?? []).map((a: string) => (
            <div key={a} className="text-[10px] text-[#6B7280] mb-1">
              • {a}
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

