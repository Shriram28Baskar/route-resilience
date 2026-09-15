"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, FlaskConical, HelpCircle, XCircle } from "lucide-react";
import type { DataProvenance, DataUnavailableError, ProvenanceStatus } from "@/lib/api";

/**
 * Renders the backend's data_provenance block.
 *
 * The point of this component is that a number alone does not tell the user
 * whether it was measured or produced by a chain of fixed coefficients. Every
 * panel showing a figure should show one of these next to it.
 */

const STATUS_STYLE: Record<ProvenanceStatus, { label: string; cls: string; icon: typeof CheckCircle2; blurb: string }> = {
  measured: {
    label: "MEASURED",
    cls: "text-[#00E5B4] bg-[#00E5B4]/10 border-[#00E5B4]/25",
    icon: CheckCircle2,
    blurb: "Computed from a real input artifact present on disk.",
  },
  derived: {
    label: "DERIVED",
    cls: "text-[#FFB400] bg-[#FFB400]/10 border-[#FFB400]/25",
    icon: AlertTriangle,
    blurb:
      "Computed from a measured input PLUS modelling constants that are not themselves measured. Read the assumptions before citing this.",
  },
  synthetic: {
    label: "SYNTHETIC",
    cls: "text-[#FF8C00] bg-[#FF8C00]/10 border-[#FF8C00]/25",
    icon: FlaskConical,
    blurb: "Produced by a placeholder model with no real input behind it. Not a measurement.",
  },
  unavailable: {
    label: "UNAVAILABLE",
    cls: "text-[#FF4444] bg-[#FF4444]/10 border-[#FF4444]/25",
    icon: XCircle,
    blurb: "A required input is missing. No value is shown.",
  },
};

export function ProvenanceBadge({ provenance }: { provenance?: DataProvenance }) {
  const [open, setOpen] = useState(false);
  if (!provenance) return null;

  const style = STATUS_STYLE[provenance.status] ?? STATUS_STYLE.synthetic;
  const Icon = style.icon;
  const graphInput = provenance.inputs?.find((i) => i.kind === "graph");
  const detailCount = (provenance.assumptions?.length ?? 0) + (provenance.notes?.length ?? 0);

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-mono tracking-wider ${style.cls}`}
        aria-expanded={open}
      >
        <Icon className="w-3 h-3" />
        {style.label}
        {detailCount > 0 && <span className="opacity-70">· {detailCount} note{detailCount === 1 ? "" : "s"}</span>}
        <HelpCircle className="w-3 h-3 opacity-50" />
      </button>

      {open && (
        <div className="mt-2 p-3 rounded-lg bg-black/30 border border-white/10 text-[11px] space-y-2">
          <p className="text-[#9CA3AF]">{style.blurb}</p>

          {graphInput?.fingerprint && (
            <div>
              <div className="text-[#6B7280] uppercase tracking-widest text-[9px] mb-0.5">
                Graph fingerprint
              </div>
              <code className="text-[#9CA3AF] break-all">{graphInput.fingerprint.slice(0, 32)}…</code>
              <div className="text-[#6B7280] mt-0.5">
                {graphInput.nodes?.toLocaleString()} nodes · {graphInput.edges?.toLocaleString()} edges
              </div>
            </div>
          )}

          {provenance.assumptions?.length > 0 && (
            <div>
              <div className="text-[#FFB400] uppercase tracking-widest text-[9px] mb-1">
                Modelling assumptions
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[#9CA3AF]">
                {provenance.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {provenance.notes?.length > 0 && (
            <div>
              <div className="text-[#6B7280] uppercase tracking-widest text-[9px] mb-1">Notes</div>
              <ul className="list-disc list-inside space-y-0.5 text-[#9CA3AF]">
                {provenance.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Rendered in place of a chart when the backend returns 503 because a required
 * artifact is absent. Showing an empty chart instead would read as "no impact".
 */
export function DataUnavailablePanel({ error }: { error: DataUnavailableError }) {
  return (
    <div className="bg-[#FF4444]/5 border border-[#FF4444]/25 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <XCircle className="w-4 h-4 text-[#FF4444]" />
        <span className="text-[#FF4444] font-semibold text-sm">Data unavailable</span>
      </div>

      <p className="text-xs text-[#9CA3AF] mb-3">{error.message}</p>

      {error.missing?.length > 0 && (
        <div className="mb-3">
          <div className="text-[9px] uppercase tracking-widest text-[#6B7280] mb-1">
            Missing artifacts
          </div>
          <ul className="space-y-1">
            {error.missing.map((m) => (
              <li key={m.name} className="text-[11px]">
                <code className="text-[#FFB400]">{m.path ?? m.name}</code>
                {m.obtain && <div className="text-[#6B7280] mt-0.5">{m.obtain}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[10px] text-[#6B7280]">
        No substitute value is shown. Previously this endpoint returned numbers computed
        from fixed constants, which was indistinguishable from a real result.
        {error.see && <> See <code>{error.see}</code>.</>}
      </p>
    </div>
  );
}
