import type { AnalystDigest, ProviderCapability, TaskDetail, TaskExecutionReport } from "./types";

export function buildDigestEli5(value: AnalystDigest): string {
  const text = (value.eli5_summary || "").trim();
  if (text) return text;
  const top = Object.entries(value.event_breakdown || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 2)
    .map(([name, count]) => `${name} (${count})`)
    .join(", ");
  const latest = value.highlights?.[0] || "no recent highlight";
  return (
    `Simple summary: ${value.headline}. ` +
    `Top signals: ${top || "none"}. ` +
    `Latest: ${latest}. ` +
    `Risk: ${value.risk_level}.`
  );
}

export function formatDigestEli5(text: string): string {
  return text.replace(/\. /g, ".\n");
}

export function summarizeProviderCapability(
  providerCapabilities: ProviderCapability[],
  provider: string,
): string | null {
  const item = providerCapabilities.find((row) => row.provider === provider);
  if (!item) return null;
  return `ctx ${item.max_context_tokens.toLocaleString()} | quality ${item.quality_tier}/5 | speed ${item.speed_tier}/5 | cost ${item.cost_tier}/5`;
}

export function deriveTaskFreshness(lastLoadedAt: Date | null): {
  secondsSinceRefresh: number | null;
  freshnessState: string;
} {
  const secondsSinceRefresh = lastLoadedAt
    ? Math.max(0, Math.round((Date.now() - lastLoadedAt.getTime()) / 1000))
    : null;
  const freshnessState =
    secondsSinceRefresh === null ? "unknown" : secondsSinceRefresh <= 20 ? "fresh" : "stale";
  return { secondsSinceRefresh, freshnessState };
}

export function deriveTaskExecutionState(
  detail: TaskDetail | null,
  executionReport: TaskExecutionReport | null,
): string {
  return (
    executionReport?.outcome_status ||
    detail?.agent_runs.find((run) => run.status === "running" || run.status === "in_progress")
      ?.status ||
    detail?.task.status ||
    "unknown"
  );
}

export function isOfflineTaskError(error: string | null): boolean {
  return Boolean(error?.includes("Could not reach Syncore API"));
}
