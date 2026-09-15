"use client";
/**
 * IncidentCommanderPanel.tsx
 *
 * Executive Incident Commander Dashboard:
 * Replaces dense paragraph walls with clean KPI cards, structured operational
 * directives, compact trigger badges, and an expandable narrative briefing.
 */

import React, { useState } from "react";
import { useDisasterState } from "@/contexts/DisasterStateContext";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CloudRain,
  Hospital,
  ShieldCheck,
  ShieldAlert,
  Tent,
  ChevronDown,
  ChevronUp,
  Zap,
  Radio,
} from "lucide-react";

function NarrativeSourceBadge({ source }: { source: "llm" | "template" }) {
  return source === "llm" ? (
    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-purple-900/80 text-purple-200 border border-purple-600 font-semibold tracking-wide">
      <Zap className="w-3 h-3 text-purple-300" />
      AI Briefing
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
      <Radio className="w-3 h-3 text-gray-400" />
      Deterministic
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const isHigh = severity === "HIGH";
  const isMed = severity === "MEDIUM";
  const cls = isHigh
    ? "bg-red-500/20 text-red-300 border-red-500/50"
    : isMed
    ? "bg-amber-500/20 text-amber-300 border-amber-500/50"
    : "bg-emerald-500/20 text-emerald-300 border-emerald-500/50";

  return (
    <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border ${cls}`}>
      {severity || "NORMAL"}
    </span>
  );
}

export default function IncidentCommanderPanel() {
  const { state } = useDisasterState();
  const [showFullNarrative, setShowFullNarrative] = useState(false);
  const [showFacilityList, setShowFacilityList] = useState(false);

  if (!state) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/90 p-5 shadow-lg backdrop-blur-sm">
        <div className="flex items-center gap-2 text-sm text-gray-400 italic">
          <Activity className="w-4 h-4 animate-spin text-blue-400" />
          Synchronizing with autonomous digital twin loop…
        </div>
      </div>
    );
  }

  const isolatedHospitals = state.hospital_status.filter((h) => !h.reachable);
  const totalHospitals = state.hospital_status.length || 346;
  const reachableCount = totalHospitals - isolatedHospitals.length;
  const de = state.decision_event;

  // Evacuation counts
  const evacNowCount =
    state.action_plan?.evacuation_advisories.filter((a) => a.action === "EVACUATE_NOW").length || 0;
  const evacAdvisedCount =
    state.action_plan?.evacuation_advisories.filter((a) => a.action === "EVACUATE_ADVISED").length || 0;
  const reliefCampsCount = state.action_plan?.relief_camps?.length || 3;

  // Format trigger reason so it never vomits 28 hospital names
  const cleanTriggerReason = de?.trigger_reason
    ? de.trigger_reason.replace(/^(?:[^,]+,\s*){3,}[^;]+hospital\(s\)\s*(restored|now isolated)/i, (match, action) => {
        const count = match.split(",").length;
        return `${count} medical facilities ${action}`;
      })
    : "";

  // Parse narrative into scannable bullet points
  const rawBullets = state.narrative
    ? state.narrative
        .split(/(?:^|\n)[•\-\*]\s*|\.\s+(?=[A-Z])/)
        .map((s) => s.trim())
        .filter((s) => s.length > 5)
    : [];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/95 p-4 md:p-5 shadow-2xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800/80">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-gray-100 uppercase tracking-wider">
              Incident Commander
            </h3>
            <p className="text-[11px] text-gray-400">
              Autonomous Loop #{state.sequence_no} ·{" "}
              {new Date(state.observed_at).toLocaleTimeString()} UTC
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {de && <SeverityBadge severity={de.severity} />}
          <NarrativeSourceBadge source={state.narrative_source} />
        </div>
      </div>

      {/* 4-Card Executive KPI Grid (2x2 layout for spacious, zero-collision alignment) */}
      <div className="grid grid-cols-2 gap-2.5">
        {/* Rainfall */}
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/60 flex flex-col justify-between">
          <div className="flex items-center justify-between text-gray-400 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Precipitation</span>
            <CloudRain className="w-4 h-4 text-blue-400" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-white">{state.rainfall_rate_mm_h.toFixed(1)}</span>
            <span className="text-xs font-medium text-gray-400">mm/h</span>
          </div>
          <div className="text-[11px] text-blue-300 font-medium mt-1">
            {state.rainfall_rate_mm_h > 0 ? "⚡ Storm Surge Active" : "✓ Dry Weather Baseline"}
          </div>
        </div>

        {/* Flood Extent */}
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/60 flex flex-col justify-between">
          <div className="flex items-center justify-between text-gray-400 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Inundation</span>
            <div className={`w-2.5 h-2.5 rounded-full ${state.flooded_node_count > 0 ? "bg-red-500 animate-pulse" : "bg-emerald-500"}`} />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-white">{state.flooded_node_count}</span>
            <span className="text-xs font-medium text-gray-400">nodes</span>
          </div>
          <div className="text-[11px] font-medium mt-1 text-gray-300">
            {state.flooded_node_count > 0 ? "⚠️ K&C Valley Inundated" : "✓ All Roads Clear"}
          </div>
        </div>

        {/* Healthcare Access */}
        <div className={`p-3 rounded-lg border flex flex-col justify-between ${
          isolatedHospitals.length > 0
            ? "bg-red-950/30 border-red-800/60"
            : "bg-emerald-950/20 border-emerald-800/40"
        }`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Healthcare</span>
            <Hospital className={`w-4 h-4 ${isolatedHospitals.length > 0 ? "text-red-400" : "text-emerald-400"}`} />
          </div>
          <div className="flex items-baseline gap-1">
            <span className={`text-xl font-black ${isolatedHospitals.length > 0 ? "text-red-300" : "text-emerald-300"}`}>
              {isolatedHospitals.length > 0 ? isolatedHospitals.length : reachableCount}
            </span>
            <span className="text-xs font-medium text-gray-400">
              {isolatedHospitals.length > 0 ? `/${totalHospitals} isolated` : `/${totalHospitals} reachable`}
            </span>
          </div>
          <div className="text-[11px] font-medium mt-1">
            {isolatedHospitals.length > 0 ? (
              <span className="text-red-400 font-semibold">⚠️ Corridors Severed</span>
            ) : (
              <span className="text-emerald-400 font-medium">✓ 100% Reachable</span>
            )}
          </div>
        </div>

        {/* Resilience Index */}
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/60 flex flex-col justify-between">
          <div className="flex items-center justify-between text-gray-400 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Resilience</span>
            {state.resilience_index && state.resilience_index < 0.7 ? (
              <ShieldAlert className="w-4 h-4 text-amber-400" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
            )}
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-white">
              {state.resilience_index !== null ? state.resilience_index.toFixed(2) : "1.00"}
            </span>
            <span className="text-xs font-medium text-gray-400">RI</span>
          </div>
          <div className="w-full bg-gray-700 h-1.5 rounded-full overflow-hidden mt-2">
            <div
              className={`h-full transition-all duration-500 ${
                (state.resilience_index || 1) < 0.6
                  ? "bg-red-500"
                  : (state.resilience_index || 1) < 0.85
                  ? "bg-amber-400"
                  : "bg-emerald-400"
              }`}
              style={{ width: `${Math.round((state.resilience_index || 1) * 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Decision Trigger Banner */}
      {de && (
        <div className="p-2.5 rounded-lg bg-gray-800/50 border border-gray-700/50 text-xs text-gray-300">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 font-medium text-gray-200">
              <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>
                <strong className="text-white">Trigger Event:</strong> {cleanTriggerReason}
              </span>
            </div>
            {isolatedHospitals.length > 2 && (
              <button
                onClick={() => setShowFacilityList(!showFacilityList)}
                className="text-[11px] text-blue-400 hover:text-blue-300 underline shrink-0 ml-2"
              >
                {showFacilityList ? "Hide facilities" : `View all ${isolatedHospitals.length}`}
              </button>
            )}
          </div>
          {de.changed_components.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {de.changed_components.map((comp) => (
                <span
                  key={comp}
                  className="text-[10px] px-2 py-0.5 rounded bg-gray-750 border border-gray-650 text-gray-300 font-mono"
                >
                  {comp}
                </span>
              ))}
            </div>
          )}
          {showFacilityList && isolatedHospitals.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-700/60 flex flex-wrap gap-1 max-h-32 overflow-y-auto">
              {isolatedHospitals.map((h) => (
                <span
                  key={h.name}
                  className="text-[10px] px-2 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-800/60"
                >
                  {h.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Key Operational Status Directives */}
      <div className="space-y-2">
        {/* Hospital Warning or All-Clear */}
        {isolatedHospitals.length > 0 ? (
          <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/70 text-xs text-red-200 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-bold uppercase tracking-wider text-red-300">
                Hospital Isolation Alert ({isolatedHospitals.length} Facilities Severed)
              </p>
              <p className="text-red-200/90 leading-relaxed">
                Emergency access cut off for:{" "}
                <span className="font-semibold text-white">
                  {isolatedHospitals.slice(0, 3).map((h) => h.name).join(", ")}
                </span>
                {isolatedHospitals.length > 3 && (
                  <span className="text-red-300"> +{isolatedHospitals.length - 3} more facilities</span>
                )}
                . Tactical corridor bridging prescribed.
              </p>
            </div>
          </div>
        ) : (
          <div className="p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs text-emerald-200 flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>
              <strong className="text-emerald-300">All {totalHospitals} medical facilities</strong> remain fully reachable via primary road corridors.
            </span>
          </div>
        )}

        {/* Evacuation & Civil Defense */}
        {evacNowCount > 0 || evacAdvisedCount > 0 ? (
          <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/60 text-xs text-amber-200 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold uppercase tracking-wider text-amber-300">
                Evacuation Directives Active
              </p>
              <p className="text-amber-100/90 mt-0.5">
                <span className="font-bold text-red-300">{evacNowCount} wards</span> under mandatory <strong>EVACUATE_NOW</strong> directive.{" "}
                <span className="font-bold text-amber-300">{evacAdvisedCount} wards</span> under <strong>EVACUATE_ADVISED</strong>.
              </p>
            </div>
          </div>
        ) : (
          <div className="p-2.5 rounded-lg bg-gray-800/40 border border-gray-700/40 text-xs text-gray-300 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Tent className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <span>
                <strong className="text-gray-200">{reliefCampsCount} Tactical Relief Camps</strong> positioned on dry high-elevation ground.
              </span>
            </div>
            <span className="text-[10px] text-emerald-400 font-semibold uppercase">0 Evac Orders</span>
          </div>
        )}
      </div>

      {/* Structured Scannable Bullets */}
      {rawBullets.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
            Executive Directives:
          </div>
          <div className="grid gap-1.5 text-xs text-gray-300">
            {rawBullets.slice(0, 4).map((bullet, idx) => (
              <div
                key={idx}
                className="p-2 rounded bg-gray-800/30 border border-gray-800 flex items-start gap-2 leading-relaxed"
              >
                <span className="text-blue-400 font-bold">•</span>
                <span>{bullet}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Collapsible Full Narrative Accordion */}
      {state.narrative && (
        <div className="pt-1">
          <button
            onClick={() => setShowFullNarrative(!showFullNarrative)}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 font-medium transition-colors"
          >
            {showFullNarrative ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showFullNarrative ? "Hide Full AI Briefing" : "Read Full AI Briefing"}
          </button>
          {showFullNarrative && (
            <div className="mt-2 p-3 rounded-lg bg-gray-950/80 border border-gray-800 text-xs text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">
              {state.narrative}
            </div>
          )}
        </div>
      )}

      {/* Citizen Evidence Warning */}
      {state.citizen_reports.filter((r) => r.twin_agreement === "DISAGREES").length > 0 && (
        <div className="text-xs p-2.5 rounded-lg bg-yellow-900/30 border border-yellow-700/60 text-yellow-200 flex items-center gap-2">
          <Zap className="w-4 h-4 text-yellow-400 shrink-0" />
          <span>
            <strong>Digital Twin Discrepancy:</strong>{" "}
            {state.citizen_reports.filter((r) => r.twin_agreement === "DISAGREES").length} citizen report(s) disagree with the physical twin (unmodeled local blockage detected).
          </span>
        </div>
      )}

      {/* Footer */}
      <div className="text-[11px] text-gray-500 border-t border-gray-800/70 pt-2 flex items-center justify-between">
        <span>Execution Latency: {state.loop_duration_s.toFixed(2)}s</span>
        <span>Decision Engine: Deterministic DECIDE</span>
      </div>
    </div>
  );
}
