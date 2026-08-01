"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Play, Clock, ChevronDown, RotateCcw } from "lucide-react";
import type { SearchResult, QueryHistoryItem, ScoreBreakdown } from "../types";
import { useScenarios } from "../hooks/useApi";

// ── SmartScoreBars ────────────────────────────────────────────────────────────
function SmartScoreBars({ sb }: { sb: ScoreBreakdown }) {
  const MONO: React.CSSProperties = {
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: "0.65rem",
    lineHeight: 1.6,
  };
  const BAR_LEN = 20;
  const FILLED = "#c4b8a5";
  const EMPTY = "#8a8275";

  const cats: [string, number, number, string | undefined][] = [
    ["Object",   sb.object_score,   40, sb.details.object],
    ["Color",    sb.color_score,    20, sb.details.color],
    ["Spatial",  sb.spatial_score,  20, sb.details.spatial],
    ["Negation", sb.negation_score, 20, sb.details.negation],
  ];

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ ...MONO, color: EMPTY, marginBottom: 2, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Score breakdown
      </div>
      {cats.map(([label, score, max, detail]) => {
        const filled = max > 0 ? Math.round((score / max) * BAR_LEN) : 0;
        const empty = BAR_LEN - filled;
        return (
          <div key={label} title={detail || ""} style={{ ...MONO, display: "flex", gap: 6, cursor: "help" }}>
            <span style={{ color: EMPTY, width: "4.5rem", flexShrink: 0 }}>{label}</span>
            <span>
              <span style={{ color: FILLED }}>{"█".repeat(filled)}</span>
              <span style={{ color: EMPTY }}>{"░".repeat(empty)}</span>
            </span>
            <span style={{ color: EMPTY }}>{score}/{max}</span>
          </div>
        );
      })}
      <div style={{ ...MONO, color: FILLED, textAlign: "right", marginTop: 2, fontWeight: 700 }}>
        Score: {sb.total}/100
      </div>
    </div>
  );
}

// ── ConfBadge ─────────────────────────────────────────────────────────────────
function ConfBadge({ score }: { score: number }) {
  const isHigh = score >= 0.75;
  const isMed = score >= 0.50;
  const label = isHigh ? "HIGH" : isMed ? "MED" : "LOW";
  const color = isHigh ? "#10b981" : isMed ? "#f59e0b" : "#ef4444";
  const bg    = isHigh ? "rgba(16,185,129,0.12)" : isMed ? "rgba(245,158,11,0.12)" : "rgba(239,68,68,0.12)";
  return (
    <span style={{
      background: bg, color, border: `1px solid ${color}`,
      padding: "2px 8px", borderRadius: 20,
      fontFamily: "'JetBrains Mono', monospace", fontSize: "0.68rem",
      fontWeight: 700, letterSpacing: "0.4px", textTransform: "uppercase",
    }}>
      {label} {score.toFixed(2)}
    </span>
  );
}

// ── ProcessingLog ─────────────────────────────────────────────────────────────
// Mirrors the Gradio log-container with colored step lines
function ProcessingLog({ steps }: { steps: Array<{ cls: string; text: string }> }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [steps]);

  const clsColor: Record<string, string> = {
    pass: "#10b981",
    fail: "#ef4444",
    info: "#818cf8",
    warn: "#f59e0b",
    muted: "#475569",
  };

  return (
    <div style={{
      background: "#080812",
      border: "1px solid #1a1a2e",
      borderRadius: 10,
      padding: "14px 16px",
      height: 300,
      overflowY: "auto",
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: "0.78rem",
      lineHeight: 1.8,
      color: "#94a3b8",
    }}>
      {steps.length === 0 && (
        <span style={{ color: "#475569" }}>⌛ Waiting for a query…</span>
      )}
      {steps.map((s, i) => (
        <div key={i} style={{ color: clsColor[s.cls] ?? "#94a3b8", padding: "1px 0" }}
          dangerouslySetInnerHTML={{ __html: s.text }} />
      ))}
      <div ref={endRef} />
    </div>
  );
}

