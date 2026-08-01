"use client";

import { useEffect, useState, useCallback } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

import Navigation from "./sections/Navigation";
import Hero from "./sections/Hero";
import QuoteSection from "./sections/QuoteSection";
import AboutSection from "./sections/AboutSection";
import ConceptSection from "./sections/ConceptSection";
import CinematicSection from "./sections/CinematicSection";
import SVGPathTextSection from "./sections/SVGPathTextSection";
import PipelineBreakdown from "./sections/PipelineBreakdown";
import InfrastructureGrid from "./sections/InfrastructureGrid";
import InteractiveDemo from "./sections/InteractiveDemo";
import Footer from "./sections/Footer";

import { useQuery, useIngestion, useVocabCheck } from "./hooks/useApi";
import { useHistory } from "./hooks/useHistory";
import type { SearchResult, QueryHistoryItem, ProcessLogStep } from "./types";

gsap.registerPlugin(ScrollTrigger);

export default function Home() {
  // Lenis smooth scroll
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.4,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      touchMultiplier: 2,
    });

    lenis.on("scroll", ScrollTrigger.update);

    gsap.ticker.add((time) => {
      lenis.raf(time * 1000);
    });

    gsap.ticker.lagSmoothing(0);

    return () => {
      lenis.destroy();
      gsap.ticker.remove(lenis.raf as any);
    };
  }, []);

  // App state
  const [activeCollection, setActiveCollection] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [diagnosis, setDiagnosis] = useState<{ html: string; best_score: number } | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<{ path: string; timestamp: number } | null>(null);
  const [currentQuery, setCurrentQuery] = useState("");
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [processLog, setProcessLog] = useState<ProcessLogStep[]>([]);
  const [ingestStats, setIngestStats] = useState<Record<string, unknown> | null>(null);
  const [ingestObjectTally, setIngestObjectTally] = useState<Record<string, Record<string, number>> | null>(null);

  const { execute: runQuery, loading: queryLoading } = useQuery();
  const { start: startIngest, status: ingestStatus, progress: ingestProgress, logs: ingestLogs, collection: ingestCollection } = useIngestion();
  const { check: checkVocab, warnings: vocabWarnings } = useVocabCheck();
  const { history, add: addHistory } = useHistory();

  const handleIngestComplete = useCallback((collectionName: string) => {
    setActiveCollection(collectionName);
  }, []);

  const handleSearch = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setCurrentQuery(query);
    setResults([]);
    setDiagnosis(null);
    setShowDiagnosis(false);
    // Start processing log
    setProcessLog([
      { cls: "info", text: "⏳ Parsing query…" },
    ]);

    await checkVocab(query);

    setProcessLog(prev => [...prev, { cls: "info", text: `🔎 Searching Qdrant…` }]);

    const response = await runQuery(query, activeCollection || undefined);
    if (!response) {
      setProcessLog(prev => [...prev, { cls: "fail", text: "❌ Search request failed" }]);
      return;
    }

    if (response.parsed?.filters) {
      setProcessLog(prev => [...prev,
        { cls: "muted", text: `🔍 Filter: <code>${JSON.stringify(response.parsed.filters)}</code>` },
      ]);
    }

    if (response.status === "match" && response.results) {
      setProcessLog(prev => [...prev,
        { cls: "muted", text: `📦 Found ${response.results.length} raw result(s)` },
        { cls: "info",  text: "📊 Reranking by confidence…" },
        { cls: "muted", text: "📂 Grouping by source video…" },
        { cls: "pass",  text: `✅ Threshold check: PASS — best score ${(response.best_score || 0).toFixed(2)} ≥ threshold ${(response.threshold || 0.32).toFixed(2)}` },
        { cls: "pass",  text: `🎯 Returning ${response.results.length} result(s) — select from dropdown to play clip` },
      ]);
      setResults(response.results);
      setShowDiagnosis(false);
    } else {
      const best = response.best_score || 0;
      setProcessLog(prev => [...prev,
        { cls: "fail", text: `🔴 Threshold check: FAIL — best score ${best.toFixed(2)} < threshold ${(response.threshold || 0.32).toFixed(2)}` },
        { cls: "muted", text: "🔬 Running no-match diagnosis…" },
      ]);
      if (response.diagnosis) {
        setDiagnosis(response.diagnosis);
        setShowDiagnosis(true);
      }
    }

    const historyItem: QueryHistoryItem = {
      query_text: query,
      timestamp: new Date().toLocaleTimeString(),
      parsed_filter: response.parsed?.filters || {},
      result_count: response.results?.length || 0,
      top_score: response.best_score || 0,
    };
    addHistory(historyItem);
  }, [activeCollection, runQuery, checkVocab, addHistory]);

  const handleResultSelect = useCallback((videoPath: string, timestamp: number) => {
    setSelectedVideo({ path: videoPath, timestamp });
  }, []);

  const handleHistoryReplay = useCallback((queryText: string) => {
    handleSearch(queryText);
  }, [handleSearch]);

  return (
    <main className="min-h-screen bg-black">
      <Navigation />
      <Hero />
      <QuoteSection />
      <AboutSection />
      <ConceptSection />
      <CinematicSection />
      <SVGPathTextSection />
      <PipelineBreakdown />
      <InfrastructureGrid />
      <InteractiveDemo
        onIngestComplete={handleIngestComplete}
        ingestStatus={ingestStatus}
        ingestProgress={ingestProgress}
        ingestLogs={ingestLogs}
        ingestStats={ingestStats}
        ingestObjectTally={ingestObjectTally}
        startIngest={startIngest}
        onSearch={handleSearch}
        queryLoading={queryLoading}
        processLog={processLog}
        vocabWarnings={vocabWarnings}
        disabled={!activeCollection && ingestStatus !== "complete"}
        results={results}
        diagnosis={diagnosis}
        showDiagnosis={showDiagnosis}
        currentQuery={currentQuery}
        selectedVideo={selectedVideo}
        onResultSelect={handleResultSelect}
        history={history}
        onHistoryReplay={handleHistoryReplay}
      />
      <Footer />
    </main>
  );
}
