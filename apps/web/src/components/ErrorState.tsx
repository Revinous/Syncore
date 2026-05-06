type ErrorStateProps = {
  message: string;
  title?: string;
  hint?: string;
};

export function ErrorState({
  message,
  title = "Operator attention required",
  hint = "Refresh the surface. If this persists, check diagnostics and service health.",
}: ErrorStateProps) {
  return (
    <div className="error-state">
      <div className="state-title">{title}</div>
      <div>Error: {message}</div>
      {hint ? <div className="state-hint">{hint}</div> : null}
    </div>
  );
}
