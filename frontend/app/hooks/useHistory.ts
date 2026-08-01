"use client";

import { useState, useCallback } from "react";
import type { QueryHistoryItem } from "../types";

export function useHistory() {
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);

  const add = useCallback((item: QueryHistoryItem) => {
    setHistory((prev) => [item, ...prev]);
  }, []);

  const clear = useCallback(() => setHistory([]), []);

  return { history, add, clear };
}
