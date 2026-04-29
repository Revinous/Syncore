import { useEffect, useState } from "react";

import { acknowledgeNotification, listNotifications } from "../src/lib/api";
import { NotificationItem } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await listNotifications(false, 200);
      setItems(payload.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }

  async function ack(id: string) {
    try {
      await acknowledgeNotification(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to acknowledge notification");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Layout title="Notifications">
      <button onClick={() => void load()} style={{ marginBottom: 12 }}>
        Refresh
      </button>
      {loading && <LoadingState message="Loading notifications..." />}
      {error && <ErrorState message={error} />}
      {!loading && !error && items.length === 0 && <EmptyState message="No unread notifications." />}
      {!loading && !error && items.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Category</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Title</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Body</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Created</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{item.category}</td>
                <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{item.title}</td>
                <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{item.body}</td>
                <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{item.created_at}</td>
                <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                  <button onClick={() => void ack(item.id)}>Acknowledge</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}
