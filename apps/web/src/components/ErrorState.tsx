export function ErrorState({ message }: { message: string }) {
  return <div className="error-state">Error: {message}</div>;
}
