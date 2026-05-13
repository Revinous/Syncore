export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = ["ok", "healthy", "completed", "running", "in_progress", "ready", "open", "fresh"].includes(normalized)
    ? "good"
    : ["warning", "degraded", "blocked", "pending", "queued", "stale"].includes(normalized)
      ? "warn"
      : ["error", "failed", "offline", "unhealthy"].includes(normalized)
        ? "bad"
        : "neutral";

  return <span className={`status-badge ${tone}`}>{status.replaceAll("_", " ")}</span>;
}
