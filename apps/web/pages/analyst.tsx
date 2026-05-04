import { useEffect, useMemo, useState } from "react";

import { generateDigest, getTaskDigest, listTasks } from "../src/lib/api";
import { AnalystDigest, Task } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";
import { Surface } from "../src/components/Surface";

function toEli5(digest: AnalystDigest | null): string {
  if (!digest) return "";
  const raw = (digest.eli5_summary || "").trim();
  if (raw) return raw;
  const top = Object.entries(digest.event_breakdown || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 2)
    .map(([name, count]) => `${name} (${count})`)
    .join(", ");
  const latest = digest.highlights?.[0] || "no recent highlight";
  return (
    `Simple summary: ${digest.headline}. ` +
    `Top signals: ${top || "none"}. ` +
    `Latest: ${latest}. ` +
    `Risk: ${digest.risk_level}.`
  );
}

function formatEli5ForDisplay(text: string): string {
  return text.replace(/\. /g, ".\n");
}

export default function AnalystPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>("");
  const [digest, setDigest] = useState<AnalystDigest | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? null,
    [tasks, selectedTaskId]
  );

  async function loadTasks() {
    setLoading(true);
    setError(null);
    try {
      const data = await listTasks(200);
      setTasks(data);
      if (!selectedTaskId && data.length > 0) {
        setSelectedTaskId(data[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }

  async function runDigest() {
    if (!selectedTaskId) return;
    setError(null);
    setDigestLoading(true);
    try {
      const d = await generateDigest({ task_id: selectedTaskId, limit: 100 });
      setDigest(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate digest");
    } finally {
      setDigestLoading(false);
    }
  }

  async function loadDigest(taskId: string) {
    if (!taskId) return;
    setDigestLoading(true);
    setDigest(null);
    setError(null);
    try {
      const d = await getTaskDigest(taskId);
      setDigest(d);
    } catch {
      setDigest(null);
    } finally {
      setDigestLoading(false);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, []);

  useEffect(() => {
    if (!selectedTaskId) {
      setDigest(null);
      return;
    }
    void loadDigest(selectedTaskId);
  }, [selectedTaskId]);

  return (
    <Layout title="Analyst Digest">
      <div className="page-shell">
        <PageHeader
          title="Analyst Lens"
          subtitle="Translate task execution into human-readable status, risk, and practical impact without forcing the operator to read raw event streams."
          kicker="Human Readability"
          actions={
            <>
              <button className="secondary-button" onClick={() => void loadTasks()}>Refresh Tasks</button>
              <button className="button" onClick={() => void runDigest()} disabled={!selectedTaskId}>Generate Digest</button>
            </>
          }
          metrics={[
            { label: "Tasks", value: tasks.length },
            { label: "Selected", value: selectedTask?.title ?? "none" },
          ]}
        />

        {loading && <LoadingState message="Loading tasks..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error ? (
          <div className="content-grid two-column">
            <div className="stack">
              <Surface title="Digest Target" description="Choose a task, then generate or refresh the ELI5 digest for that specific execution stream.">
                {tasks.length === 0 ? (
                  <EmptyState message="No tasks yet." />
                ) : (
                  <div className="form-grid two-up">
                    <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                      Task
                      <select className="field" id="task-select" value={selectedTaskId} onChange={(event) => setSelectedTaskId(event.target.value)}>
                        {tasks.map((task) => (
                          <option key={task.id} value={task.id}>{task.title}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}
              </Surface>

              {selectedTask ? (
                <Surface title="Selected Task" description="Task metadata that the digest is summarizing.">
                  <div className="meta-grid">
                    <div className="meta-card"><span className="meta-label">Task ID</span><div className="meta-value">{selectedTask.id}</div></div>
                    <div className="meta-card"><span className="meta-label">Status</span><div className="meta-value">{selectedTask.status}</div></div>
                    <div className="meta-card"><span className="meta-label">Type</span><div className="meta-value">{selectedTask.task_type}</div></div>
                    <div className="meta-card"><span className="meta-label">Complexity</span><div className="meta-value">{selectedTask.complexity}</div></div>
                  </div>
                </Surface>
              ) : null}
            </div>

            <div className="stack">
              <Surface title="Digest Output" description="This should explain what changed, why it matters, and what the operator needs to know next." tone="highlight">
                {digestLoading ? <LoadingState message="Loading digest..." /> : null}
                {!digest ? (
                  <EmptyState message="No digest generated yet." />
                ) : (
                  <div className="stack">
                    <div className="callout">
                      <strong>Headline</strong>
                      <div>{digest.headline}</div>
                    </div>
                    <div className="callout">
                      <strong>ELI5</strong>
                      <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{formatEli5ForDisplay(toEli5(digest))}</div>
                    </div>
                    <div className="meta-grid">
                      <div className="meta-card"><span className="meta-label">Risk</span><div className="meta-value">{digest.risk_level}</div></div>
                      <div className="meta-card"><span className="meta-label">Total Events</span><div className="meta-value">{digest.total_events}</div></div>
                    </div>
                    <div className="callout">
                      <strong>Summary</strong>
                      <div>{digest.summary}</div>
                    </div>
                    <div className="code-block">{JSON.stringify(digest, null, 2)}</div>
                  </div>
                )}
              </Surface>
            </div>
          </div>
        ) : null}
      </div>
    </Layout>
  );
}
