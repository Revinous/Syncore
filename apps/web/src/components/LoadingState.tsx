export function LoadingState({ message = "Loading..." }: { message?: string }) {
  return <div className="loading-state">{message}</div>;
}
