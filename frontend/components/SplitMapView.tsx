"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface SplitMapViewProps {
  /** Label shown on the left (before) panel */
  beforeLabel?: string;
  /** Label shown on the right (after) panel */
  afterLabel?: string;
  /** Initial split position as a percentage (0-100) */
  initialSplit?: number;
  onSplitChange?: (pct: number) => void;
}

/**
 * Before/After split-screen map slider.
 * Renders two side-by-side labels with a draggable divider.
 * Wrap your before and after content inside and pass via children or render
 * props. This component provides the visual divider UI.
 */
export default function SplitMapView({
  beforeLabel = "Pre-Disaster",
  afterLabel = "Post-Disaster",
  initialSplit = 50,
  onSplitChange,
}: SplitMapViewProps) {
  const [splitPct, setSplitPct] = useState(initialSplit);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.max(10, Math.min(90, ((e.clientX - rect.left) / rect.width) * 100));
      setSplitPct(pct);
      onSplitChange?.(pct);
    },
    [isDragging, onSplitChange]
  );

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const touch = e.touches[0];
      const pct = Math.max(10, Math.min(90, ((touch.clientX - rect.left) / rect.width) * 100));
      setSplitPct(pct);
      onSplitChange?.(pct);
    },
    [isDragging, onSplitChange]
  );

  useEffect(() => {
    const stopDrag = () => setIsDragging(false);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", stopDrag);
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", stopDrag);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", stopDrag);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", stopDrag);
    };
  }, [handleMouseMove, handleTouchMove]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden select-none"
      style={{ cursor: isDragging ? "col-resize" : "default" }}
    >
      {/* ── Before label ─────────────────────────────────────────────── */}
      <div
        className="absolute top-3 z-10 pointer-events-none"
        style={{ left: `${Math.max(8, splitPct - 18)}%` }}
      >
        <div
          className="px-3 py-1 rounded-full text-xs font-bold tracking-wider"
          style={{
            background: "rgba(11,15,26,0.85)",
            border: "1px solid rgba(0,229,180,0.5)",
            color: "#00E5B4",
            backdropFilter: "blur(8px)",
          }}
        >
          {beforeLabel}
        </div>
      </div>

      {/* ── After label ──────────────────────────────────────────────── */}
      <div
        className="absolute top-3 z-10 pointer-events-none"
        style={{ left: `${Math.min(92, splitPct + 4)}%` }}
      >
        <div
          className="px-3 py-1 rounded-full text-xs font-bold tracking-wider"
          style={{
            background: "rgba(11,15,26,0.85)",
            border: "1px solid rgba(255,68,68,0.5)",
            color: "#FF4444",
            backdropFilter: "blur(8px)",
          }}
        >
          {afterLabel}
        </div>
      </div>

      {/* ── Divider line ─────────────────────────────────────────────── */}
      <div
        className="absolute top-0 bottom-0 z-20"
        style={{
          left: `${splitPct}%`,
          width: "3px",
          background: "linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,255,255,0.4))",
          boxShadow: "0 0 12px rgba(255,255,255,0.5)",
          cursor: "col-resize",
          transform: "translateX(-50%)",
        }}
        onMouseDown={(e) => { e.preventDefault(); setIsDragging(true); }}
        onTouchStart={() => setIsDragging(true)}
      >
        {/* Drag handle */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            background: "white",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 2px 12px rgba(0,0,0,0.4)",
            cursor: "col-resize",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M5 3L2 8L5 13" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M11 3L14 8L11 13" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </div>

      {/* ── Overlay: colour tint on each side ────────────────────────── */}
      <div
        className="absolute inset-0 z-5 pointer-events-none"
        style={{
          background: `linear-gradient(to right, rgba(0,229,180,0.06) 0%, transparent ${splitPct}%, rgba(255,68,68,0.06) ${splitPct}%, transparent 100%)`,
        }}
      />

      {/* ── Instructions tooltip ─────────────────────────────────────── */}
      <div
        className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 pointer-events-none"
        style={{ opacity: isDragging ? 0 : 0.8, transition: "opacity 0.3s" }}
      >
        <div
          className="px-3 py-1 rounded-full text-xs text-gray-400"
          style={{ background: "rgba(11,15,26,0.8)", backdropFilter: "blur(4px)" }}
        >
          ← Drag to compare →
        </div>
      </div>
    </div>
  );
}
