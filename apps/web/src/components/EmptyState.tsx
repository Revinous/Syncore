export function EmptyState({ message }: { message: string }) {
  return (
    <div style={{ border: "1px dashed #c9ced8", background: "#fff", padding: 12, borderRadius: 8 }}>
      {message}
    </div>
  );
}
