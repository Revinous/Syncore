export function LoadingState({ message = "Loading..." }: { message?: string }) {
  return <div style={{ color: "#555" }}>{message}</div>;
}
