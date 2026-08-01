"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, ChevronDown, RotateCcw, Play } from "lucide-react";
import type { SearchResult, QueryHistoryItem, ScoreBreakdown, ProcessLogStep } from "../types";
import { useScenarios } from "../hooks/useApi";

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens — mirrors Gradio CUSTOM_CSS colour system
// ─────────────────────────────────────────────────────────────────────────────
const C = {
  bg:           "#07070f",
  panel:        "#0c0c1e",
  panelBorder:  "#1a1a35",
  logBg:        "#080812",
  logBorder:    "#1a1a2e",
  indigo:       "#818cf8",
  indigoDark:   "#6366f1",
  indigoFaint:  "rgba(99,102,241,0.15)",
  purple:       "#c084fc",
  white:        "#e2e8f0",
  muted:        "#94a3b8",
  dim:          "#64748b",
  dimmer:       "#475569",
  green:        "#10b981",
  amber:        "#f59e0b",
  red:          "#ef4444",
  cyan:         "#c7d2fe",
};

const MONO: React.CSSProperties = {
  fontFamily: "'JetBrains Mono','Fira Code',monospace",
};

// ─────────────────────────────────────────────────────────────────────────────
// SmartScoreBars
// ─────────────────────────────────────────────────────────────────────────────
function SmartScoreBars({ sb }: { sb: ScoreBreakdown }) {
  const BAR_LEN = 20;
  const cats: [string, number, number, string | undefined][] = [
    ["Object",   sb.object_score,   40, sb.details.object],
    ["Color",    sb.color_score,    20, sb.details.color],
    ["Spatial",  sb.spatial_score,  20, sb.details.spatial],
    ["Negation", sb.negation_score, 20, sb.details.negation],
  ];
  return (
    <div style={{ marginTop: 8, padding: "8px 10px", background: "rgba(15,23,42,0.7)", border: "1px solid #1e1e3f", borderRadius: 8 }}>
      <div style={{ ...MONO, fontSize: "0.67rem", color: C.indigo, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
        Score Breakdown
      </div>
      {cats.map(([label, score, max, detail]) => {
        const filled = max > 0 ? Math.round((score / max) * BAR_LEN) : 0;
        return (
          <div key={label} title={detail ?? ""} style={{ ...MONO, fontSize: "0.72rem", display: "flex", gap: 8, cursor: "help", color: C.muted }}>
            <span style={{ width: "4.5rem", flexShrink: 0, color: C.dim }}>{label}</span>
            <span>
              <span style={{ color: "#c4b8a5" }}>{"█".repeat(filled)}</span>
              <span style={{ color: "#334155" }}>{"░".repeat(BAR_LEN - filled)}</span>
            </span>
            <span>{score}/{max}</span>
          </div>
        );
      })}
      <div style={{ ...MONO, fontSize: "0.75rem", color: C.purple, textAlign: "right", marginTop: 4, fontWeight: 700 }}>
        Score: {sb.total}/100
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ConfBadge — HIGH / MED / LOW
// ─────────────────────────────────────────────────────────────────────────────
function ConfBadge({ score }: { score: number }) {
  const isHigh = score >= 0.75, isMed = score >= 0.50;
  const label = isHigh ? "HIGH" : isMed ? "MED" : "LOW";
  const color = isHigh ? C.green : isMed ? C.amber : C.red;
  const bg    = isHigh ? "rgba(16,185,129,0.12)" : isMed ? "rgba(245,158,11,0.12)" : "rgba(239,68,68,0.12)";
  return (
    <span style={{ ...MONO, background: bg, color, border: `1px solid ${color}`, padding: "2px 10px", borderRadius: 20, fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.4px", textTransform: "uppercase" }}>
      {label} {score.toFixed(2)}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SectionLabel — panel headings (mimics Gradio .panel-label)
// ─────────────────────────────────────────────────────────────────────────────
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: "0.75rem", fontWeight: 600, color: C.dimmer, textTransform: "uppercase", letterSpacing: "0.8px", padding: "12px 0 6px" }}>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ProcessingLog
// ─────────────────────────────────────────────────────────────────────────────
const CLS_COLOR: Record<string, string> = {
  pass: C.green, fail: C.red, info: C.indigo, warn: C.amber, muted: C.dimmer,
};
function ProcessingLog({ steps }: { steps: ProcessLogStep[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [steps]);
  return (
    <div style={{
      ...MONO,
      background: C.logBg, border: `1px solid ${C.logBorder}`,
      borderRadius: 10, padding: "14px 16px",
      height: 420, overflowY: "auto",
      fontSize: "0.82rem", lineHeight: 1.8, color: C.muted,
    }}>
      {steps.length === 0
        ? <span style={{ color: C.dimmer }}>⌛ Waiting for a query…</span>
        : steps.map((s, i) => (
            <div key={i} style={{ color: CLS_COLOR[s.cls] ?? C.muted, padding: "1px 0" }}
              dangerouslySetInnerHTML={{ __html: s.text }} />
          ))}
      <div ref={endRef} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// IngestStats  (scenes / keyframes / objects / collection)
// ─────────────────────────────────────────────────────────────────────────────
function IngestStats({ stats }: { stats: Record<string, unknown> | null }) {
  if (!stats) return null;
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.panelBorder}`, borderRadius: 8, padding: "10px 14px", marginTop: 10 }}>
      <div style={{ fontSize: "0.65rem", color: C.dimmer, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6, ...MONO }}>Stats</div>
      {Object.entries(stats).map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", ...MONO, fontSize: "0.78rem", padding: "2px 0" }}>
          <span style={{ color: C.dim }}>{k}</span>
          <span style={{ color: C.cyan }}>{String(v)}</span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectedObjectsSummary
// ─────────────────────────────────────────────────────────────────────────────
const OBJ_EMOJI: Record<string, string> = {
  person: "🚶", car: "🚗", truck: "🚚", bus: "🚌", bicycle: "🚲",
  motorcycle: "🏍", dog: "🐕", cat: "🐈", chair: "🪑", bottle: "🍶",
  laptop: "💻", "cell phone": "📱", backpack: "🎒", umbrella: "☂",
  "traffic light": "🚦", "stop sign": "🛑",
};
function DetectedObjectsSummary({ tally }: { tally: Record<string, Record<string, number>> | null }) {
  if (!tally || !Object.keys(tally).length) return null;
  const sorted = Object.entries(tally)
    .sort(([, a], [, b]) => Object.values(b).reduce((s,v)=>s+v,0) - Object.values(a).reduce((s,v)=>s+v,0))
    .slice(0, 20);
  return (
    <div style={{ maxHeight: 220, overflowY: "auto", background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: "8px 10px", marginTop: 10 }}>
      <div style={{ ...MONO, fontSize: "0.65rem", color: C.dim, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Objects detected in this video</div>
      {sorted.map(([cls, colorMap]) => {
        const total = Object.values(colorMap).reduce((s,v)=>s+v,0);
        const parts = Object.entries(colorMap).filter(([c])=>c!=="unknown").sort(([,a],[,b])=>b-a).map(([c,n])=>`${c}(${n})`).join(", ");
        return (
          <div key={cls} style={{ padding: "3px 8px", borderRadius: 6, margin: "2px 0", background: "#1e293b", fontSize: "0.87rem", color: C.white }}>
            {OBJ_EMOJI[cls]??"📦"} <b>{cls}</b> <span style={{ color: C.muted }}>×{total}{parts ? ` — ${parts}` : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ResultPickerDropdown — "▶ Jump to result (click to seek video)"
// ─────────────────────────────────────────────────────────────────────────────
interface PickerOpt { label: string; value: string; }
function ResultPickerDropdown({ options, onSelect }: { options: PickerOpt[]; onSelect: (vid: string, ts: number) => void }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  if (!options.length) return null;

  const pick = (opt: PickerOpt) => {
    setSelected(opt.label); setOpen(false);
    const [vid, tsRaw] = opt.value.split(":::");
    onSelect(vid?.trim() ?? "", parseFloat(tsRaw?.trim() ?? "0") || 0);
  };

  return (
    <div ref={ref} style={{ position: "relative", marginTop: 12 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        width: "100%", textAlign: "left",
        background: C.panel, border: `1px solid ${C.panelBorder}`,
        borderRadius: 8, padding: "10px 14px",
        color: selected ? C.cyan : C.dimmer,
        ...MONO, fontSize: "0.82rem",
        cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span>{selected ?? "▶  Jump to result (click to seek video)"}</span>
        <ChevronDown size={14} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s", color: C.dim }} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50, background: C.panel, border: `1px solid ${C.panelBorder}`, borderRadius: 8, overflow: "hidden", maxHeight: 240, overflowY: "auto" }}>
            {options.map(opt => (
              <button key={opt.value} onClick={() => pick(opt)}
                style={{ width: "100%", textAlign: "left", display: "block", padding: "9px 14px", background: "transparent", border: "none", borderBottom: "1px solid #1a1a2e", color: C.muted, ...MONO, fontSize: "0.78rem", cursor: "pointer" }}
                onMouseEnter={e => (e.currentTarget.style.background = "#1a1a3e")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                {opt.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ResultCard — mirrors Gradio render_result_card()
// ─────────────────────────────────────────────────────────────────────────────
function ResultCard({ r, onSeek }: { r: SearchResult; onSeek: () => void }) {
  return (
    <div style={{ background: "linear-gradient(135deg,#0d0d20 0%,#11112a 100%)", border: "1px solid #1e1e3f", borderRadius: 12, padding: 14, marginBottom: 12 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontWeight: 600, fontSize: "0.88rem", color: C.cyan }}>📹 {r.video_id}</span>
        <ConfBadge score={r.confidence_score} />
      </div>
      {/* Meta */}
      <div style={{ fontSize: "0.75rem", color: C.dim, marginBottom: 8 }}>
        ⏱ {r.timestamp.toFixed(1)}s &nbsp;·&nbsp; Scene {r.scene_id} &nbsp;·&nbsp; {r.matched_objects.length} object(s)
      </div>
      {/* Thumbnail with bbox overlays */}
      <div style={{ width: "100%", height: 88, background: "linear-gradient(135deg,#0f0f20,#161630)", borderRadius: 8, border: "1px dashed #1e1e3f", position: "relative", overflow: "hidden", marginBottom: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: 28, opacity: 0.6 }}>🎬</span>
        {r.matched_objects.slice(0, 3).map((obj, j) => {
          const b = obj.bbox ?? [0.1 + j * 0.25, 0.2, 0.35 + j * 0.25, 0.6];
          return <div key={j} style={{ position: "absolute", left: `${b[0]*100}%`, top: `${b[1]*100}%`, width: `${Math.max((b[2]-b[0])*100,5)}%`, height: `${Math.max((b[3]-b[1])*100,5)}%`, border: "2px solid rgba(99,102,241,0.7)", borderRadius: 3, background: "rgba(99,102,241,0.08)" }} />;
        })}
      </div>
      {/* BBox text tags */}
      {r.matched_objects.slice(0, 3).map((obj, j) => !obj.bbox ? null : (
        <div key={j} style={{ ...MONO, fontSize: "0.7rem", color: C.muted, background: "rgba(0,0,0,0.4)", padding: "3px 8px", borderRadius: 4, margin: "2px 0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {obj.class_name}/{obj.color ?? "?"}: [{obj.bbox.map(v => v.toFixed(2)).join(", ")}]
        </div>
      ))}
      {/* Explanation */}
      {r.explanation && (
        <p style={{ fontSize: "0.78rem", color: "#cbd5e1", fontStyle: "italic", lineHeight: 1.5, marginTop: 6, paddingTop: 6, borderTop: "1px solid #1e1e3f" }}>
          💡 {r.explanation}
        </p>
      )}
      {/* Score bars */}
      {r.score_breakdown && <SmartScoreBars sb={r.score_breakdown} />}
      {/* Seek hint */}
      <button onClick={onSeek} style={{ marginTop: 8, width: "100%", textAlign: "right", color: C.dimmer, fontSize: "0.68rem", background: "none", border: "none", cursor: "pointer", ...MONO }}>
        🔽 Click to seek video
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────
interface Props {
  onIngestComplete:  (col: string) => void;
  ingestStatus:      "idle" | "running" | "complete" | "error";
  ingestProgress:    number;
  ingestLogs:        string[];
  ingestStats:       Record<string, unknown> | null;
  ingestObjectTally: Record<string, Record<string, number>> | null;
  startIngest:       (path: string) => Promise<string | null>;
  onSearch:          (query: string) => void;
  queryLoading:      boolean;
  processLog:        ProcessLogStep[];
  vocabWarnings:     Array<{ token: string; suggestion?: string }>;
  disabled?:         boolean;
  results:           SearchResult[];
  diagnosis:         { html: string; best_score: number } | null;
  showDiagnosis:     boolean;
  currentQuery:      string;
  selectedVideo:     { path: string; timestamp: number } | null;
  onResultSelect:    (videoPath: string, timestamp: number) => void;
  history:           QueryHistoryItem[];
  onHistoryReplay:   (query: string) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// InteractiveDemo — main export
// ─────────────────────────────────────────────────────────────────────────────
export default function InteractiveDemo({
  onIngestComplete, ingestStatus, ingestProgress, ingestLogs, ingestStats,
  ingestObjectTally, startIngest,
  onSearch, queryLoading, processLog, vocabWarnings, disabled,
  results, diagnosis, showDiagnosis, currentQuery,
  selectedVideo, onResultSelect, history, onHistoryReplay,
}: Props) {
  const [query, setQuery] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const { scenarios } = useScenarios();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Seek on result select
  useEffect(() => {
    if (videoRef.current && selectedVideo) {
      videoRef.current.currentTime = selectedVideo.timestamp;
      videoRef.current.play().catch(() => {});
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

  const pickerOptions = results.map((r, i) => ({
    label: `${i + 1}. ${r.video_id} @ ${r.timestamp.toFixed(1)}s  [${r.confidence_score >= 0.75 ? "HIGH" : r.confidence_score >= 0.50 ? "MED" : "LOW"} ${r.confidence_score.toFixed(2)}]`,
    value: `${r.video_id}:::${r.timestamp}`,
  }));

  const panelBox: React.CSSProperties = {
    background: C.panel, border: `1px solid ${C.panelBorder}`, borderRadius: 12, padding: 0,
  };

  return (
    <section id="demo" style={{ background: C.bg, padding: "80px 24px 100px" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>

        {/* ── Header ───────────────────────────────────────────────────────── */}
        <div style={{ textAlign: "center", padding: "32px 24px 28px", background: "linear-gradient(135deg,#0d0d1a 0%,#12122a 100%)", borderRadius: 16, border: "1px solid #1e1e3f", marginBottom: 28, boxShadow: "0 10px 30px rgba(0,0,0,0.4)" }}>
          <h1 style={{ fontSize: "2.2rem", fontWeight: 700, background: "linear-gradient(90deg,#818cf8,#c084fc,#f472b6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text", margin: "0 0 8px", letterSpacing: "-0.5px" }}>
            Ask-N-Seek
          </h1>
          <p style={{ color: C.muted, fontSize: "1rem", margin: 0 }}>
            Type what happened. We&apos;ll show you exactly where — and prove it.
          </p>
          <span style={{ display: "inline-block", marginTop: 14, padding: "4px 14px", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.4)", borderRadius: 20, color: C.indigo, fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase" }}>
            {ingestStatus === "complete" ? "✅ Video Indexed · Ready to Search" : "Backend Ready"}
          </span>
        </div>

        {/* ── Ingestion Accordion ──────────────────────────────────────────── */}
        <div style={{ ...panelBox, marginBottom: 20 }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #1a1a35", color: C.white, fontWeight: 600, fontSize: "0.95rem" }}>
            📥 Live Judge-Video Ingestion
          </div>
          <div style={{ padding: "16px 20px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16 }}>
              {/* Upload zone */}
              <div
                onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                style={{
                  position: "relative", minHeight: 140,
                  border: `1px dashed ${isDragOver ? C.indigo : "#1e1e3f"}`,
                  borderRadius: 10, background: isDragOver ? C.indigoFaint : "#08080f",
                  display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column",
                  gap: 8, cursor: "pointer", transition: "all 0.2s",
                }}>
                <input type="file" accept="video/*" onChange={handleFileSelect}
                  style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer" }}
                  disabled={ingestStatus === "running"} />
                {ingestStatus === "complete"
                  ? <>
                      <span style={{ fontSize: 28 }}>✅</span>
                      <span style={{ color: C.green, fontSize: "0.85rem", fontWeight: 600 }}>{fileName ?? "Video Indexed"}</span>
                    </>
                  : <>
                      <span style={{ fontSize: 28 }}>🎬</span>
                      <span style={{ color: C.indigo, fontWeight: 600, fontSize: "0.88rem" }}>Drop a video file</span>
                      <span style={{ color: C.dimmer, fontSize: "0.75rem" }}>.mp4 / .avi / .mov / .mkv</span>
                    </>
                }
              </div>

              {/* Progress + Log + Stats */}
              <div>
                {/* Progress bar */}
                <div style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: C.dim, marginBottom: 4 }}>
                    <span>Ingestion Progress</span>
                    <span style={{ color: C.white, fontWeight: 600 }}>{ingestProgress}%</span>
                  </div>
                  <div style={{ height: 6, background: "#1e1e3f", borderRadius: 3, overflow: "hidden" }}>
                    <motion.div animate={{ width: `${ingestProgress}%` }} transition={{ duration: 0.3 }}
                      style={{ height: "100%", background: "linear-gradient(90deg,#6366f1,#818cf8)", borderRadius: 3 }} />
                  </div>
                </div>
                {/* Log box */}
                <div style={{ background: "#0f0f1f", border: "1px solid #1e1e3f", borderRadius: 8, padding: "10px 12px", height: 100, overflowY: "auto", ...MONO, fontSize: "0.75rem", color: C.muted, lineHeight: 1.7 }}>
                  {ingestLogs.length === 0
                    ? <span style={{ color: C.dimmer }}>Waiting for upload…</span>
                    : ingestLogs.map((l, i) => <div key={i}>{l}</div>)}
                </div>
                {/* Stats + Objects */}
                <IngestStats stats={ingestStats} />
                <DetectedObjectsSummary tally={ingestObjectTally} />
              </div>
            </div>
          </div>
        </div>

        <hr style={{ borderColor: "#1e293b", margin: "16px 0" }} />

        {/* ── Scenario Presets ─────────────────────────────────────────────── */}
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 600, color: C.dimmer, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 10 }}>
            Scenario Presets
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {scenarios.map(s => (
              <button key={s.id} onClick={() => { setQuery(s.query); onSearch(s.query); }}
                disabled={disabled || queryLoading}
                style={{ background: "rgba(30,30,63,0.6)", border: "1px solid #1e1e3f", color: C.indigo, fontSize: "0.8rem", fontWeight: 500, borderRadius: 8, padding: "6px 12px", cursor: "pointer", transition: "all 0.15s", opacity: disabled ? 0.4 : 1 }}
                onMouseEnter={e => { e.currentTarget.style.background = "rgba(99,102,241,0.2)"; e.currentTarget.style.borderColor = C.indigoDark; e.currentTarget.style.color = C.cyan; }}
                onMouseLeave={e => { e.currentTarget.style.background = "rgba(30,30,63,0.6)"; e.currentTarget.style.borderColor = "#1e1e3f"; e.currentTarget.style.color = C.indigo; }}>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Search Query ─────────────────────────────────────────────────── */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 600, color: C.dimmer, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8 }}>
            Search Query
          </div>
          <form onSubmit={handleSubmit} style={{ display: "flex", gap: 12 }}>
            <input
              type="text" value={query} onChange={e => setQuery(e.target.value)}
              placeholder={disabled ? "Upload a video first to search…" : "Try: 'person in red' · 'person without helmet' · 'two people'"}
              disabled={disabled || queryLoading}
              style={{
                flex: 1, background: "#0f0f1f", border: "1px solid #1e1e3f",
                borderRadius: 10, color: C.white, fontSize: "1rem", padding: "12px 16px",
                outline: "none", transition: "border-color 0.2s",
                opacity: disabled ? 0.6 : 1,
                fontFamily: "Inter, sans-serif",
              }}
              onFocus={e => e.target.style.borderColor = C.indigoDark}
              onBlur={e => e.target.style.borderColor = "#1e1e3f"}
            />
            <button type="submit" disabled={!query.trim() || queryLoading || disabled}
              style={{
                background: "linear-gradient(135deg,#6366f1,#818cf8)", border: "none",
                borderRadius: 10, color: "#fff", fontWeight: 600, fontSize: "0.95rem",
                padding: "12px 28px", cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
                boxShadow: "0 4px 15px rgba(99,102,241,0.3)", transition: "all 0.18s",
                opacity: (!query.trim() || queryLoading || disabled) ? 0.5 : 1,
              }}
              onMouseEnter={e => { if (!disabled) e.currentTarget.style.transform = "translateY(-1px)"; }}
              onMouseLeave={e => { e.currentTarget.style.transform = "none"; }}>
              <Search size={16} />
              {queryLoading ? "Searching…" : "🔍 Search"}
            </button>
          </form>

          {/* Vocab warnings */}
          <AnimatePresence>
            {vocabWarnings.length > 0 && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                style={{ marginTop: 10, background: "#451a03", border: "1px solid #f59e0b", color: "#fef3c7", padding: "10px 14px", borderRadius: 8, fontSize: "0.88rem" }}>
                {vocabWarnings.map((w, i) => (
                  <div key={i}>⚠️ {w.suggestion ? `"${w.token}" — did you mean "${w.suggestion}"?` : `"${w.token}" not recognized — try a different term.`}</div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Quick chips */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 10 }}>
            {["person in red", "person without helmet", "two people", "person left of car", "car in dark blue"].map(s => (
              <button key={s} onClick={() => { setQuery(s); onSearch(s); }} disabled={disabled || queryLoading}
                style={{ background: "none", border: "none", color: C.dim, ...MONO, fontSize: "0.78rem", cursor: "pointer", opacity: disabled ? 0.4 : 1, transition: "color 0.15s" }}
                onMouseEnter={e => e.currentTarget.style.color = C.white}
                onMouseLeave={e => e.currentTarget.style.color = C.dim}>
                {s} →
              </button>
            ))}
          </div>
        </div>

        {/* ── 2-Column: Processing Log | Results ───────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, marginBottom: 20 }}>
          {/* LEFT: Processing Log */}
          <div>
            <SectionLabel>Processing Log</SectionLabel>
            <ProcessingLog steps={processLog} />
          </div>

          {/* RIGHT: Results + Vocab Banner + Picker */}
          <div>
            <SectionLabel>Results</SectionLabel>

            {results.length === 0 && !showDiagnosis && (
              <div style={{ height: 420, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg,#0a0a14 0%,#0d0d1a 100%)", border: "1px dashed #1e1e3f", borderRadius: 12, color: C.dimmer, textAlign: "center", padding: 32 }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.6 }}>{queryLoading ? "⚙️" : "🔭"}</div>
                <p style={{ fontSize: "1rem", fontWeight: 600, color: C.dim, margin: "0 0 8px" }}>{queryLoading ? "Processing…" : "No results yet"}</p>
                <p style={{ fontSize: "0.85rem", color: C.dimmer, maxWidth: 280, lineHeight: 1.5, margin: 0 }}>
                  {queryLoading ? "Searching Qdrant…" : "Enter a query above and press Search to begin."}
                </p>
              </div>
            )}

            {/* Diagnosis panel */}
            {showDiagnosis && diagnosis && !results.length && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                style={{ height: 420, overflowY: "auto", background: "linear-gradient(135deg,#0a0a14,#0d0d1a)", border: "1px solid #1e1e3f", borderRadius: 12, padding: 24 }}>
                <div style={{ fontSize: 36, marginBottom: 12, textAlign: "center" }}>🔍</div>
                <p style={{ fontWeight: 600, color: C.dim, marginBottom: 8, textAlign: "center" }}>No confident match found</p>
                <p style={{ fontSize: "0.85rem", color: C.dimmer, textAlign: "center", marginBottom: 16 }}>No confident match found for this query.<br />Try broadening your description.</p>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", ...MONO, fontSize: "0.75rem", color: C.dim, marginBottom: 4 }}>
                    <span>Best partial score</span>
                    <span style={{ color: C.amber }}>{diagnosis.best_score.toFixed(3)}</span>
                  </div>
                  <div style={{ height: 4, background: "#1e1e3f", borderRadius: 2 }}>
                    <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(diagnosis.best_score * 100, 100)}%` }} transition={{ duration: 1.5 }}
                      style={{ height: "100%", background: C.amber, borderRadius: 2 }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", ...MONO, fontSize: "0.68rem", color: C.dimmer, marginTop: 2 }}>
                    <span>0.0</span><span>Threshold 0.320</span><span>1.0</span>
                  </div>
                </div>
                <div style={{ fontSize: "0.82rem", color: C.muted }} dangerouslySetInnerHTML={{ __html: diagnosis.html }} />
              </motion.div>
            )}

            {/* Result cards */}
            {results.length > 0 && (
              <>
                <div style={{ fontSize: "0.75rem", color: C.dimmer, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.5px", ...MONO }}>
                  {results.length} result{results.length !== 1 ? "s" : ""} — sorted by confidence
                </div>
                <div style={{ maxHeight: 420, overflowY: "auto", paddingRight: 4 }}>
                  {results.map((r, i) => <ResultCard key={i} r={r} onSeek={() => onResultSelect(r.video_id, r.timestamp)} />)}
                </div>
                <ResultPickerDropdown options={pickerOptions} onSelect={onResultSelect} />
              </>
            )}
          </div>
        </div>

        {/* ── Video Player ─────────────────────────────────────────────────── */}
        {selectedVideo && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 20 }}>
            <SectionLabel>Video Player</SectionLabel>
            <div style={{ background: "#08080f", border: "1px solid #1a1a2e", borderRadius: 12, padding: 16 }}>
              <video ref={videoRef} src={selectedVideo.path} controls style={{ width: "100%", borderRadius: 8, background: "#000", maxHeight: 480 }} />
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, ...MONO, fontSize: "0.78rem", color: C.dim }}>
                <Play size={14} /> Seeking to {selectedVideo.timestamp.toFixed(1)}s
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Query History ─────────────────────────────────────────────────── */}
        {history.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ ...panelBox }}>
            <div style={{ padding: "12px 20px", borderBottom: "1px solid #1a1a35", color: C.white, fontWeight: 600, fontSize: "0.95rem" }}>
              📜 Session Query History
            </div>
            <div style={{ padding: "12px 20px", maxHeight: 260, overflowY: "auto" }}>
              {history.map((item, idx) => (
                <div key={idx} style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 6, padding: "8px 12px", marginBottom: 6, fontSize: "0.85rem", color: C.white, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <b style={{ color: "#f8fafc" }}>Q: {item.query_text}</b>
                    <span style={{ color: C.dimmer, margin: "0 6px" }}>|</span>
                    <span style={{ color: C.muted }}>{item.result_count} result{item.result_count !== 1 ? "s" : ""}</span>
                    <span style={{ color: C.dimmer, margin: "0 6px" }}>|</span>
                    <span style={{ color: C.muted }}>score {item.top_score.toFixed(2)}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: C.dimmer, ...MONO, fontSize: "0.72rem" }}>{item.timestamp}</span>
                    <button onClick={() => { setQuery(item.query_text); onHistoryReplay(item.query_text); }}
                      style={{ background: "#3b82f6", color: "#fff", padding: "2px 10px", borderRadius: 4, fontSize: "0.75rem", fontWeight: 500, border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                      <RotateCcw size={10} /> Re-run
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", padding: "24px 0 8px", color: "#334155", fontSize: "0.75rem", marginTop: 20 }}>
          Ask-N-Seek · Natural Language Video Retrieval Engine
        </div>
      </div>
    </section>
  );
}
