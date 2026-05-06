import Link from "next/link";
import { useEffect, useState } from "react";

import { listAgentRuns, listTasks } from "../src/lib/api";
import { AgentRun, Task } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";
import { StatusBadge } from "../src/components/StatusBadge";
import { Surface } from "../src/components/Surface";

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
      <div className="page-shell">
        <PageHeader
          title="Run Monitor"
          subtitle="Track which role is executing, where it is attached, and whether the delivery loop is healthy or stalled."
          kicker="Execution Threads"
          actions={<button className="button" onClick={() => void load()}>Refresh Runs</button>}
          metrics={[
            { label: "Active Records", value: runs.length },
            { label: "Live States", value: runs.filter((run) => run.status === "running" || run.status === "in_progress").length },
          ]}
        />

        {loading && <LoadingState message="Loading runs..." />}
        {error && <ErrorState message={error} />}

        <Surface title="Agent Run Ledger" description="Recent execution attempts and the task each run is attached to.">
          {!loading && !error && runs.length === 0 ? (
            <EmptyState
              message="No agent runs have been recorded yet."
              hint="Start a run from a task detail page or use `syncore run start <task_id> --agent-role <role>`."
            />
          ) : runs.length > 0 ? (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Task</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Result</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id}>
                      <td><span className="inline-code">{run.id.slice(0, 8)}...</span></td>
                      <td><Link href={`/tasks/${run.task_id}`}>{tasksById[run.task_id]?.title ?? run.task_id}</Link></td>
                      <td>{run.role}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td className="two-line-clamp">{run.output_summary ?? run.error_message ?? "Awaiting output"}</td>
                      <td>{new Date(run.updated_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Surface>
      </div>
    </Layout>
  );
}
