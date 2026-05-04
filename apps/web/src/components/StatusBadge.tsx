export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = ["ok", "healthy", "completed", "running", "ready", "open"].includes(normalized)
    ? "good"
    : ["warning", "degraded", "blocked", "pending", "queued"].includes(normalized)
      ? "warn"
      : ["error", "failed", "offline", "unhealthy"].includes(normalized)
        ? "bad"
        : "neutral";

  return <span className={`status-badge ${tone}`}>{status.replaceAll("_", " ")}</span>;
}
