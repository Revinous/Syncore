import { useEffect, useState } from "react";

import {
  getApiBaseUrl,
  getDiagnostics,
  getDiagnosticsConfig,
  getDiagnosticsRoutes,
  getHealth,
  getServicesHealth,
} from "../src/lib/api";
import {
  DiagnosticsConfig,
  DiagnosticsOverview,
  DiagnosticsRoutes,
  HealthResponse,
  ServicesHealthResponse,
} from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { StatusBadge } from "../src/components/StatusBadge";

export default function DiagnosticsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [servicesHealth, setServicesHealth] = useState<ServicesHealthResponse | null>(null);
  const [overview, setOverview] = useState<DiagnosticsOverview | null>(null);
  const [config, setConfig] = useState<DiagnosticsConfig | null>(null);
  const [routes, setRoutes] = useState<DiagnosticsRoutes | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [h, sh, ov, cfg, rt] = await Promise.all([
        getHealth(),
        getServicesHealth(),
        getDiagnostics(),
        getDiagnosticsConfig(),
        getDiagnosticsRoutes(),
      ]);
      setHealth(h);
      setServicesHealth(sh);
      setOverview(ov);
      setConfig(cfg);
      setRoutes(rt);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load diagnostics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Layout title="Diagnostics">
      <button onClick={() => void load()} style={{ marginBottom: 12 }}>Refresh</button>
      <p>Frontend API base URL: {getApiBaseUrl()}</p>
      {loading && <LoadingState message="Loading diagnostics..." />}
      {error && <ErrorState message={error} />}

      {overview && config && health && servicesHealth && (
        <>
          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Service Health</h2>
            <p>Orchestrator: <StatusBadge status={health.status} /></p>
            <p>Dependencies: <StatusBadge status={servicesHealth.status} /></p>
            <ul>
              {servicesHealth.dependencies.map((dependency) => (
                <li key={dependency.name}>{dependency.name}: <StatusBadge status={dependency.status} /> ({dependency.detail})</li>
              ))}
            </ul>
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Runtime</h2>
            <p>Runtime mode: {overview.runtime_mode}</p>
            <p>DB backend: {overview.db_backend}</p>
            <p>Redis required: {String(overview.redis_required)}</p>
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Config</h2>
            <pre>{JSON.stringify(config, null, 2)}</pre>
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Registered Routes</h2>
            {!routes?.routes?.length ? (
              <EmptyState message="No route metadata available." />
            ) : (
              <ul>
                {routes.routes.slice(0, 200).map((route) => (
                  <li key={route}>{route}</li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Layout>
  );
}
