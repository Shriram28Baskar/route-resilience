"use client";
/**
 * LoopStatusBar.tsx
 *
 * Shows the autonomous loop status: sequence number, last update time,
 * connection state, and rainfall severity badge.
 */

import React, { useEffect, useState } from "react";
import { useDisasterState } from "@/contexts/DisasterStateContext";
import { triggerLoop } from "@/lib/api";

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5)  return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function severityColor(rainfall: number): string {
  if (rainfall >= 64.5) return "bg-red-700 text-white";     // Extremely heavy
  if (rainfall >= 15.6) return "bg-orange-500 text-white";  // Heavy / Very heavy
  if (rainfall >= 7.5)  return "bg-yellow-400 text-black";  // Moderate
  if (rainfall >= 2.5)  return "bg-blue-400 text-white";    // Light
  return "bg-gray-200 text-gray-700";                        // Trace / No rain
}

function rainfallLabel(rainfall: number): string {
  if (rainfall >= 64.5) return "Extremely Heavy";
  if (rainfall >= 15.6) return "Heavy";
  if (rainfall >= 7.5)  return "Moderate";
  if (rainfall >= 2.5)  return "Light";
  return "No Rain";
}

export default function LoopStatusBar() {
  const { state, lastHeartbeat, wsStatus, loopSeq, lastUpdated } = useDisasterState();
  const [timeStr, setTimeStr] = useState("—");
  const [triggering, setTriggering] = useState(false);

  // Update time-ago every 5s
  useEffect(() => {
    const update = () => setTimeStr(timeAgo(lastUpdated));
    update();
    const id = setInterval(update, 5000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  const rainfall = state?.rainfall_rate_mm_h ?? lastHeartbeat?.rainfall_rate_mm_h ?? 0;
  const ri = state?.resilience_index;

  const handleTrigger = async (rainfallMmH?: number) => {
    setTriggering(true);
    try {
      await triggerLoop(rainfallMmH);
    } catch {
      // Silent — loop will run
    }
    setTimeout(() => setTriggering(false), 3000);
  };

  const wsBadge =
    wsStatus === "connected"     ? "bg-green-500"  :
    wsStatus === "reconnecting"  ? "bg-yellow-400" :
                                   "bg-red-500";

  const changeBadge = state?.material_change
    ? "text-orange-400 font-semibold"
    : "text-gray-400";

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 text-sm font-mono">
      {/* WS indicator */}
      <span className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full inline-block ${wsBadge}`} />
        <span className="text-gray-300">
          {wsStatus === "connected" ? "Live" : wsStatus === "reconnecting" ? "Reconnecting…" : "Offline"}
        </span>
      </span>

      <span className="text-gray-600">|</span>

      {/* Loop sequence */}
      <span className="text-gray-300">
        Loop <span className="text-white font-bold">#{loopSeq || "—"}</span>
      </span>

      {/* Last updated */}
      <span className="text-gray-400">Updated {timeStr}</span>

      {/* Material change */}
      {state && (
        <span className={changeBadge}>
          {state.material_change ? "● Changed" : "○ No change"}
        </span>
      )}

      <span className="text-gray-600">|</span>

      {/* Rainfall + severity */}
      <span className={`px-2 py-0.5 rounded text-xs font-bold ${severityColor(rainfall)}`}>
        {rainfall.toFixed(1)} mm/h — {rainfallLabel(rainfall)}
      </span>

      {/* Resilience Index */}
      {ri !== null && ri !== undefined && (
        <span className={`text-xs ${ri < 0.5 ? "text-red-400 font-bold" : ri < 0.7 ? "text-yellow-400" : "text-green-400"}`}>
          RI: {ri.toFixed(2)}
        </span>
      )}

      {/* Flooded nodes */}
      {state && (
        <span className="text-gray-300 text-xs">
          {state.flooded_node_count.toLocaleString()} nodes flooded
        </span>
      )}

      <span className="ml-auto" />

      {/* Forecast Stress Test Controls */}
      <div className="flex items-center gap-1.5 bg-gray-850 px-2 py-1 rounded-lg border border-gray-700/80 text-xs">
        <span className="text-gray-400 font-semibold text-[11px] uppercase tracking-wider mr-0.5">
          Forecast Test:
        </span>
        <button
          onClick={() => handleTrigger(15.0)}
          disabled={triggering}
          title="Simulate 15 mm/h Moderate Rain forecast"
          className="px-2 py-0.5 text-[11px] bg-blue-900/70 hover:bg-blue-700 border border-blue-600/50
                     text-blue-100 rounded transition-colors"
        >
          15 mm/h
        </button>

        <button
          onClick={() => handleTrigger(35.0)}
          disabled={triggering}
          title="Simulate 35 mm/h Heavy Rain forecast"
          className="px-2 py-0.5 text-[11px] bg-amber-900/70 hover:bg-amber-700 border border-amber-600/50
                     text-amber-100 font-medium rounded transition-colors"
        >
          35 mm/h
        </button>

        <button
          onClick={() => handleTrigger(65.0)}
          disabled={triggering}
          title="Simulate 65 mm/h Cloudburst surge"
          className="px-2.5 py-0.5 text-[11px] bg-red-600 hover:bg-red-500 disabled:bg-gray-700
                     text-white font-bold rounded transition-colors flex items-center gap-1"
        >
          ⚡ 65 mm/h
        </button>

        <button
          onClick={() => handleTrigger(0.0)}
          disabled={triggering}
          title="Reset to 0 mm/h Dry Baseline / Live Weather"
          className="px-2 py-0.5 text-[11px] bg-gray-800 hover:bg-gray-700 disabled:bg-gray-850
                     text-gray-300 rounded transition-colors border border-gray-700"
        >
          ↺ Reset
        </button>
      </div>
    </div>
  );
}
