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
import { PageHeader } from "../src/components/PageHeader";
import { StatusBadge } from "../src/components/StatusBadge";
import { Surface } from "../src/components/Surface";

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
      <div className="page-shell">
        <PageHeader
          title="Operational Diagnostics"
          subtitle="Inspect route registration, runtime shape, dependency posture, and the exact frontend-to-orchestrator connection being used right now."
          kicker="Operational State"
          actions={<button className="button" onClick={() => void load()}>Refresh Diagnostics</button>}
          metrics={[
            { label: "API Base", value: getApiBaseUrl() },
            { label: "Health", value: health?.status ?? "unknown" },
          ]}
        />

        {loading && <LoadingState message="Loading diagnostics..." />}
        {error && <ErrorState message={error} />}

        {overview && config && health && servicesHealth ? (
          <div className="content-grid two-column">
            <div className="stack">
              <Surface title="Service Health" description="Health endpoints surfaced by the orchestrator.">
                <div className="meta-grid">
                  <div className="meta-card">
                    <span className="meta-label">Orchestrator</span>
                    <div className="meta-value"><StatusBadge status={health.status} /></div>
                  </div>
                  <div className="meta-card">
                    <span className="meta-label">Dependencies</span>
                    <div className="meta-value"><StatusBadge status={servicesHealth.status} /></div>
                  </div>
                </div>
                <div className="stack" style={{ marginTop: 16 }}>
                  {servicesHealth.dependencies.map((dependency) => (
                    <div className="meta-card" key={dependency.name}>
                      <span className="meta-label">{dependency.name}</span>
                      <div className="meta-value"><StatusBadge status={dependency.status} /> {dependency.detail}</div>
                    </div>
                  ))}
                </div>
              </Surface>

              <Surface title="Runtime Shape" description="Backend runtime flags relevant to local operation.">
                <div className="meta-grid">
                  <div className="meta-card"><span className="meta-label">Runtime Mode</span><div className="meta-value">{overview.runtime_mode}</div></div>
                  <div className="meta-card"><span className="meta-label">DB Backend</span><div className="meta-value">{overview.db_backend}</div></div>
                  <div className="meta-card"><span className="meta-label">Redis Required</span><div className="meta-value">{String(overview.redis_required)}</div></div>
                </div>
              </Surface>
            </div>

            <div className="stack">
              <Surface title="Config Snapshot" description="Current orchestrator config as exposed by diagnostics.">
                <div className="code-block">{JSON.stringify(config, null, 2)}</div>
              </Surface>

              <Surface title="Registered Routes" description="Current route inventory available to the UI and CLI.">
                {!routes?.routes?.length ? (
                  <EmptyState message="No route metadata available." />
                ) : (
                  <div className="code-block">{routes.routes.slice(0, 200).join("\n")}</div>
                )}
              </Surface>
            </div>
          </div>
        ) : null}
      </div>
    </Layout>
  );
}
