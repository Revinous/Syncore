type EmptyStateProps = {
  message: string;
  title?: string;
  hint?: string;
};

export function EmptyState({
  message,
  title = "Nothing to show yet",
  hint,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="state-title">{title}</div>
      <div>{message}</div>
      {hint ? <div className="state-hint">{hint}</div> : null}
    </div>
  );
}
