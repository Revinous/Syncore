export function ErrorState({ message }: { message: string }) {
  return (
    <div style={{ border: "1px solid #f0c2c7", background: "#fff5f6", padding: 12, borderRadius: 8 }}>
      Error: {message}
    </div>
  );
}
