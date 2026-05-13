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
  const [refreshing, setRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(background = false) {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
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
      setLastLoadedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load diagnostics");
    } finally {
      if (background) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const secondsSinceRefresh = lastLoadedAt
    ? Math.max(0, Math.round((Date.now() - lastLoadedAt.getTime()) / 1000))
    : null;
  const freshnessState =
    secondsSinceRefresh === null
      ? "unknown"
      : secondsSinceRefresh <= 20
        ? "fresh"
        : "stale";
  const isOfflineError = error?.includes("Could not reach Syncore API");

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

        <div className="operator-strip">
          <div className="operator-strip-block">
            <span className="operator-strip-label">Freshness</span>
            <div className="operator-strip-value"><StatusBadge status={freshnessState} /></div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Last Refresh</span>
            <div className="operator-strip-value">
              {lastLoadedAt ? `${lastLoadedAt.toLocaleTimeString()}${refreshing ? " · refreshing" : ""}` : "waiting"}
            </div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Cadence</span>
            <div className="operator-strip-value">auto every 15s</div>
          </div>
        </div>

        {loading && <LoadingState message="Loading diagnostics..." />}
        {error && (
          <ErrorState
            title={isOfflineError ? "Syncore API offline" : "Operator attention required"}
            message={error}
            hint={
              isOfflineError
                ? "The browser cannot reach the local orchestrator. Start Syncore services, then refresh diagnostics."
                : "Refresh the surface. If this persists, check diagnostics and service health."
            }
          />
        )}

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
