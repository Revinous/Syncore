import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import {
  createAgentRun,
  generateDigest,
  getTaskModelPolicy,
  getTaskExecutionReport,
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
  TaskExecutionReport,
  TaskModelPolicy,
} from "../../src/lib/types";
import { EmptyState } from "../../src/components/EmptyState";
import { ErrorState } from "../../src/components/ErrorState";
import { Layout } from "../../src/components/Layout";
import { LoadingState } from "../../src/components/LoadingState";
import { PageHeader } from "../../src/components/PageHeader";
import { StatusBadge } from "../../src/components/StatusBadge";
import { Surface } from "../../src/components/Surface";

export default function TaskDetailPage() {
  const router = useRouter();
  const taskId = typeof router.query.taskId === "string" ? router.query.taskId : "";

  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [batons, setBatons] = useState<BatonPacket[]>([]);
  const [routing, setRouting] = useState<RoutingDecision | null>(null);
  const [digest, setDigest] = useState<AnalystDigest | null>(null);
  const [childrenBoard, setChildrenBoard] = useState<TaskChildrenBoard | null>(null);
  const [executionReport, setExecutionReport] = useState<TaskExecutionReport | null>(null);
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
        setExecutionReport(await getTaskExecutionReport(taskId));
      } catch {
        setExecutionReport(null);
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
      <div className="page-shell">
        <PageHeader
          title={detail?.task.title ?? "Task Detail"}
          subtitle="Inspect a single task across task metadata, child execution, baton handoffs, routing, and the model strategy shaping autonomy behavior."
          kicker="Task Control"
          actions={
            <>
              <button className="secondary-button" onClick={() => void startRun()} disabled={!detail}>Start agent run</button>
              <button className="secondary-button" onClick={() => void routeTask()} disabled={!detail}>Route next action</button>
              <button className="button" onClick={() => void generateTaskDigest()} disabled={!detail}>Generate digest</button>
              <button className="ghost-button" onClick={() => void load()}>Refresh</button>
            </>
          }
          metrics={[
            { label: "Task Status", value: detail ? <StatusBadge status={detail.task.status} /> : "loading" },
            { label: "Task Type", value: detail?.task.task_type ?? "n/a" },
            { label: "Complexity", value: detail?.task.complexity ?? "n/a" },
          ]}
        />

        {loading && <LoadingState message="Loading task detail..." />}
        {error && <ErrorState message={error} />}

        {detail ? (
          <>
            <div className="content-grid two-column">
              <div className="stack">
                <Surface title="Task Overview" description="Core task metadata and current execution posture.">
                  <div className="meta-grid">
                    <div className="meta-card"><span className="meta-label">Task ID</span><div className="meta-value">{detail.task.id}</div></div>
                    <div className="meta-card"><span className="meta-label">Task Type</span><div className="meta-value">{detail.task.task_type}</div></div>
                    <div className="meta-card"><span className="meta-label">Complexity</span><div className="meta-value">{detail.task.complexity}</div></div>
                    <div className="meta-card"><span className="meta-label">Status</span><div className="meta-value"><StatusBadge status={detail.task.status} /></div></div>
                  </div>
                </Surface>

                <Surface title="Agent Runs" description="Runs already attached to this task.">
                  {detail.agent_runs.length === 0 ? (
                    <EmptyState message="No runs yet." />
                  ) : (
                    <div className="stack">
                      {detail.agent_runs.map((run: AgentRun) => (
                        <div className="meta-card" key={run.id}>
                          <span className="meta-label">{run.role}</span>
                          <div className="meta-value"><StatusBadge status={run.status} /></div>
                        </div>
                      ))}
                    </div>
                  )}
                </Surface>

                <Surface title="Child Tasks" description="Planner fanout and current completion board.">
                  {!childrenBoard || !childrenBoard.has_children ? (
                    <EmptyState message="No spawned child tasks." />
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
                  {routing ? <div className="code-block">{JSON.stringify(routing, null, 2)}</div> : <EmptyState message="No routing decision yet." />}
                </Surface>
              </div>

              <div className="stack">
                <Surface title="Analyst Digest" description="Readable interpretation of the task stream." tone="highlight">
                  {digest ? (
                    <div className="stack">
                      <div className="callout">
                        <strong>Headline</strong>
                        <div>{digest.headline}</div>
                      </div>
                      <div className="callout">
                        <strong>ELI5</strong>
                        <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{formatEli5ForDisplay(eli5Text(digest))}</div>
                      </div>
                      <div className="meta-grid">
                        <div className="meta-card"><span className="meta-label">Risk</span><div className="meta-value">{digest.risk_level}</div></div>
                        <div className="meta-card"><span className="meta-label">Total Events</span><div className="meta-value">{digest.total_events}</div></div>
                      </div>
                      <div className="code-block">{JSON.stringify(digest, null, 2)}</div>
                    </div>
                  ) : (
                    <EmptyState message="No digest yet." />
                  )}
                </Surface>

                <Surface title="Event Timeline" description="Raw project events attached to this task.">
                  {events.length === 0 ? (
                    <EmptyState message="No events." />
                  ) : (
                    <div className="event-stream">
                      {events.map((event: ProjectEvent) => (
                        <div className="event-item" key={event.id}>
                          <p className="item-title">{event.event_type}</p>
                          <p className="item-meta">{event.created_at ? new Date(event.created_at).toLocaleString() : "timestamp unavailable"}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </Surface>

                <Surface title="Baton Packets" description="Role handoffs and summarized transfer context.">
                  {batons.length === 0 ? (
                    <EmptyState message="No baton handoffs." />
                  ) : (
                    <div className="baton-stream">
                      {batons.map((packet: BatonPacket) => (
                        <div className="baton-item" key={packet.id}>
                          <p className="item-title">{packet.from_agent} → {packet.to_agent ?? "unassigned"}</p>
                          <p className="item-meta">{packet.summary}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </Surface>
              </div>
            </div>

            <Surface
              title="Execution Outcome"
              description="Everything an operator needs in one place: why the task succeeded or failed, what changed, what commands ran, and what the models actually produced."
              tone="highlight"
            >
              {!executionReport ? (
                <EmptyState message="No execution report recorded yet." />
              ) : (
                <div className="stack">
                  <div className="meta-grid">
                    <div className="meta-card">
                      <span className="meta-label">Outcome</span>
                      <div className="meta-value"><StatusBadge status={executionReport.outcome_status} /></div>
                    </div>
                    <div className="meta-card">
                      <span className="meta-label">Meaningful Change</span>
                      <div className="meta-value">{executionReport.meaningful_change ? "yes" : "no"}</div>
                    </div>
                    <div className="meta-card">
                      <span className="meta-label">Verification</span>
                      <div className="meta-value">{executionReport.verification_status ?? "n/a"}</div>
                    </div>
                    <div className="meta-card">
                      <span className="meta-label">Updated</span>
                      <div className="meta-value">{executionReport.last_updated_at ? new Date(executionReport.last_updated_at).toLocaleString() : "n/a"}</div>
                    </div>
                  </div>

                  <div className="callout">
                    <strong>Why it ended this way</strong>
                    <div>{executionReport.summary_reason}</div>
                    {executionReport.verification_reason ? (
                      <div className="helper-text" style={{ marginTop: 8 }}>{executionReport.verification_reason}</div>
                    ) : null}
                  </div>

                  <div className="panel-grid two-up">
                    <div className="callout">
                      <strong>Changed Files</strong>
                      {executionReport.changed_files.length === 0 ? (
                        <div className="helper-text">No changed files recorded.</div>
                      ) : (
                        <ul className="list-reset">
                          {executionReport.changed_files.map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      )}
                    </div>
                    <div className="callout">
                      <strong>Planned Actions</strong>
                      {executionReport.planned_actions.length === 0 ? (
                        <div className="helper-text">No planned actions recorded.</div>
                      ) : (
                        <ul className="list-reset">
                          {executionReport.planned_actions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>

                  <div className="panel-grid two-up">
                    <div className="surface inset">
                      <div className="section-header">
                        <div>
                          <h3 className="section-title">Verification Commands</h3>
                          <p className="section-copy">Command execution status and output excerpts.</p>
                        </div>
                      </div>
                      {executionReport.verification_commands.length === 0 ? (
                        <EmptyState message="No verification command results were persisted for this task." />
                      ) : (
                        <div className="stack">
                          {executionReport.verification_commands.map((item, index) => (
                            <div className="meta-card" key={`${index}-${item.command}`}>
                              <div className="section-header" style={{ marginBottom: 8 }}>
                                <span className="inline-code">{item.command}</span>
                                <StatusBadge status={item.status} />
                              </div>
                              {item.output_preview ? <div className="code-block">{item.output_preview}</div> : null}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="surface inset">
                      <div className="section-header">
                        <div>
                          <h3 className="section-title">Run Outputs</h3>
                          <p className="section-copy">What each run returned or why it failed.</p>
                        </div>
                      </div>
                      {executionReport.output_artifacts.length === 0 ? (
                        <EmptyState message="No run outputs recorded." />
                      ) : (
                        <div className="stack">
                          {executionReport.output_artifacts.map((item) => (
                            <div className="meta-card" key={item.run_id}>
                              <div className="section-header" style={{ marginBottom: 8 }}>
                                <div>
                                  <div className="item-title">{item.role}</div>
                                  <div className="item-meta">{item.provider ?? "unknown"} · {item.target_model ?? "unknown"} · {new Date(item.updated_at).toLocaleString()}</div>
                                </div>
                                <StatusBadge status={item.status} />
                              </div>
                              {item.error_message ? <div className="error-state">{item.error_message}</div> : null}
                              {item.output_preview ? <div className="code-block">{item.output_preview}</div> : null}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="surface inset">
                    <div className="section-header">
                      <div>
                        <h3 className="section-title">File Diffs</h3>
                        <p className="section-copy">Persisted diff artifacts stored by Syncore during workspace execution.</p>
                      </div>
                    </div>
                    {executionReport.diff_artifacts.length === 0 ? (
                      <EmptyState message="No diff artifacts recorded." />
                    ) : (
                      <div className="stack">
                        {executionReport.diff_artifacts.map((artifact) => (
                          <div className="meta-card" key={artifact.ref_id}>
                            <div className="section-header" style={{ marginBottom: 8 }}>
                              <div>
                                <div className="item-title">{artifact.path}</div>
                                <div className="item-meta">{artifact.summary}</div>
                              </div>
                              <span className="label-chip">{artifact.content_type}</span>
                            </div>
                            <div className="helper-text" style={{ marginBottom: 8 }}>{artifact.retrieval_hint}</div>
                            <div className="code-block">{artifact.preview}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </Surface>

            <Surface title="Model Strategy" description="Per-stage provider and model policy used by autonomy arbitration.">
              {!modelPolicy ? (
                <EmptyState message="No model strategy loaded." />
              ) : (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void saveModelPolicy(new FormData(event.currentTarget));
                  }}
                  className="stack"
                >
                  <div className="helper-text">
                    Default provider and model are the baseline. Stage fields can override plan, execute, and review independently. Arbitration then applies your cost, speed, context, and continuity rules.
                  </div>
                  <div className="form-grid two-up">
                    <label className="field-label">
                      Default provider
                      <input className="field" name="default_provider" defaultValue={modelPolicy.default_provider} />
                    </label>
                    <label className="field-label">
                      Default model
                      <input className="field" name="default_model" defaultValue={modelPolicy.default_model} />
                    </label>
                    <label className="field-label">
                      Plan provider
                      <input className="field" name="plan_provider" defaultValue={modelPolicy.plan.provider ?? ""} />
                    </label>
                    <label className="field-label">
                      Plan model
                      <input className="field" name="plan_model" defaultValue={modelPolicy.plan.model ?? ""} />
                    </label>
                    <label className="field-label">
                      Execute provider
                      <input className="field" name="execute_provider" defaultValue={modelPolicy.execute.provider ?? ""} />
                    </label>
                    <label className="field-label">
                      Execute model
                      <input className="field" name="execute_model" defaultValue={modelPolicy.execute.model ?? ""} />
                    </label>
                    <label className="field-label">
                      Review provider
                      <input className="field" name="review_provider" defaultValue={modelPolicy.review.provider ?? ""} />
                    </label>
                    <label className="field-label">
                      Review model
                      <input className="field" name="review_model" defaultValue={modelPolicy.review.model ?? ""} />
                    </label>
                    <label className="field-label">
                      Optimization goal
                      <select className="field" name="optimization_goal" defaultValue={modelPolicy.optimization_goal}>
                        <option value="balanced">balanced</option>
                        <option value="quality">quality</option>
                        <option value="speed">speed</option>
                        <option value="cost">cost</option>
                        <option value="context">context</option>
                      </select>
                    </label>
                    <label className="field-label">
                      Minimum context window
                      <input className="field" name="minimum_context_window" type="number" min={0} defaultValue={modelPolicy.minimum_context_window} />
                    </label>
                    <label className="field-label">
                      Max latency tier
                      <select className="field" name="max_latency_tier" defaultValue={modelPolicy.max_latency_tier ?? ""}>
                        <option value="">any</option>
                        <option value="fast">fast</option>
                        <option value="medium">medium</option>
                        <option value="slow">slow</option>
                      </select>
                    </label>
                    <label className="field-label">
                      Max cost tier
                      <select className="field" name="max_cost_tier" defaultValue={modelPolicy.max_cost_tier ?? ""}>
                        <option value="">any</option>
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                      </select>
                    </label>
                    <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                      Fallback order
                      <input className="field" name="fallback_order" defaultValue={modelPolicy.fallback_order.join(", ")} />
                    </label>
                  </div>
                  <div className="checkbox-row">
                    <label className="checkbox-label"><input name="allow_cross_provider_switching" type="checkbox" defaultChecked={modelPolicy.allow_cross_provider_switching} /> allow cross-provider switching</label>
                    <label className="checkbox-label"><input name="maintain_context_continuity" type="checkbox" defaultChecked={modelPolicy.maintain_context_continuity} /> maintain context continuity</label>
                    <label className="checkbox-label"><input name="prefer_reviewer_provider" type="checkbox" defaultChecked={modelPolicy.prefer_reviewer_provider} /> prefer reviewer provider</label>
                  </div>
                  <div className="control-row">
                    <button className="button" type="submit" disabled={savingPolicy}>{savingPolicy ? "Saving..." : "Save strategy"}</button>
                  </div>
                  {providerCapabilities.length > 0 ? (
                    <div className="panel-grid two-up">
                      {providerCapabilities.map((item) => (
                        <div className="meta-card" key={item.provider}>
                          <span className="meta-label">{item.provider}</span>
                          <div className="meta-value">{providerSummary(item.provider)}; strengths {item.strengths.join(", ")}</div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </form>
              )}
            </Surface>
          </>
        ) : null}
      </div>
    </Layout>
  );
}
