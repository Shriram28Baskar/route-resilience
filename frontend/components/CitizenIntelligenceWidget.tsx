"use client";
/**
 * CitizenIntelligenceWidget.tsx
 *
 * Citizen Intelligence — independent evidence layer.
 *
 * Allows judges/users to submit a citizen distress report and see it flow
 * through NLP → geo-snap → twin-comparison → WebSocket re-evaluation.
 *
 * Includes a "Run Demo Reports" button that posts 3 pre-scripted reports.
 *
 * NOTE: Citizen reports NEVER mutate the physical flood simulation.
 * They are held as independent evidence and compared with the digital twin.
 */

import React, { useState } from "react";
import { useDisasterState } from "@/contexts/DisasterStateContext";
import {
  submitCitizenReport, runDemoCitizenReports,
  CitizenReportResponse, CitizenReport,
} from "@/lib/api";

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical", cls: "text-red-400" },
  { value: "high",     label: "High",     cls: "text-orange-400" },
  { value: "moderate", label: "Moderate", cls: "text-yellow-400" },
  { value: "low",      label: "Low",      cls: "text-gray-400" },
] as const;

function AgreementBadge({ agreement }: { agreement: CitizenReport["twin_agreement"] }) {
  const cfg = {
    AGREES:       { cls: "bg-green-800 text-green-200",  label: "✓ AGREES with twin" },
    DISAGREES:    { cls: "bg-red-800 text-red-200",      label: "⚡ DISAGREES with twin" },
    UNVERIFIABLE: { cls: "bg-gray-700 text-gray-300",    label: "? Unverifiable" },
  }[agreement] ?? { cls: "bg-gray-700 text-gray-300", label: "?" };

  return (
    <span className={`text-xs px-2 py-0.5 rounded font-semibold ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

export default function CitizenIntelligenceWidget() {
  const { state } = useDisasterState();

  const [lat, setLat]     = useState("12.9352");
  const [lon, setLon]     = useState("77.6245");
  const [msg, setMsg]     = useState("Water waist deep near arterial road junction");
  const [sev, setSev]     = useState<"critical" | "high" | "moderate" | "low">("high");
  const [submitting, setSubmitting] = useState(false);
  const [demoRunning,  setDemoRunning]  = useState(false);
  const [result, setResult] = useState<CitizenReportResponse | null>(null);
  const [error, setError]   = useState<string | null>(null);

  const liveReports = state?.citizen_reports ?? [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    setError(null);
    try {
      const res = await submitCitizenReport({
        lat: parseFloat(lat),
        lon: parseFloat(lon),
        message: msg,
        severity: sev,
      });
      setResult(res);
      setMsg("");
    } catch (err: any) {
      setError(err?.message ?? "Submission failed. Check coordinates are within Bengaluru AOI.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDemo = async () => {
    setDemoRunning(true);
    setResult(null);
    setError(null);
    try {
      await runDemoCitizenReports();
    } catch {
      setError("One or more demo reports failed.");
    } finally {
      setDemoRunning(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 space-y-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-100 uppercase tracking-wide">
          Citizen Intelligence
        </h3>
        <span className="text-xs text-gray-500">Independent Evidence Layer</span>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Latitude</label>
            <input
              type="number" step="0.0001" value={lat}
              onChange={e => setLat(e.target.value)}
              placeholder="12.9352"
              className="w-full px-2 py-1.5 text-sm bg-gray-800 border border-gray-600 rounded
                         text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Longitude</label>
            <input
              type="number" step="0.0001" value={lon}
              onChange={e => setLon(e.target.value)}
              placeholder="77.6245"
              className="w-full px-2 py-1.5 text-sm bg-gray-800 border border-gray-600 rounded
                         text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500"
              required
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Message</label>
          <textarea
            value={msg}
            onChange={e => setMsg(e.target.value)}
            placeholder="Describe what you observe (e.g. Road flooded, cars stuck...)"
            rows={2}
            maxLength={500}
            className="w-full px-2 py-1.5 text-sm bg-gray-800 border border-gray-600 rounded
                       text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 resize-none"
            required
          />
        </div>

        <div className="flex items-center gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Severity</label>
            <select
              value={sev}
              onChange={e => setSev(e.target.value as any)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-600 rounded text-gray-100
                         focus:outline-none focus:border-blue-500"
            >
              {SEVERITY_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="flex-1" />

          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                       text-white rounded font-semibold transition-colors"
          >
            {submitting ? "Submitting…" : "Submit Report"}
          </button>

          <button
            type="button"
            onClick={handleDemo}
            disabled={demoRunning}
            className="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800
                       text-gray-200 rounded transition-colors border border-gray-600"
          >
            {demoRunning ? "Posting…" : "▶ Run Demo Reports"}
          </button>
        </div>
      </form>

      {/* Result */}
      {result && (
        <div className="px-4 pb-3 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-green-400 font-semibold">✓ Report received</span>
            <AgreementBadge agreement={result.twin_agreement as any} />
            {result.flooding_indicator && (
              <span className="text-xs bg-blue-800 text-blue-200 px-2 py-0.5 rounded">
                Flooding detected in message
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400">
            Snapped to node {result.snapped_node_id} (dist: {result.snap_distance_m}m) ·{" "}
            {result.twin_note}
          </p>
          <p className="text-xs text-gray-600 italic">
            This report is stored as independent evidence. It does NOT modify the flood simulation.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-4 pb-3">
          <p className="text-xs text-red-400">⚠ {error}</p>
        </div>
      )}

      {/* Live reports from current state */}
      {liveReports.length > 0 && (
        <div className="border-t border-gray-800">
          <div className="px-4 py-1.5 text-xs text-gray-500 bg-gray-800/40">
            Reports in current loop cycle ({liveReports.length})
          </div>
          <ul className="divide-y divide-gray-800 max-h-48 overflow-y-auto">
            {liveReports.map((r) => (
              <li key={r.report_id} className="px-4 py-2 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-xs font-semibold ${
                    r.severity === "critical" ? "text-red-400" :
                    r.severity === "high"     ? "text-orange-400" :
                    r.severity === "moderate" ? "text-yellow-400" :
                                               "text-gray-400"
                  }`}>
                    {r.severity.toUpperCase()}
                  </span>
                  {r.flooding_indicator && (
                    <span className="text-xs text-blue-400">● Flooding</span>
                  )}
                  <AgreementBadge agreement={r.twin_agreement} />
                  <span className="text-xs text-gray-600 ml-auto">
                    ({r.lat.toFixed(4)}, {r.lon.toFixed(4)})
                  </span>
                </div>
                <p className="text-xs text-gray-300 truncate">{r.message}</p>
                {r.twin_agreement === "DISAGREES" && (
                  <p className="text-xs text-yellow-400 italic">{r.twin_note}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
