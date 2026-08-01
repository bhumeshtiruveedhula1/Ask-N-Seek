"use client";

import { useState, useCallback, useEffect } from "react";
import type { QueryRequest, QueryResponse, IngestStartResponse, ScenarioPreset, ScenariosResponse } from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useQuery() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<QueryResponse | null>(null);

  const execute = useCallback(async (query: string, collection?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, collection_name: collection } as QueryRequest),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      return json as QueryResponse;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { execute, loading, error, data };
}

export function useIngestion() {
  const [status, setStatus] = useState<"idle" | "running" | "complete" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [collection, setCollection] = useState<string | null>(null);

  const start = useCallback(async (videoPath: string) => {
    setStatus("running");
    setProgress(0);
    setLogs(["Initializing..."]);
    try {
      const form = new FormData();
      form.append("video_path", videoPath);
      const res = await fetch(`${API_BASE}/ingest/start`, { method: "POST", body: form });
      const json: IngestStartResponse = await res.json();
      setCollection(json.collection_name);
      for (let i = 0; i <= 100; i += 8) {
        await new Promise((r) => setTimeout(r, 250));
        setProgress(i);
        setLogs((prev) => [...prev, `${getPhaseName(i)}...`]);
      }
      setStatus("complete");
      setLogs((prev) => [...prev, "Indexing complete. Ready to search."]);
      return json.collection_name;
    } catch (err) {
      setStatus("error");
      setLogs((prev) => [...prev, `Error: ${err}`]);
      return null;
    }
  }, []);

  return { start, status, progress, logs, collection };
}

function getPhaseName(pct: number): string {
  if (pct < 15) return "Scene detection";
  if (pct < 30) return "Keyframe extraction";
  if (pct < 50) return "YOLO detection";
  if (pct < 70) return "Color extraction";
  if (pct < 85) return "Spatial relations";
  if (pct < 95) return "Qdrant indexing";
  return "Finalizing";
}

export function useVocabCheck() {
  const [warnings, setWarnings] = useState<Array<{ token: string; suggestion?: string }>>([]);

  const check = useCallback(async (query: string) => {
    try {
      const form = new FormData();
      form.append("query", query);
      const res = await fetch(`${API_BASE}/vocab/check`, { method: "POST", body: form });
      const json = await res.json();
      setWarnings(json);
    } catch {
      setWarnings([]);
    }
  }, []);

  return { check, warnings };
}

const MOCK_SCENARIOS: ScenarioPreset[] = [
  { id: "safety_violation", label: "🔴 Safety Violation", query: "person without helmet" },
  { id: "traffic_incident", label: "🚗 Traffic Incident",  query: "car left of person" },
  { id: "lost_item",        label: "🎒 Lost Item",         query: "backpack without owner" },
  { id: "access_control",   label: "🚪 Access Control",    query: "person without badge" },
  { id: "crowd_check",      label: "👥 Crowd Check",       query: "more than two people" },
];

export function useScenarios() {
  const [scenarios, setScenarios] = useState<ScenarioPreset[]>(MOCK_SCENARIOS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/scenarios`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<ScenariosResponse>;
      })
      .then((json) => {
        if (!cancelled && json.scenarios?.length) {
          setScenarios(json.scenarios);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          // Keep mock fallback — bridge may be offline
          setError(err instanceof Error ? err.message : "Scenarios unavailable");
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, []);

  return { scenarios, loading, error };
}
