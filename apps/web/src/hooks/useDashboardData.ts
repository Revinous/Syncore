import { useEffect, useState } from "react";

import { getContextEfficiencyMetrics, getDashboardSummary } from "../lib/api";
import type { ContextEfficiencyMetrics, DashboardSummary } from "../lib/types";

export function useDashboardData() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [efficiency, setEfficiency] = useState<ContextEfficiencyMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(background = false) {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const [summary, contextEfficiency] = await Promise.all([
        getDashboardSummary(),
        getContextEfficiencyMetrics(),
      ]);
      setData(summary);
      setEfficiency(contextEfficiency);
      setLastLoadedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      if (background) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  return {
    data,
    efficiency,
    loading,
    refreshing,
    lastLoadedAt,
    error,
    load,
  };
}
