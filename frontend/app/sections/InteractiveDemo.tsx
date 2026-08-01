"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Play, Clock } from "lucide-react";
import type { SearchResult, QueryHistoryItem, ScoreBreakdown } from "../types";
import { useScenarios } from "../hooks/useApi";

// ── SmartScoreBars ──────────────────────────────────────────────────────────
// Renders a 4-bar score breakdown for a result card.
// Shown on hover inside the result card overlay.
// Hidden gracefully when score_breakdown is absent (legacy data).
function SmartScoreBars({ sb }: { sb: ScoreBreakdown }) {
  const MONO: React.CSSProperties = {
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: "0.65rem",
    lineHeight: 1.6,
  };
  const BAR_LEN = 20;
  const FILLED = "#c4b8a5";
  const EMPTY  = "#8a8275";

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
        const empty  = BAR_LEN - filled;
        const bar    = "█".repeat(filled) + "░".repeat(empty);
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

interface Props {
  onIngestComplete: (collection: string) => void;
  ingestStatus: "idle" | "running" | "complete" | "error";
  ingestProgress: number;
  ingestLogs: string[];
  startIngest: (path: string) => Promise<string | null>;
  onSearch: (query: string) => void;
  queryLoading: boolean;
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

export default function InteractiveDemo({
  onIngestComplete, ingestStatus, ingestProgress, ingestLogs, startIngest,
  onSearch, queryLoading, vocabWarnings, disabled, results, diagnosis,
  showDiagnosis, currentQuery, selectedVideo, onResultSelect, history, onHistoryReplay,
}: Props) {
  const [query, setQuery] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const { scenarios } = useScenarios();

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

  return (
    <section id="demo" className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <span className="sd-label block mb-8">Demo</span>
        <h2 className="sd-headline-mid text-cream-100 mb-6">Try it live.</h2>
        <p className="sd-body-large mb-20 max-w-2xl">
          Upload a video. Ask a question. Watch the system prove every match.
        </p>

        {/* Upload Zone */}
        <div className="mb-24">
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
                  <div className="mt-4 space-y-1">
                    {ingestLogs.slice(-3).map((l, i) => <p key={i} className="sd-mono">{l}</p>)}
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
        </div>

        {/* Query */}
        <div className="mb-24">
          <span className="sd-label block mb-8">Query</span>
          <form onSubmit={handleSubmit}>
            <div className="relative">
              <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder={disabled ? "Upload a video first..." : "person without helmet left of blue car"}
                disabled={disabled || queryLoading}
                className="w-full bg-transparent border-0 border-b border-white/10 focus:border-sand pb-4 pt-2 font-serif text-2xl md:text-4xl text-cream-100 placeholder:text-cream-800 outline-none transition-colors duration-500 pr-16" />
              <button type="submit" disabled={!query.trim() || queryLoading || disabled}
                className="absolute right-0 bottom-4 text-cream-700 hover:text-sand disabled:opacity-30 transition-colors">
                <ArrowRight className="w-8 h-8" />
              </button>
            </div>
          </form>

          <AnimatePresence>
            {vocabWarnings.length > 0 && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mt-6 border-l border-sand pl-6">
                {vocabWarnings.map((w, i) => (
                  <p key={i} className="sd-mono text-cream-500">
                    {w.suggestion ? `"${w.token}" → did you mean "${w.suggestion}"?` : `"${w.token}" not recognized.`}
                  </p>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Scenario Presets */}
          <div className="flex flex-wrap gap-3 mt-8 mb-2">
            {scenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setQuery(s.query);
                  onSearch(s.query);
                }}
                disabled={disabled || queryLoading}
                title={s.query}
                className="text-xs px-3 py-1.5 border transition-all duration-300 disabled:opacity-30"
                style={{
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  borderColor: "rgba(255,255,255,0.1)",
                  color: "#8a8275",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "#c4b8a5";
                  (e.currentTarget as HTMLButtonElement).style.color = "#c4b8a5";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.1)";
                  (e.currentTarget as HTMLButtonElement).style.color = "#8a8275";
                }}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Quick-query chips (existing) */}
          <div className="flex flex-wrap gap-6 mt-4">
            {["person in red", "person without helmet", "two people", "person left of car", "car in dark blue"].map((s) => (
              <button key={s} onClick={() => { setQuery(s); onSearch(s); }} disabled={disabled || queryLoading}
                className="sd-mono hover:text-cream-100 transition-colors disabled:opacity-30">
                {s} →
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <AnimatePresence>
          {results.length > 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mb-24">
              <div className="flex items-center justify-between mb-8">
                <span className="sd-label">{results.length} Match{results.length !== 1 ? "es" : ""} for "{currentQuery}"</span>
                <span className="sd-mono">Scroll →</span>
              </div>
              <div className="flex gap-4 overflow-x-auto pb-4" style={{ scrollSnapType: "x mandatory", scrollbarWidth: "none" }}>
                {results.map((r, i) => (
                  <button key={i} onClick={() => onResultSelect(r.video_id, r.timestamp)}
                    className="flex-shrink-0 w-[320px] md:w-[400px] aspect-video bg-neutral-950 border border-white/5 hover:border-white/15 transition-all duration-500 text-left relative overflow-hidden group"
                    style={{ scrollSnapAlign: "start" }}>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Play className="w-8 h-8 text-cream-800 group-hover:text-sand transition-colors" />
                    </div>
                    <div className="absolute inset-0 opacity-20 group-hover:opacity-40 transition-opacity">
                      {r.matched_objects.slice(0, 3).map((obj, j) => {
                        const bbox = obj.bbox || [0.1 + j * 0.25, 0.2, 0.35 + j * 0.25, 0.6];
                        return (
                          <div key={j} className="absolute border border-sand/50" style={{
                            left: `${bbox[0] * 100}%`, top: `${bbox[1] * 100}%`,
                            width: `${(bbox[2] - bbox[0]) * 100}%`, height: `${(bbox[3] - bbox[1]) * 100}%`
                          }} />
                        );
                      })}
                    </div>
                    <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
                      <div className="flex items-end justify-between">
                        <div>
                          <p className="font-serif text-sm text-cream-100">{r.video_id}</p>
                          <p className="sd-mono mt-1">{r.timestamp.toFixed(1)}s · {r.matched_objects.length} objects</p>
                        </div>
                        <span className={`text-xs font-mono px-2 py-1 border ${r.confidence_score >= 0.75 ? "border-sand text-sand" : "border-cream-800 text-cream-700"}`}>
                          {(r.confidence_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <div className="absolute top-0 left-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity bg-black/70">
                      <p className="text-cream-300 text-xs leading-relaxed">{r.explanation}</p>
                      {r.score_breakdown && <SmartScoreBars sb={r.score_breakdown} />}
                    </div>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Video Player */}
        <AnimatePresence>
          {selectedVideo && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mb-24">
              <span className="sd-label block mb-4">Playback</span>
              <div className="aspect-video bg-neutral-950 border border-white/5">
                <video src={selectedVideo.path} className="w-full h-full object-contain" controls autoPlay />
              </div>
              <div className="flex items-center gap-4 mt-4">
                <Clock className="w-4 h-4 text-cream-800" />
                <span className="sd-mono">{selectedVideo.timestamp.toFixed(1)}s</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Diagnosis */}
        <AnimatePresence>
          {showDiagnosis && diagnosis && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mb-24 border-l border-white/10 pl-8 py-4">
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

        {/* History */}
        {history.length > 0 && (
          <div className="border-t border-white/5 pt-12">
            <span className="sd-label block mb-6">Session Log</span>
            <div className="space-y-0">
              {history.map((item, idx) => (
                <button key={idx} onClick={() => onHistoryReplay(item.query_text)}
                  className="w-full flex items-center justify-between py-3 border-b border-white/5 hover:border-white/10 transition-colors group text-left">
                  <div className="flex items-center gap-6">
                    <span className="sd-mono w-8">{String(history.length - idx).padStart(2, "0")}</span>
                    <span className="text-cream-500 group-hover:text-cream-100 transition-colors text-sm">{item.query_text}</span>
                  </div>
                  <div className="flex items-center gap-6 sd-mono">
                    <span>{item.result_count} results</span>
                    <span>{item.top_score.toFixed(2)}</span>
                    <span className="text-cream-800">{item.timestamp}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
