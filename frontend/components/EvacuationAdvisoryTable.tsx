"use client";
/**
 * EvacuationAdvisoryTable.tsx
 *
 * Displays ward-level evacuation advisories from the active ActionPlan.
 * Sorted by severity: EVACUATE_NOW first, EVACUATE_ADVISED second, MONITOR last.
 */

import React from "react";
import { useDisasterState } from "@/contexts/DisasterStateContext";
import { EvacAdvisory } from "@/lib/api";

function ActionBadge({ action }: { action: EvacAdvisory["action"] }) {
  const cfg = {
    EVACUATE_NOW:     { cls: "bg-red-700 text-white", label: "EVACUATE NOW" },
    EVACUATE_ADVISED: { cls: "bg-orange-600 text-white", label: "EVACUATE ADVISED" },
    MONITOR:          { cls: "bg-gray-600 text-gray-200", label: "MONITOR" },
  }[action] ?? { cls: "bg-gray-800 text-gray-400", label: action };

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold whitespace-nowrap ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function HospBadge({ reachable }: { reachable: boolean }) {
  return reachable ? (
    <span className="text-green-400 text-xs font-semibold">✓ Reachable</span>
  ) : (
    <span className="text-red-400 text-xs font-bold">✗ Isolated</span>
  );
}

function formatTime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  return `${Math.round(s / 60)} min`;
}

export default function EvacuationAdvisoryTable() {
  const { state } = useDisasterState();

  const advisories: EvacAdvisory[] =
    state?.action_plan?.evacuation_advisories ?? [];

  if (!state) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-4 text-sm text-gray-500 italic">
        Waiting for autonomous loop…
      </div>
    );
  }

  if (advisories.length === 0) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-4 text-sm text-gray-400">
        No evacuation advisories at current water level.
      </div>
    );
  }

  const evacuateNow    = advisories.filter(a => a.action === "EVACUATE_NOW");
  const evacuateAdvise = advisories.filter(a => a.action === "EVACUATE_ADVISED");
  const monitor        = advisories.filter(a => a.action === "MONITOR");

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 overflow-hidden">
      <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-100 uppercase tracking-wide">
          Evacuation Advisories
        </h3>
        <div className="flex gap-2 text-xs">
          {evacuateNow.length > 0 && (
            <span className="bg-red-800 text-red-200 px-2 py-0.5 rounded font-bold">
              {evacuateNow.length} NOW
            </span>
          )}
          {evacuateAdvise.length > 0 && (
            <span className="bg-orange-800 text-orange-200 px-2 py-0.5 rounded">
              {evacuateAdvise.length} ADVISED
            </span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs text-gray-300">
          <thead className="bg-gray-800 text-gray-400 uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Ward</th>
              <th className="px-3 py-2 text-left">Action</th>
              <th className="px-3 py-2 text-right">Population</th>
              <th className="px-3 py-2 text-right">Flooded Nodes</th>
              <th className="px-3 py-2 text-left">Route</th>
              <th className="px-3 py-2 text-right">Est. Travel</th>
              <th className="px-3 py-2 text-center">Hospital</th>
            </tr>
          </thead>
          <tbody>
            {advisories.map((a, i) => (
              <tr
                key={a.ward_name + i}
                className={`border-t border-gray-800 ${
                  a.action === "EVACUATE_NOW"
                    ? "bg-red-950/30"
                    : a.action === "EVACUATE_ADVISED"
                    ? "bg-orange-950/20"
                    : ""
                }`}
              >
                <td className="px-3 py-2 font-semibold text-gray-100">{a.ward_name}</td>
                <td className="px-3 py-2"><ActionBadge action={a.action} /></td>
                <td className="px-3 py-2 text-right">{a.population_estimate.toLocaleString()}</td>
                <td className="px-3 py-2 text-right">{a.flooded_node_count}</td>
                <td className="px-3 py-2 text-gray-400 max-w-[200px] truncate">{a.recommended_corridor}</td>
                <td className="px-3 py-2 text-right">{formatTime(a.travel_time_estimate_s)}</td>
                <td className="px-3 py-2 text-center"><HospBadge reachable={a.hospital_reachable} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-1.5 bg-gray-800/50 text-xs text-gray-500 border-t border-gray-800">
        Population: node-proxy estimate · Travel time: haversine at 30km/h · Loop #{state.sequence_no}
      </div>
    </div>
  );
}
