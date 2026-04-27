import Link from "next/link";
import { useEffect, useState } from "react";

import { listAgentRuns, listTasks } from "../src/lib/api";
import { AgentRun, Task } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { StatusBadge } from "../src/components/StatusBadge";

export default function RunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [tasksById, setTasksById] = useState<Record<string, Task>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [runData, taskData] = await Promise.all([listAgentRuns(), listTasks()]);
      setRuns(runData);
      setTasksById(Object.fromEntries(taskData.map((task) => [task.id, task])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Layout title="Agent Runs">
      <button onClick={() => void load()} style={{ marginBottom: 12 }}>Refresh</button>
      {loading && <LoadingState message="Loading runs..." />}
      {error && <ErrorState message={error} />}
      {!loading && !error && runs.length === 0 && <EmptyState message="No agent runs yet." />}

      {runs.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", border: "1px solid #d8dbe2" }}>
          <thead>
            <tr>
              <th align="left">Run ID</th>
              <th align="left">Task</th>
              <th align="left">Role</th>
              <th align="left">Status</th>
              <th align="left">Updated</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{run.id.slice(0, 8)}...</td>
                <td>
                  <Link href={`/tasks/${run.task_id}`}>{tasksById[run.task_id]?.title ?? run.task_id}</Link>
                </td>
                <td>{run.role}</td>
                <td><StatusBadge status={run.status} /></td>
                <td>{new Date(run.updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}