// ── IngestStats ───────────────────────────────────────────────────────────────
// Renders the Stats JSON panel (scenes / keyframes / objects / collection)
function IngestStats({ stats }: { stats: Record<string, unknown> | null }) {
  if (!stats) return null;
  const entries = Object.entries(stats);
  return (
    <div style={{
      background: "#0c0c1e",
      border: "1px solid #1a1a35",
      borderRadius: 8,
      padding: "10px 14px",
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: "0.75rem",
      color: "#94a3b8",
      marginTop: 12,
    }}>
      <div style={{ color: "#475569", fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
        Stats
      </div>
      {entries.map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
          <span style={{ color: "#64748b" }}>{k}</span>
          <span style={{ color: "#c7d2fe" }}>{String(v)}</span>
        </div>
      ))}
    </div>
  );
}

// ── DetectedObjectsSummary ────────────────────────────────────────────────────
// Mirrors the Gradio ingest_summary HTML panel
const OBJ_EMOJI: Record<string, string> = {
  person: "🚶", car: "🚗", truck: "🚚", bus: "🚌", bicycle: "🚲",
  motorcycle: "🏍", dog: "🐕", cat: "🐈", chair: "🪑", bottle: "🍶",
  laptop: "💻", "cell phone": "📱", backpack: "🎒", umbrella: "☂",
  "traffic light": "🚦", "stop sign": "🛑", bench: "🪑",
};

