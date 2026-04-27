import { useEffect, useState } from "react";

import { getDashboardSummary } from "../src/lib/api";
import { DashboardSummary } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { StatCard } from "../src/components/StatCard";
import { StatusBadge } from "../src/components/StatusBadge";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getDashboardSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Layout title="Dashboard">
      <button onClick={() => void load()} style={{ marginBottom: 12 }}>
        Refresh
      </button>
      {loading && <LoadingState message="Loading dashboard summary..." />}
      {error && <ErrorState message={error} />}
      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
            <StatCard label="Health" value={data.health} />
            <StatCard label="Runtime" value={data.runtime_mode} />
            <StatCard label="DB Backend" value={data.db_backend} />
            <StatCard label="Redis" value={data.services.redis ?? "unknown"} />
            <StatCard label="Workspaces" value={data.workspace_count} />
            <StatCard label="Open Tasks" value={data.open_task_count} />
            <StatCard label="Active Runs" value={data.active_run_count} />
            <StatCard label="Recent Events" value={data.recent_events.length} />
          </div>

          <section style={{ marginTop: 16, padding: 12, border: "1px solid #d8dbe2", background: "#fff", borderRadius: 8 }}>
            <h2>Services</h2>
            <ul>
              {Object.entries(data.services).map(([name, status]) => (
                <li key={name}>
                  {name}: <StatusBadge status={status} />
                </li>
              ))}
            </ul>
          </section>

          <section style={{ marginTop: 16, padding: 12, border: "1px solid #d8dbe2", background: "#fff", borderRadius: 8 }}>
            <h2>Recent Events</h2>
            {data.recent_events.length === 0 ? (
              <EmptyState message="No recent events." />
            ) : (
              <ul>
                {data.recent_events.slice(0, 10).map((event) => (
                  <li key={event.id}>
                    {event.event_type} ({event.task_id})
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section style={{ marginTop: 16, padding: 12, border: "1px solid #d8dbe2", background: "#fff", borderRadius: 8 }}>
            <h2>Recent Batons</h2>
            {data.recent_batons.length === 0 ? (
              <EmptyState message="No baton handoffs yet." />
            ) : (
              <ul>
                {data.recent_batons.slice(0, 10).map((packet) => (
                  <li key={packet.id}>
                    {packet.from_agent} → {packet.to_agent ?? "unassigned"}: {packet.summary}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Layout>
  );
}
