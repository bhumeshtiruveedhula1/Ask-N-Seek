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
import type { SearchResult, QueryHistoryItem } from "./types";

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

    await checkVocab(query);
    const response = await runQuery(query, activeCollection || undefined);
    if (!response) return;

    if (response.status === "match" && response.results) {
      setResults(response.results);
      setShowDiagnosis(false);
    } else if (response.diagnosis) {
      setDiagnosis(response.diagnosis);
      setShowDiagnosis(true);
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
        startIngest={startIngest}
        onSearch={handleSearch}
        queryLoading={queryLoading}
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
