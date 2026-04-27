export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const isGood = normalized === "ok" || normalized === "completed" || normalized === "running";
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 12,
        background: isGood ? "#e8f7ef" : "#fdecea",
        color: isGood ? "#1b6b44" : "#9d2436",
      }}
    >
      {status}
    </span>
  );
}
