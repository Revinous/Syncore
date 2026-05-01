import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import {
  createAgentRun,
  generateDigest,
  getTaskModelPolicy,
  getTask,
  getTaskChildren,
  getTaskDigest,
  getTaskRouting,
  listProviderCapabilities,
  listTaskBatonPackets,
  listTaskEvents,
  routeNextAction,
  updateTaskModelPolicy,
} from "../../src/lib/api";
import {
  AgentRun,
  AnalystDigest,
  BatonPacket,
  ProviderCapability,
  ProjectEvent,
  RoutingDecision,
  TaskChildrenBoard,
  TaskDetail,
  TaskModelPolicy,
} from "../../src/lib/types";
import { EmptyState } from "../../src/components/EmptyState";
import { ErrorState } from "../../src/components/ErrorState";
import { Layout } from "../../src/components/Layout";
import { LoadingState } from "../../src/components/LoadingState";
import { StatusBadge } from "../../src/components/StatusBadge";

export default function TaskDetailPage() {
  const router = useRouter();
  const taskId = typeof router.query.taskId === "string" ? router.query.taskId : "";

  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [batons, setBatons] = useState<BatonPacket[]>([]);
  const [routing, setRouting] = useState<RoutingDecision | null>(null);
  const [digest, setDigest] = useState<AnalystDigest | null>(null);
  const [childrenBoard, setChildrenBoard] = useState<TaskChildrenBoard | null>(null);
  const [modelPolicy, setModelPolicy] = useState<TaskModelPolicy | null>(null);
  const [providerCapabilities, setProviderCapabilities] = useState<ProviderCapability[]>([]);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    try {
      const [taskDetail, eventData, batonData] = await Promise.all([
        getTask(taskId),
        listTaskEvents(taskId),
        listTaskBatonPackets(taskId),
      ]);
      setDetail(taskDetail);
      setEvents(eventData);
      setBatons(batonData);
      try {
        setRouting(await getTaskRouting(taskId));
      } catch {
        setRouting(null);
      }
      try {
        setDigest(await getTaskDigest(taskId));
      } catch {
        setDigest(null);
      }
      try {
        setChildrenBoard(await getTaskChildren(taskId));
      } catch {
        setChildrenBoard(null);
      }
      try {
        setModelPolicy(await getTaskModelPolicy(taskId));
      } catch {
        setModelPolicy(null);
      }
      try {
        setProviderCapabilities(await listProviderCapabilities());
      } catch {
        setProviderCapabilities([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load task detail");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [taskId]);

  async function startRun() {
    if (!taskId) return;
    await createAgentRun({ task_id: taskId, role: "coder", status: "running" });
    await load();
  }

  async function routeTask() {
    if (!detail) return;
    const decision = await routeNextAction({
      task_type: detail.task.task_type,
      complexity: detail.task.complexity,
      requires_memory: events.length > 0,
    });
    setRouting(decision);
  }

  async function generateTaskDigest() {
    if (!taskId) return;
    const nextDigest = await generateDigest({ task_id: taskId, limit: 50 });
    setDigest(nextDigest);
  }

  async function saveModelPolicy(formData: FormData) {
    if (!taskId) return;
    setSavingPolicy(true);
    setError(null);
    try {
      const payload = {
        default_provider: String(formData.get("default_provider") || ""),
        default_model: String(formData.get("default_model") || ""),
        plan_provider: String(formData.get("plan_provider") || ""),
        plan_model: String(formData.get("plan_model") || ""),
        execute_provider: String(formData.get("execute_provider") || ""),
        execute_model: String(formData.get("execute_model") || ""),
        review_provider: String(formData.get("review_provider") || ""),
        review_model: String(formData.get("review_model") || ""),
        fallback_order: String(formData.get("fallback_order") || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        optimization_goal: String(formData.get("optimization_goal") || "balanced"),
        allow_cross_provider_switching: formData.get("allow_cross_provider_switching") === "on",
        maintain_context_continuity: formData.get("maintain_context_continuity") === "on",
        minimum_context_window: Number(formData.get("minimum_context_window") || 0),
        max_latency_tier: String(formData.get("max_latency_tier") || "") || null,
        max_cost_tier: String(formData.get("max_cost_tier") || "") || null,
        prefer_reviewer_provider: formData.get("prefer_reviewer_provider") === "on",
      };
      const next = await updateTaskModelPolicy(taskId, payload);
      setModelPolicy(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save model strategy");
    } finally {
      setSavingPolicy(false);
    }
  }

  function eli5Text(value: AnalystDigest): string {
    const text = (value.eli5_summary || "").trim();
    if (text) return text;
    const top = Object.entries(value.event_breakdown || {})
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 2)
      .map(([name, count]) => `${name} (${count})`)
      .join(", ");
    const latest = value.highlights?.[0] || "no recent highlight";
    return (
      `Simple summary: ${value.headline}. ` +
      `Top signals: ${top || "none"}. ` +
      `Latest: ${latest}. ` +
      `Risk: ${value.risk_level}.`
    );
  }

  function formatEli5ForDisplay(text: string): string {
    return text.replace(/\. /g, ".\n");
  }

  function providerSummary(provider: string) {
    const item = providerCapabilities.find((row) => row.provider === provider);
    if (!item) return null;
    return `ctx ${item.max_context_tokens.toLocaleString()} | quality ${item.quality_tier}/5 | speed ${item.speed_tier}/5 | cost ${item.cost_tier}/5`;
  }

  return (
    <Layout title="Task Detail">
      {loading && <LoadingState message="Loading task detail..." />}
      {error && <ErrorState message={error} />}
      {detail && (
        <>
          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>{detail.task.title}</h2>
            <p>Task ID: {detail.task.id}</p>
            <p>Type: {detail.task.task_type}</p>
            <p>Complexity: {detail.task.complexity}</p>
            <p>Status: <StatusBadge status={detail.task.status} /></p>
            <button onClick={() => void startRun()}>Start agent run</button>{" "}
            <button onClick={() => void routeTask()}>Route next action</button>{" "}
            <button onClick={() => void generateTaskDigest()}>Generate digest</button>{" "}
            <button onClick={() => void load()}>Refresh</button>
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Agent Runs</h2>
            {detail.agent_runs.length === 0 ? (
              <EmptyState message="No runs yet." />
            ) : (
              <ul>
                {detail.agent_runs.map((run: AgentRun) => (
                  <li key={run.id}>
                    {run.role} <StatusBadge status={run.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Model Strategy</h2>
            {!modelPolicy ? (
              <EmptyState message="No model strategy loaded." />
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveModelPolicy(new FormData(event.currentTarget));
                }}
              >
                <p>
                  Default provider and model are the baseline. Stage fields can override plan, execute, and review independently. Arbitration then applies your cost, speed, context, and continuity rules.
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                  <label>
                    Default provider
                    <input name="default_provider" defaultValue={modelPolicy.default_provider} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Default model
                    <input name="default_model" defaultValue={modelPolicy.default_model} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Plan provider
                    <input name="plan_provider" defaultValue={modelPolicy.plan.provider ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Plan model
                    <input name="plan_model" defaultValue={modelPolicy.plan.model ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Execute provider
                    <input name="execute_provider" defaultValue={modelPolicy.execute.provider ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Execute model
                    <input name="execute_model" defaultValue={modelPolicy.execute.model ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Review provider
                    <input name="review_provider" defaultValue={modelPolicy.review.provider ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Review model
                    <input name="review_model" defaultValue={modelPolicy.review.model ?? ""} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Optimization goal
                    <select name="optimization_goal" defaultValue={modelPolicy.optimization_goal} style={{ display: "block", width: "100%" }}>
                      <option value="balanced">balanced</option>
                      <option value="quality">quality</option>
                      <option value="speed">speed</option>
                      <option value="cost">cost</option>
                      <option value="context">context</option>
                    </select>
                  </label>
                  <label>
                    Minimum context window
                    <input name="minimum_context_window" type="number" min={0} defaultValue={modelPolicy.minimum_context_window} style={{ display: "block", width: "100%" }} />
                  </label>
                  <label>
                    Max latency tier
                    <select name="max_latency_tier" defaultValue={modelPolicy.max_latency_tier ?? ""} style={{ display: "block", width: "100%" }}>
                      <option value="">any</option>
                      <option value="fast">fast</option>
                      <option value="medium">medium</option>
                      <option value="slow">slow</option>
                    </select>
                  </label>
                  <label>
                    Max cost tier
                    <select name="max_cost_tier" defaultValue={modelPolicy.max_cost_tier ?? ""} style={{ display: "block", width: "100%" }}>
                      <option value="">any</option>
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                    </select>
                  </label>
                  <label style={{ gridColumn: "1 / -1" }}>
                    Fallback order
                    <input name="fallback_order" defaultValue={modelPolicy.fallback_order.join(", ")} style={{ display: "block", width: "100%" }} />
                  </label>
                </div>
                <div style={{ marginTop: 12 }}>
                  <label style={{ marginRight: 12 }}>
                    <input
                      name="allow_cross_provider_switching"
                      type="checkbox"
                      defaultChecked={modelPolicy.allow_cross_provider_switching}
                    />{" "}
                    allow cross-provider switching
                  </label>
                  <label style={{ marginRight: 12 }}>
                    <input
                      name="maintain_context_continuity"
                      type="checkbox"
                      defaultChecked={modelPolicy.maintain_context_continuity}
                    />{" "}
                    maintain context continuity
                  </label>
                  <label>
                    <input
                      name="prefer_reviewer_provider"
                      type="checkbox"
                      defaultChecked={modelPolicy.prefer_reviewer_provider}
                    />{" "}
                    prefer reviewer provider
                  </label>
                </div>
                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={savingPolicy}>
                    {savingPolicy ? "Saving..." : "Save strategy"}
                  </button>
                </div>
                {providerCapabilities.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <strong>Configured providers</strong>
                    <ul>
                      {providerCapabilities.map((item) => (
                        <li key={item.provider}>
                          {item.provider}: {providerSummary(item.provider)}; strengths {item.strengths.join(", ")}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </form>
            )}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Child Tasks</h2>
            {!childrenBoard || !childrenBoard.has_children ? (
              <EmptyState message="No spawned child tasks." />
            ) : (
              <>
                <p>
                  Total: {childrenBoard.total_children} | Completed: {childrenBoard.completed_children} | Active: {childrenBoard.active_children} | Blocked: {childrenBoard.blocked_children}
                </p>
                <ul>
                  {childrenBoard.children.map((child) => (
                    <li key={child.task_id}>
                      {child.title} [{child.status}] ({child.task_type}/{child.complexity})
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Event Timeline</h2>
            {events.length === 0 ? (
              <EmptyState message="No events." />
            ) : (
              <ul>
                {events.map((event) => (
                  <li key={event.id}>{event.event_type}</li>
                ))}
              </ul>
            )}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Baton Packets</h2>
            {batons.length === 0 ? (
              <EmptyState message="No baton handoffs." />
            ) : (
              <ul>
                {batons.map((packet) => (
                  <li key={packet.id}>
                    {packet.from_agent} → {packet.to_agent ?? "unassigned"}: {packet.summary}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Routing Decision</h2>
            {routing ? <pre>{JSON.stringify(routing, null, 2)}</pre> : <EmptyState message="No routing decision yet." />}
          </section>

          <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Analyst Digest</h2>
            {digest ? (
              <>
                <p><strong>Headline:</strong> {digest.headline}</p>
                <div>
                  <strong>ELI5:</strong>
                  <div
                    style={{
                      marginTop: 6,
                      padding: "8px 10px",
                      border: "1px solid #e5e7eb",
                      borderRadius: 6,
                      background: "#f9fafb",
                      whiteSpace: "pre-wrap",
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                      lineHeight: 1.5,
                    }}
                  >
                    {formatEli5ForDisplay(eli5Text(digest))}
                  </div>
                </div>
                <p><strong>Risk:</strong> {digest.risk_level}</p>
                <p><strong>Total events:</strong> {digest.total_events}</p>
                <pre>{JSON.stringify(digest, null, 2)}</pre>
              </>
            ) : (
              <EmptyState message="No digest yet." />
            )}
          </section>
        </>
      )}
    </Layout>
  );
}
