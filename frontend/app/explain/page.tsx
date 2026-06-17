"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, Eye, Cpu, Layers, CheckCircle } from "lucide-react";
import { segmentTile, explainTile, buildGraph, healGraph } from "@/lib/api";
import { b64ToDataUrl } from "@/lib/utils";

type Stage = "idle" | "segment" | "explain" | "build" | "heal" | "done";

interface Results {
  original?: string;
  mask?: string;
  confidence?: string;
  overlay?: string;
  roadPixelRatio?: number;
  connectivityRatio?: number;
}

export default function ExplainPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [results, setResults] = useState<Results>({});
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<keyof Results>("original");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setResults({});
    setStage("idle");
    setError(null);
    const reader = new FileReader();
    reader.onload = e => {
      const url = e.target?.result as string;
      setPreview(url);
      setResults({ original: url });
      setActiveView("original");
    };
    reader.readAsDataURL(f);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) handleFile(f);
  }, [handleFile]);

  const runPipeline = async () => {
    if (!file) return;
    setError(null);

    try {
      // Stage 1: Segment
      setStage("segment");
      const segResult = await segmentTile(file);
      const maskUrl = b64ToDataUrl(segResult.mask_b64);
      const confUrl = b64ToDataUrl(segResult.confidence_b64);
      setResults(r => ({ ...r, mask: maskUrl, confidence: confUrl, roadPixelRatio: segResult.road_pixel_ratio }));
      setActiveView("mask");

      // Stage 2: Explain
      setStage("explain");
      const expResult = await explainTile(file);
      setResults(r => ({ ...r, overlay: b64ToDataUrl(expResult.overlay_b64) }));

      // Stage 3: Build graph
      setStage("build");
      await buildGraph(segResult.mask_b64);

      // Stage 4: Heal
      setStage("heal");
      const healResult = await healGraph();
      setResults(r => ({ ...r, connectivityRatio: healResult.connectivity_ratio }));

      setStage("done");
      setActiveView("overlay");
    } catch (e: any) {
      setError(e.message);
      setStage("idle");
    }
  };

  const VIEWS: { key: keyof Results; label: string; available: boolean }[] = [
    { key: "original",    label: "Original",    available: !!results.original },
    { key: "mask",        label: "Road Mask",   available: !!results.mask },
    { key: "confidence",  label: "Confidence",  available: !!results.confidence },
    { key: "overlay",     label: "Grad-CAM",    available: !!results.overlay },
  ];

  return (
    <div className="min-h-screen bg-[#0B0F1A] p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center">
              <Eye className="w-4 h-4 text-[#00E5B4]" />
            </div>
            <h1 className="font-display text-2xl font-bold">Segmentation & Explainability</h1>
          </div>
          <p className="text-[#6B7280] text-sm">
            Upload a satellite tile → run road segmentation → inspect Grad-CAM saliency → build routable graph.
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* Left panel */}
          <div className="lg:col-span-2 space-y-4">
            {/* Upload area */}
            <div
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              onClick={() => inputRef.current?.click()}
              className="bg-[#111827] border-2 border-dashed border-white/10 rounded-xl p-8 text-center cursor-pointer hover:border-[#00E5B4]/30 hover:bg-[#1C2333] transition-all"
            >
              <input ref={inputRef} type="file" accept="image/*" className="hidden"
                onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }} />
              <Upload className="w-8 h-8 text-[#00E5B4] mx-auto mb-3" />
              <p className="text-sm text-white font-medium mb-1">
                {file ? file.name : "Drop satellite tile here"}
              </p>
              <p className="text-xs text-[#6B7280]">PNG, JPEG, or GeoTIFF · RGB · 256–1024px</p>
            </div>

            {/* Pipeline stages */}
            <div className="bg-[#111827] border border-white/8 rounded-xl p-5">
              <h3 className="font-display font-semibold text-sm mb-4">Pipeline Stages</h3>
              <div className="space-y-3">
                {STAGES.map((s, i) => {
                  const stageIdx = STAGE_ORDER.indexOf(s.id as Stage);
                  const currentIdx = STAGE_ORDER.indexOf(stage);
                  const isDone = stage === "done" || currentIdx > stageIdx;
                  const isActive = stage === s.id;
                  return (
                    <div key={s.id} className="flex items-center gap-3">
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0 transition-colors ${
                        isDone ? "bg-[#22C55E]/20 text-[#22C55E]" :
                        isActive ? "bg-[#00E5B4]/20 text-[#00E5B4]" :
                        "bg-white/5 text-[#6B7280]"
                      }`}>
                        {isDone ? <CheckCircle className="w-3.5 h-3.5" /> :
                         isActive ? <span className="w-2.5 h-2.5 rounded-full bg-[#00E5B4] animate-pulse" /> :
                         <span>{i + 1}</span>}
                      </div>
                      <div className="flex-1">
                        <div className={`text-xs font-medium ${isDone ? "text-[#22C55E]" : isActive ? "text-white" : "text-[#6B7280]"}`}>
                          {s.label}
                        </div>
                        <div className="text-xs text-[#6B7280]">{s.desc}</div>
                      </div>
                      <s.icon className={`w-3.5 h-3.5 ${isDone ? "text-[#22C55E]" : isActive ? "text-[#00E5B4] animate-spin" : "text-[#6B7280]"}`} />
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Metrics */}
            {(results.roadPixelRatio !== undefined || results.connectivityRatio !== undefined) && (
              <div className="bg-[#111827] border border-white/8 rounded-xl p-5 space-y-3">
                <h3 className="font-display font-semibold text-sm">Computed Metrics</h3>
                {results.roadPixelRatio !== undefined && (
                  <div className="flex justify-between text-sm">
                    <span className="text-[#6B7280]">Road pixel ratio</span>
                    <span className="font-mono text-white">{(results.roadPixelRatio * 100).toFixed(1)}%</span>
                  </div>
                )}
                {results.connectivityRatio !== undefined && (
                  <div className="flex justify-between text-sm">
                    <span className="text-[#6B7280]">Connectivity ratio (heal)</span>
                    <span className="font-mono text-[#22C55E]">{results.connectivityRatio.toFixed(3)}×</span>
                  </div>
                )}
              </div>
            )}

            <button
              onClick={runPipeline}
              disabled={!file || (stage !== "idle" && stage !== "done")}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-[#00E5B4] text-[#0B0F1A] font-display font-bold rounded-xl hover:bg-[#00B38A] transition-colors disabled:opacity-40"
            >
              <Cpu className="w-4 h-4" />
              {stage === "done" ? "Run Again" : stage === "idle" ? "Run Full Pipeline" : "Running…"}
            </button>

            {error && (
              <div className="bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-xl p-4 text-[#FF4444] text-xs">{error}</div>
            )}
          </div>

          {/* Image viewer */}
          <div className="lg:col-span-3">
            <div className="bg-[#111827] border border-white/8 rounded-xl overflow-hidden h-full min-h-[520px] flex flex-col">
              {/* View tabs */}
              <div className="flex border-b border-white/8 p-2 gap-1">
                {VIEWS.map(v => (
                  <button
                    key={v.key}
                    disabled={!v.available}
                    onClick={() => setActiveView(v.key)}
                    className={`px-3 py-1.5 rounded-md text-xs transition-colors ${
                      activeView === v.key && v.available
                        ? "bg-[#00E5B4]/15 text-[#00E5B4]"
                        : v.available
                        ? "text-[#6B7280] hover:text-white"
                        : "text-[#6B7280]/40 cursor-not-allowed"
                    }`}
                  >
                    {v.label}
                  </button>
                ))}
              </div>

              {/* Image display */}
              <div className="flex-1 flex items-center justify-center p-4 bg-[#0B0F1A]">
                <AnimatePresence mode="wait">
                  {results[activeView] && typeof results[activeView] === "string" ? (
                    <motion.img
                      key={activeView}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      src={results[activeView] as string}
                      alt={activeView}
                      className="max-w-full max-h-[440px] object-contain rounded-lg"
                      style={activeView !== "original" && activeView !== "overlay" ? { imageRendering: "pixelated" } : {}}
                    />
                  ) : (
                    <motion.div key="placeholder" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                      className="text-center text-[#6B7280]">
                      <Layers className="w-12 h-12 mx-auto mb-3 opacity-20" />
                      <p className="text-sm">{file ? "Upload an image and run the pipeline" : "Upload a satellite tile to get started"}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Legend */}
              {activeView === "overlay" && (
                <div className="px-4 py-3 border-t border-white/8 flex items-center gap-4 text-xs text-[#6B7280]">
                  <span className="font-semibold text-white">Grad-CAM:</span>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-blue-600" /> Low influence
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-green-500" /> Medium
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-red-500" /> High influence
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const STAGE_ORDER: Stage[] = ["idle", "segment", "explain", "build", "heal", "done"];

const STAGES = [
  { id: "segment", label: "Road Segmentation",       desc: "U-Net / Transformer forward pass",    icon: Cpu },
  { id: "explain", label: "Grad-CAM Explainability",  desc: "Saliency overlay generation",         icon: Eye },
  { id: "build",   label: "Graph Construction",       desc: "Skeletonize → NetworkX graph",        icon: Layers },
  { id: "heal",    label: "MST Topological Healing",  desc: "Bridge disconnected components",      icon: CheckCircle },
];
