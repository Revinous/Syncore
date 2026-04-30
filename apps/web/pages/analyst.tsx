import { useEffect, useMemo, useState } from "react";

import { generateDigest, getTaskDigest, listTasks } from "../src/lib/api";
import { AnalystDigest, Task } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";

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
      <button onClick={() => void loadTasks()} style={{ marginBottom: 12 }}>
        Refresh Tasks
      </button>
      {loading && <LoadingState message="Loading tasks..." />}
      {error && <ErrorState message={error} />}
      {!loading && !error && (
        <>
          {tasks.length === 0 ? (
            <EmptyState message="No tasks yet." />
          ) : (
            <section style={{ marginBottom: 16 }}>
              <label htmlFor="task-select">Task</label>{" "}
              <select
                id="task-select"
                value={selectedTaskId}
                onChange={(event) => setSelectedTaskId(event.target.value)}
              >
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.title}
                  </option>
                ))}
              </select>{" "}
              <button onClick={() => void runDigest()} disabled={!selectedTaskId}>
                Generate Digest
              </button>
            </section>
          )}

          {selectedTask ? (
            <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
              <h2>{selectedTask.title}</h2>
              <p>Task ID: {selectedTask.id}</p>
              <p>Status: {selectedTask.status}</p>
              <p>Type: {selectedTask.task_type}</p>
              <p>Complexity: {selectedTask.complexity}</p>
            </section>
          ) : null}

          <section style={{ background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
            <h2>Digest Output</h2>
            {digestLoading ? <LoadingState message="Loading digest..." /> : null}
            {!digest ? (
              <EmptyState message="No digest generated yet." />
            ) : (
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
                    {formatEli5ForDisplay(toEli5(digest))}
                  </div>
                </div>
                <p><strong>Risk:</strong> {digest.risk_level}</p>
                <p><strong>Total events:</strong> {digest.total_events}</p>
                <p><strong>Summary:</strong> {digest.summary}</p>
                <pre>{JSON.stringify(digest, null, 2)}</pre>
              </>
            )}
          </section>
        </>
      )}
    </Layout>
  );
}
