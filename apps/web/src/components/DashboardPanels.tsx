import { EmptyState } from "./EmptyState";
import { StatCard } from "./StatCard";
import { StatusBadge } from "./StatusBadge";
import { Surface } from "./Surface";
import type { ContextEfficiencyMetrics, DashboardSummary } from "../lib/types";

type DashboardPanelsProps = {
  data: DashboardSummary;
  efficiency: ContextEfficiencyMetrics | null;
};

export function DashboardPanels({ data, efficiency }: DashboardPanelsProps) {
  return (
    <>
      <div className="stat-grid">
        <StatCard label="Workspaces" value={data.workspace_count} hint="Registered repos available to the orchestrator." />
        <StatCard label="Open Tasks" value={data.open_task_count} hint="Work still active in the local queue." />
        <StatCard label="Active Runs" value={data.active_run_count} hint="Current agent execution threads." />
        <StatCard label="Recent Events" value={data.recent_events.length} hint="Events sampled into the summary window." />
        <StatCard label="Redis" value={data.services.redis ?? "unknown"} hint="Dependency state as reported by the orchestrator." />
        <StatCard
          label="Token Savings"
          value={efficiency ? `${efficiency.totals.saved_tokens}` : "n/a"}
          hint={efficiency ? `${efficiency.totals.savings_pct}% reduced from raw bundle size.` : "No bundle metrics yet."}
        />
      </div>

      <div className="content-grid two-column">
        <div className="stack">
          <Surface
            title="Service Envelope"
            description="Core dependency posture for the current runtime."
          >
            <div className="meta-grid">
              {Object.entries(data.services).map(([name, status]) => (
                <div className="meta-card" key={name}>
                  <span className="meta-label">{name}</span>
                  <div className="meta-value">
                    <StatusBadge status={status} />
                  </div>
                </div>
              ))}
            </div>
          </Surface>

          <Surface
            title="Recent Events"
            description="Latest task and autonomy signals reaching the control plane."
          >
            {data.recent_events.length === 0 ? (
              <EmptyState message="No recent events." />
            ) : (
              <div className="event-stream">
                {data.recent_events.slice(0, 8).map((event) => (
                  <div className="event-item" key={event.id}>
                    <p className="item-title">{event.event_type}</p>
                    <p className="item-meta">
                      Task <span className="inline-code">{event.task_id}</span>
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Surface>

          <Surface
            title="Recent Batons"
            description="Handoffs between planner, implementer, reviewer, and analyst roles."
          >
            {data.recent_batons.length === 0 ? (
              <EmptyState message="No baton handoffs yet." />
            ) : (
              <div className="baton-stream">
                {data.recent_batons.slice(0, 8).map((packet) => (
                  <div className="baton-item" key={packet.id}>
                    <p className="item-title">{packet.from_agent} → {packet.to_agent ?? "unassigned"}</p>
                    <p className="item-meta">{packet.summary}</p>
                  </div>
                ))}
              </div>
            )}
          </Surface>
        </div>

        <div className="stack">
          <Surface
            title="Context Efficiency"
            description="Bundle compression performance and layering posture."
            tone="highlight"
          >
            {!efficiency || efficiency.bundle_count === 0 ? (
              <EmptyState message="No context efficiency data yet." />
            ) : (
              <div className="meta-grid">
                <div className="meta-card">
                  <span className="meta-label">Bundles</span>
                  <div className="meta-value">{efficiency.bundle_count}</div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Raw Tokens</span>
                  <div className="meta-value">{efficiency.totals.raw_tokens}</div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Optimized Tokens</span>
                  <div className="meta-value">{efficiency.totals.optimized_tokens}</div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Saved Tokens</span>
                  <div className="meta-value">{efficiency.totals.saved_tokens} ({efficiency.totals.savings_pct}%)</div>
                </div>
                {efficiency.cost_totals ? (
                  <div className="meta-card">
                    <span className="meta-label">Estimated Cost Saved</span>
                    <div className="meta-value">${efficiency.cost_totals.saved_usd.toFixed(4)}</div>
                  </div>
                ) : null}
                {efficiency.layering_comparison ? (
                  <div className="meta-card">
                    <span className="meta-label">Layered vs Legacy</span>
                    <div className="meta-value">{efficiency.layering_comparison.saved_tokens} tokens ({efficiency.layering_comparison.savings_pct}%)</div>
                  </div>
                ) : null}
              </div>
            )}
          </Surface>

          <Surface
            title="Layering Modes"
            description="Distribution of bundle rendering paths in recent assembly output."
          >
            {!efficiency?.layering_modes || Object.keys(efficiency.layering_modes).length === 0 ? (
              <EmptyState message="No layering mode data yet." />
            ) : (
              <div className="stack">
                {Object.entries(efficiency.layering_modes).map(([mode, count]) => (
                  <div className="meta-card" key={mode}>
                    <span className="meta-label">{mode}</span>
                    <div className="meta-value">{count}</div>
                  </div>
                ))}
              </div>
            )}
          </Surface>
        </div>
      </div>
    </>
  );
}
