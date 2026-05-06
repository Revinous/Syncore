type LoadingStateProps = {
  message?: string;
  hint?: string;
};

export function LoadingState({
  message = "Loading...",
  hint = "Syncore is querying the orchestrator and assembling the latest operator view.",
}: LoadingStateProps) {
  return (
    <div className="loading-state">
      <div className="state-title">Working</div>
      <div>{message}</div>
      {hint ? <div className="state-hint">{hint}</div> : null}
    </div>
  );
}
