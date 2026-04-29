import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import {
  createAgentRun,
  generateDigest,
  getTask,
  getTaskDigest,
  getTaskRouting,
  listTaskBatonPackets,
  listTaskEvents,
  routeNextAction,
} from "../../src/lib/api";
import { AgentRun, AnalystDigest, BatonPacket, ProjectEvent, RoutingDecision, TaskDetail } from "../../src/lib/types";
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
                <p><strong>ELI5:</strong> {eli5Text(digest)}</p>
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