function DetectedObjectsSummary({ tally }: { tally: Record<string, Record<string, number>> | null }) {
  if (!tally || Object.keys(tally).length === 0) return null;
  const sorted = Object.entries(tally)
    .sort(([, a], [, b]) => Object.values(b).reduce((s, v) => s + v, 0) - Object.values(a).reduce((s, v) => s + v, 0))
    .slice(0, 20);

  return (
    <div style={{
      maxHeight: 200, overflowY: "auto",
      background: "#0f172a",
      border: "1px solid #334155",
      borderRadius: 8,
      padding: "8px 10px",
      marginTop: 12,
    }}>
      <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Objects detected in this video
      </div>
      {sorted.map(([cls, colorMap]) => {
        const total = Object.values(colorMap).reduce((s, v) => s + v, 0);
        const colorParts = Object.entries(colorMap)
          .filter(([c]) => c !== "unknown")
          .sort(([, a], [, b]) => b - a)
          .map(([c, n]) => `${c}(${n})`)
          .join(", ");
        return (
          <div key={cls} style={{
            padding: "3px 8px", borderRadius: 6, margin: "2px 0",
            background: "#1e293b", fontSize: "0.82rem", color: "#e2e8f0",
          }}>
            {OBJ_EMOJI[cls] ?? "📦"} <b>{cls}</b>{" "}
            <span style={{ color: "#94a3b8" }}>×{total}{colorParts ? ` — ${colorParts}` : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── ResultPickerDropdown ──────────────────────────────────────────────────────
// Mirrors Gradio result_picker: "Jump to result (click to seek video)"
interface PickerOption { label: string; value: string; }
interface ResultPickerProps {
  options: PickerOption[];
  onSelect: (videoId: string, timestamp: number) => void;
}
function ResultPickerDropdown({ options, onSelect }: ResultPickerProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (options.length === 0) return null;

  const handlePick = (opt: PickerOption) => {
    setSelected(opt.label);
    setOpen(false);
    const parts = opt.value.split(":::");
    const vid = parts[0]?.trim() || "";
    const ts = parseFloat(parts[1]?.trim() || "0");
    onSelect(vid, isNaN(ts) ? 0 : ts);
  };

  return (
    <div ref={ref} style={{ position: "relative", marginTop: 16 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", textAlign: "left",
          background: "#0c0c1e", border: "1px solid #1e1e3f",
          borderRadius: 8, padding: "10px 14px",
          color: selected ? "#c7d2fe" : "#475569",
          fontFamily: "'JetBrains Mono', monospace", fontSize: "0.82rem",
          cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
        }}
      >
        <span>{selected ?? "▶ Jump to result (click to seek video)"}</span>
        <ChevronDown size={16} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            style={{
              position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50,
              background: "#0c0c1e", border: "1px solid #1e1e3f", borderRadius: 8,
              overflow: "hidden", maxHeight: 260, overflowY: "auto",
            }}
          >
            {options.map(opt => (
              <button key={opt.value} onClick={() => handlePick(opt)}
                style={{
                  width: "100%", textAlign: "left", display: "block",
                  padding: "9px 14px", background: "transparent",
                  border: "none", borderBottom: "1px solid #1a1a2e",
                  color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "0.78rem", cursor: "pointer",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "#1a1a3e")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                {opt.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Props interface ───────────────────────────────────────────────────────────
interface Props {
  onIngestComplete: (collection: string) => void;
  ingestStatus: "idle" | "running" | "complete" | "error";
  ingestProgress: number;
  ingestLogs: string[];
  ingestStats: Record<string, unknown> | null;
  ingestObjectTally: Record<string, Record<string, number>> | null;
  startIngest: (path: string) => Promise<string | null>;
  onSearch: (query: string) => void;
  queryLoading: boolean;
  processLog: Array<{ cls: string; text: string }>;
  vocabWarnings: Array<{ token: string; suggestion?: string }>;
  disabled?: boolean;
  results: SearchResult[];
  diagnosis: { html: string; best_score: number } | null;
  showDiagnosis: boolean;
  currentQuery: string;
  selectedVideo: { path: string; timestamp: number } | null;
  onResultSelect: (videoPath: string, timestamp: number) => void;
  history: QueryHistoryItem[];
  onHistoryReplay: (query: string) => void;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function InteractiveDemo({
  onIngestComplete, ingestStatus, ingestProgress, ingestLogs, ingestStats,
  ingestObjectTally, startIngest,
  onSearch, queryLoading, processLog, vocabWarnings, disabled, results, diagnosis,
  showDiagnosis, currentQuery, selectedVideo, onResultSelect, history, onHistoryReplay,
}: Props) {
  const [query, setQuery] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const { scenarios } = useScenarios();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Seek video to timestamp when selectedVideo changes
  useEffect(() => {
    if (videoRef.current && selectedVideo) {
      videoRef.current.currentTime = selectedVideo.timestamp;
      videoRef.current.play().catch(() => {/* autoplay may be blocked */});
    }
  }, [selectedVideo]);

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragOver(true); }, []);
  const handleDragLeave = useCallback(() => setIsDragOver(false), []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault(); setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file?.type.startsWith("video/")) {
      setFileName(file.name);
      const col = await startIngest(file.name);
      if (col) onIngestComplete(col);
    }
  }, [startIngest, onIngestComplete]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFileName(file.name);
      const col = await startIngest(file.name);
      if (col) onIngestComplete(col);
    }
  }, [startIngest, onIngestComplete]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !queryLoading) onSearch(query.trim());
  };

  // Build result picker options from current results
  const pickerOptions: Array<{ label: string; value: string }> = results.map((r, i) => {
    const conf = r.confidence_score >= 0.75 ? "HIGH" : r.confidence_score >= 0.50 ? "MED" : "LOW";
    return {
      label: `${i + 1}. ${r.video_id} @ ${r.timestamp.toFixed(1)}s  [${conf} ${r.confidence_score.toFixed(2)}]`,
      value: `${r.video_id}:::${r.timestamp}`,
    };
  });

  return (
    <section id="demo" className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <span className="sd-label block mb-8">Demo</span>
        <h2 className="sd-headline-mid text-cream-100 mb-6">Try it live.</h2>
        <p className="sd-body-large mb-20 max-w-2xl">
          Upload a video. Ask a question. Watch the system prove every match.
        </p>

        {/* ── Upload Zone ─────────────────────────────────────────────── */}
        <div className="mb-16">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`
              relative aspect-[21/9] flex items-center justify-center border transition-all duration-500
              ${isDragOver ? "border-sand bg-sand/5" : "border-white/10 hover:border-white/20"}
              ${ingestStatus === "running" ? "pointer-events-none" : ""}
            `}
          >
            <input type="file" accept="video/*" onChange={handleFileSelect}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
              disabled={ingestStatus === "running"} />
            <AnimatePresence mode="wait">
              {ingestStatus === "idle" && (
                <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-center">
                  <p className="font-serif text-2xl md:text-4xl text-cream-100 italic mb-3">
                    {isDragOver ? "Release to ingest" : "Drop video here"}
                  </p>
                  <p className="sd-mono">MP4 · MOV · AVI · MKV · Max 3 min</p>
                </motion.div>
              )}
              {ingestStatus === "running" && (
                <motion.div key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="w-full max-w-lg px-8">
                  <div className="flex justify-between items-end mb-4">
                    <span className="font-serif text-2xl text-cream-100">Ingesting</span>
                    <span className="font-serif text-4xl text-sand">{ingestProgress}%</span>
                  </div>
                  <div className="h-px bg-white/10 relative">
                    <motion.div className="absolute inset-y-0 left-0 bg-sand" animate={{ width: `${ingestProgress}%` }} transition={{ duration: 0.3 }} />
                  </div>
                  {/* Full scrollable log — all lines, not just last 3 */}
                  <div style={{
                    marginTop: 16, maxHeight: 120, overflowY: "auto",
                    fontFamily: "'JetBrains Mono', monospace", fontSize: "0.72rem",
                    color: "#94a3b8", lineHeight: 1.7,
                  }}>
                    {ingestLogs.map((l, i) => <div key={i}>{l}</div>)}
                  </div>
                </motion.div>
              )}
              {ingestStatus === "complete" && (
                <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
                  <p className="font-serif text-3xl text-cream-100 italic mb-2">Ready.</p>
                  <p className="sd-mono">{fileName} · Indexed</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Stats JSON + Detected Objects Summary — shown after ingestion */}
          {(ingestStats || ingestObjectTally) && ingestStatus !== "idle" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <IngestStats stats={ingestStats} />
              <DetectedObjectsSummary tally={ingestObjectTally} />
            </motion.div>
          )}
        </div>

        {/* ── Query ───────────────────────────────────────────────────── */}
        <div className="mb-16">
          <span className="sd-label block mb-8">Query</span>
          <form onSubmit={handleSubmit}>
            <div className="relative">
              <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder={disabled ? "Upload a video first..." : "person without helmet left of blue car"}
                disabled={disabled || queryLoading}
                className="w-full bg-transparent border-0 border-b border-white/10 focus:border-sand pb-4 pt-2 font-serif text-2xl md:text-4xl text-cream-100 placeholder:text-cream-800 outline-none transition-colors duration-500 pr-16" />
              <button type="submit" disabled={!query.trim() || queryLoading || disabled}
                className="absolute right-0 bottom-4 text-cream-700 hover:text-sand disabled:opacity-30 transition-colors">
                {queryLoading
                  ? <span className="sd-mono text-sm animate-pulse">Searching…</span>
                  : <ArrowRight className="w-8 h-8" />}
              </button>
            </div>
          </form>

          {/* Vocab warnings */}
          <AnimatePresence>
            {vocabWarnings.length > 0 && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                style={{ marginTop: 12, background: "#451a03", border: "1px solid #f59e0b", color: "#fef3c7", padding: "10px 14px", borderRadius: 8, fontSize: "0.88rem" }}>
                {vocabWarnings.map((w, i) => (
                  <div key={i}>
                    {w.suggestion ? `⚠️ "${w.token}" — did you mean "${w.suggestion}"?` : `⚠️ "${w.token}" not recognized — try a different term.`}
                  </div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Scenario Presets */}
          <div className="flex flex-wrap gap-3 mt-8 mb-2">
            {scenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => { setQuery(s.query); onSearch(s.query); }}
                disabled={disabled || queryLoading}
                title={s.query}
                className="text-xs px-3 py-1.5 border transition-all duration-300 disabled:opacity-30"
                style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace", borderColor: "rgba(255,255,255,0.1)", color: "#8a8275" }}
                onMouseEnter={e => { (e.currentTarget).style.borderColor = "#c4b8a5"; (e.currentTarget).style.color = "#c4b8a5"; }}
                onMouseLeave={e => { (e.currentTarget).style.borderColor = "rgba(255,255,255,0.1)"; (e.currentTarget).style.color = "#8a8275"; }}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Quick-query chips */}
          <div className="flex flex-wrap gap-6 mt-4">
            {["person in red", "person without helmet", "two people", "person left of car", "car in dark blue"].map((s) => (
              <button key={s} onClick={() => { setQuery(s); onSearch(s); }} disabled={disabled || queryLoading}
                className="sd-mono hover:text-cream-100 transition-colors disabled:opacity-30">
                {s} →
              </button>
            ))}
          </div>
        </div>

        {/* ── Processing Log + Results (2-column layout like Gradio) ─── */}
        <AnimatePresence>
          {(processLog.length > 0 || results.length > 0 || queryLoading) && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="mb-16 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-8">

              {/* LEFT: Processing Log */}
              <div>
                <span className="sd-label block mb-4">Processing Log</span>
                <ProcessingLog steps={processLog} />
              </div>

              {/* RIGHT: Result Cards + Picker */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="sd-label">
                    {results.length > 0
                      ? `${results.length} Result${results.length !== 1 ? "s" : ""} for "${currentQuery}"`
                      : queryLoading ? "Processing…" : "Results"}
                  </span>
                </div>

                {/* Scrollable result cards — vertical list like Gradio, not horizontal strip */}
                {results.length > 0 && (
                  <div style={{ maxHeight: 460, overflowY: "auto", paddingRight: 4 }}>
                    {results.map((r, i) => {
                      const bbox = r.matched_objects[0]?.bbox;
                      return (
                        <div key={i} style={{
                          background: "linear-gradient(135deg, #0d0d20 0%, #11112a 100%)",
                          border: "1px solid #1e1e3f", borderRadius: 12,
                          padding: 14, marginBottom: 12,
                        }}>
                          {/* Header */}
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "#c7d2fe" }}>📹 {r.video_id}</span>
                            <ConfBadge score={r.confidence_score} />
                          </div>

                          {/* Meta */}
                          <div style={{ fontSize: "0.75rem", color: "#64748b", marginBottom: 8 }}>
                            ⏱ {r.timestamp.toFixed(1)}s &nbsp;·&nbsp; Scene {r.scene_id} &nbsp;·&nbsp; {r.matched_objects.length} object(s)
                          </div>

                          {/* Thumbnail placeholder with bbox overlay */}
                          <div style={{
                            width: "100%", height: 88,
                            background: "linear-gradient(135deg, #0f0f20, #161630)",
                            borderRadius: 8, border: "1px dashed #1e1e3f",
                            position: "relative", overflow: "hidden", marginBottom: 10,
                            display: "flex", alignItems: "center", justifyContent: "center",
                          }}>
                            <span style={{ fontSize: 28, opacity: 0.6 }}>🎬</span>
                            {r.matched_objects.slice(0, 3).map((obj, j) => {
                              const b = obj.bbox || [0.1 + j * 0.25, 0.2, 0.35 + j * 0.25, 0.6];
                              return (
                                <div key={j} style={{
                                  position: "absolute",
                                  left: `${b[0] * 100}%`, top: `${b[1] * 100}%`,
                                  width: `${Math.max((b[2] - b[0]) * 100, 5)}%`,
                                  height: `${Math.max((b[3] - b[1]) * 100, 5)}%`,
                                  border: "2px solid rgba(99,102,241,0.7)",
                                  borderRadius: 3, background: "rgba(99,102,241,0.08)",
                                }} />
                              );
                            })}
                          </div>

                          {/* BBox text tags (like Gradio) */}
                          {r.matched_objects.slice(0, 3).map((obj, j) => {
                            if (!obj.bbox) return null;
                            const bStr = obj.bbox.map(v => v.toFixed(2)).join(", ");
                            return (
                              <div key={j} style={{
                                fontFamily: "'JetBrains Mono', monospace", fontSize: "0.7rem",
                                color: "#94a3b8", background: "rgba(0,0,0,0.4)",
                                padding: "3px 8px", borderRadius: 4, margin: "2px 0",
                                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                              }}>
                                {obj.class_name}/{obj.color ?? "?"}: [{bStr}]
                              </div>
                            );
                          })}

                          {/* Explanation */}
                          {r.explanation && (
                            <p style={{ fontSize: "0.78rem", color: "#cbd5e1", fontStyle: "italic", lineHeight: 1.5, marginTop: 6, paddingTop: 6, borderTop: "1px solid #1e1e3f" }}>
                              💡 {r.explanation}
                            </p>
                          )}

                          {/* Smart Score Bars */}
                          {r.score_breakdown && <SmartScoreBars sb={r.score_breakdown} />}

                          {/* Click-to-seek hint */}
                          <button
                            onClick={() => onResultSelect(r.video_id, r.timestamp)}
                            style={{
                              marginTop: 8, width: "100%", textAlign: "right",
                              color: "#64748b", fontSize: "0.68rem", background: "none",
                              border: "none", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                            }}
                          >
                            🔽 Click to seek video
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Result Picker Dropdown */}
                {results.length > 0 && (
                  <ResultPickerDropdown options={pickerOptions} onSelect={onResultSelect} />
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Video Player ─────────────────────────────────────────────── */}
        <AnimatePresence>
          {selectedVideo && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mb-16">
              <span className="sd-label block mb-4">Video Player</span>
              <div style={{ background: "#08080f", border: "1px solid #1a1a2e", borderRadius: 12, padding: 16 }}>
                <video
                  ref={videoRef}
                  src={selectedVideo.path}
                  className="w-full"
                  style={{ borderRadius: 8, background: "#000", maxHeight: 480 }}
                  controls
                />
                <div className="flex items-center gap-4 mt-3">
                  <Clock className="w-4 h-4 text-cream-800" />
                  <span className="sd-mono">Seeking to {selectedVideo.timestamp.toFixed(1)}s</span>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* No-match Diagnosis */}
        <AnimatePresence>
          {showDiagnosis && diagnosis && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mb-16 border-l border-white/10 pl-8 py-4">
              <span className="sd-label block mb-4">Diagnosis</span>
              <h3 className="font-serif text-2xl text-cream-100 mb-4">No confident match.</h3>
              <p className="text-cream-600 mb-8 max-w-2xl">We found related objects, but nothing satisfied all constraints together.</p>
              <div className="mb-8">
                <div className="flex justify-between text-xs font-mono text-cream-700 mb-2">
                  <span>Best partial score</span>
                  <span className="text-sand">{diagnosis.best_score.toFixed(3)}</span>
                </div>
                <div className="h-px bg-white/10 relative">
                  <motion.div className="absolute inset-y-0 left-0 bg-sand" initial={{ width: 0 }} animate={{ width: `${Math.min(diagnosis.best_score * 100, 100)}%` }} transition={{ duration: 1.5 }} />
                </div>
                <div className="flex justify-between text-[10px] font-mono text-cream-800 mt-1">
                  <span>0.0</span><span>Threshold 0.320</span><span>1.0</span>
                </div>
              </div>
              <div className="prose prose-invert prose-sm max-w-none prose-p:text-cream-600 prose-strong:text-cream-300 prose-code:text-sand prose-code:bg-transparent"
                dangerouslySetInnerHTML={{ __html: diagnosis.html }} />
              <div className="mt-8 pt-6 border-t border-white/5">
                <p className="sd-mono"><span className="text-sand">Tip:</span> Try removing one constraint. Search for just "person" or just "helmet".</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Query History ──────────────────────────────────────────── */}
        {history.length > 0 && (
          <div className="border-t border-white/5 pt-12">
            <span className="sd-label block mb-6">Session Query History</span>
            <div style={{ maxHeight: 280, overflowY: "auto", paddingRight: 4 }}>
              {history.map((item, idx) => (
                <div key={idx} style={{
                  background: "#0f172a", border: "1px solid #1e293b", borderRadius: 6,
                  padding: "8px 12px", marginBottom: 6, fontSize: "0.85rem", color: "#cbd5e1",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                  <div>
                    <b style={{ color: "#f8fafc" }}>Q: {item.query_text}</b>
                    <span style={{ color: "#64748b", margin: "0 6px" }}>|</span>
                    <span>{item.result_count} result{item.result_count !== 1 ? "s" : ""}</span>
                    <span style={{ color: "#64748b", margin: "0 6px" }}>|</span>
                    <span>score {item.top_score.toFixed(2)}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: "#64748b", fontSize: "0.75rem" }}>{item.timestamp}</span>
                    <button
                      onClick={() => { setQuery(item.query_text); onHistoryReplay(item.query_text); }}
                      style={{
                        background: "#3b82f6", color: "#fff",
                        padding: "2px 8px", borderRadius: 4,
                        fontSize: "0.75rem", fontWeight: 500, border: "none", cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 4,
                      }}
                    >
                      <RotateCcw size={10} /> Re-run
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
