import type {
  AnalystDigest,
  BatonPacket,
  ProjectEvent,
  RoutingDecision,
  TaskChildrenBoard,
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { Surface } from "./Surface";

type TaskActivityPanelsProps = {
  digest: AnalystDigest | null;
  events: ProjectEvent[];
  batons: BatonPacket[];
  routing: RoutingDecision | null;
  childrenBoard: TaskChildrenBoard | null;
  eli5Text: (value: AnalystDigest) => string;
  formatEli5ForDisplay: (text: string) => string;
};

export function TaskActivityPanels({
  digest,
  events,
  batons,
  routing,
  childrenBoard,
  eli5Text,
  formatEli5ForDisplay,
}: TaskActivityPanelsProps) {
  return (
    <>
      <Surface title="Child Tasks" description="Planner fanout and current completion board.">
        {!childrenBoard || !childrenBoard.has_children ? (
          <EmptyState
            message="No spawned child tasks were recorded for this task."
            hint="Planner fanout appears here when autonomy decomposes the parent task into implementation, review, or analysis children."
          />
        ) : (
          <>
            <div className="meta-grid">
              <div className="meta-card"><span className="meta-label">Total</span><div className="meta-value">{childrenBoard.total_children}</div></div>
              <div className="meta-card"><span className="meta-label">Completed</span><div className="meta-value">{childrenBoard.completed_children}</div></div>
              <div className="meta-card"><span className="meta-label">Active</span><div className="meta-value">{childrenBoard.active_children}</div></div>
              <div className="meta-card"><span className="meta-label">Blocked</span><div className="meta-value">{childrenBoard.blocked_children}</div></div>
            </div>
            <div className="stack" style={{ marginTop: 16 }}>
              {childrenBoard.children.map((child) => (
                <div className="meta-card" key={child.task_id}>
                  <span className="meta-label">{child.task_type} / {child.complexity}</span>
                  <div className="meta-value">{child.title} · {child.status}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </Surface>

      <Surface title="Routing Decision" description="Latest next-action route computed for this task.">
        {routing ? (
          <div className="code-block">{JSON.stringify(routing, null, 2)}</div>
        ) : (
          <EmptyState
            message="No routing decision has been recorded yet."
            hint="Use “Route next action” to ask the orchestrator which worker role and model tier should act next."
          />
        )}
      </Surface>

      <Surface title="Analyst Digest" description="Readable interpretation of the task stream." tone="highlight">
        {digest ? (
          <div className="stack">
            <div className="callout">
              <p className="callout-title">Headline</p>
              <p className="callout-copy">{digest.headline}</p>
            </div>
            <div className="callout">
              <p className="callout-title">ELI5</p>
              <p className="callout-copy" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {formatEli5ForDisplay(eli5Text(digest))}
              </p>
            </div>
            <div className="meta-grid">
              <div className="meta-card"><span className="meta-label">Risk</span><div className="meta-value">{digest.risk_level}</div></div>
              <div className="meta-card"><span className="meta-label">Total Events</span><div className="meta-value">{digest.total_events}</div></div>
            </div>
            <div className="code-block">{JSON.stringify(digest, null, 2)}</div>
          </div>
        ) : (
          <EmptyState
            message="No digest has been generated for this task yet."
            hint="Generate a digest after events, runs, or baton handoffs exist so the analyst can explain what changed and why it matters."
          />
        )}
      </Surface>

      <Surface title="Event Timeline" description="Raw project events attached to this task.">
        {events.length === 0 ? (
          <EmptyState
            message="No task events were recorded yet."
            hint="Execution, baton handoffs, approval gates, and analyst generation all leave events here."
          />
        ) : (
          <div className="event-stream">
            {events.map((event) => (
              <div className="event-item" key={event.id}>
                <p className="item-title">{event.event_type}</p>
                <p className="item-meta">
                  {event.created_at ? new Date(event.created_at).toLocaleString() : "timestamp unavailable"}
                </p>
              </div>
            ))}
          </div>
        )}
      </Surface>

      <Surface title="Baton Packets" description="Role handoffs and summarized transfer context.">
        {batons.length === 0 ? (
          <EmptyState
            message="No baton handoffs were recorded."
            hint="Planner, implementer, reviewer, and analyst handoffs appear here once the task moves through the multi-agent loop."
          />
        ) : (
          <div className="baton-stream">
            {batons.map((packet) => (
              <div className="baton-item" key={packet.id}>
                <p className="item-title">{packet.from_agent} → {packet.to_agent ?? "unassigned"}</p>
                <p className="item-meta">{packet.summary}</p>
              </div>
            ))}
          </div>
        )}
      </Surface>
    </>
  );
}
