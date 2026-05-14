import { useDashboardData } from "../src/hooks/useDashboardData";
import { DashboardPanels } from "../src/components/DashboardPanels";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";
import { StatusBadge } from "../src/components/StatusBadge";

export default function DashboardPage() {
  const { data, efficiency, loading, refreshing, lastLoadedAt, error, load } = useDashboardData();

  const secondsSinceRefresh = lastLoadedAt
    ? Math.max(0, Math.round((Date.now() - lastLoadedAt.getTime()) / 1000))
    : null;
  const freshnessState =
    secondsSinceRefresh === null
      ? "unknown"
      : secondsSinceRefresh <= 20
        ? "fresh"
        : "stale";
  const refreshLabel =
    lastLoadedAt === null
      ? "waiting"
      : `${lastLoadedAt.toLocaleTimeString()}${refreshing ? " · refreshing" : ""}`;

  return (
    <Layout title="Dashboard">
      <div className="page-shell">
        <PageHeader
          title="Delivery Control"
          subtitle="See the current health of the local autonomy stack, token-efficiency posture, and the operational stream that is driving work across tasks, runs, and workspace context."
          kicker="Runtime Overview"
          actions={<button className="button" onClick={() => void load()}>Refresh Dashboard</button>}
          metrics={[
            { label: "Health", value: data?.health ?? "unknown" },
            { label: "Runtime", value: data?.runtime_mode ?? "n/a" },
            { label: "DB Backend", value: data?.db_backend ?? "n/a" },
          ]}
        />

        <div className="operator-strip">
          <div className="operator-strip-block">
            <span className="operator-strip-label">Data Freshness</span>
            <div className="operator-strip-value"><StatusBadge status={freshnessState} /></div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Last Refresh</span>
            <div className="operator-strip-value">{refreshLabel}</div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Cadence</span>
            <div className="operator-strip-value">auto every 15s</div>
          </div>
        </div>

        {loading && <LoadingState message="Loading dashboard summary..." />}
        {error && <ErrorState message={error} />}

        {data ? <DashboardPanels data={data} efficiency={efficiency} /> : null}
      </div>
    </Layout>
  );
}
