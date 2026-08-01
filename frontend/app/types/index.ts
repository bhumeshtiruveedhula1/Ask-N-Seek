export interface MatchedObject {
  class_name: string;
  color?: string;
  bbox?: number[];
  confidence?: number;
}

export interface ScoreBreakdown {
  total: number;         // 0-100
  object_score: number;  // 0-40
  color_score: number;   // 0-20
  spatial_score: number; // 0-20
  negation_score: number; // 0-20
  details: {
    object?: string;
    color?: string;
    spatial?: string;
    negation?: string;
  };
}

export interface ScenarioPreset {
  id: string;
  label: string;
  query: string;
}

export interface SearchResult {
  video_id: string;
  timestamp: number;
  scene_id: number;
  confidence_score: number;
  matched_objects: MatchedObject[];
  explanation?: string;
  score_breakdown?: ScoreBreakdown; // optional — absent on legacy data
}

export interface QueryHistoryItem {
  query_text: string;
  timestamp: string;
  parsed_filter: Record<string, unknown>;
  result_count: number;
  top_score: number;
}

export interface QueryRequest {
  query: string;
  collection_name?: string;
}

export interface QueryResponse {
  status: "match" | "no_match";
  parsed: { status: string; filters: Record<string, unknown> };
  results: SearchResult[];
  diagnosis: { html: string; best_score: number } | null;
  threshold: number;
  best_score: number;
  vocab_warnings: Array<{ token: string; suggestion?: string }>;
}

export interface ScenariosResponse {
  scenarios: ScenarioPreset[];
}

export interface IngestStartResponse {
  job_id: string;
  collection_name: string;
  video_path: string;
  status: string;
}
