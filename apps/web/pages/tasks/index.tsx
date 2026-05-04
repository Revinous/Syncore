import Link from "next/link";
import { useRouter } from "next/router";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { createTask, listTasks, listWorkspaces } from "../../src/lib/api";
import { Task, Workspace } from "../../src/lib/types";
import { EmptyState } from "../../src/components/EmptyState";
import { ErrorState } from "../../src/components/ErrorState";
import { Layout } from "../../src/components/Layout";
import { LoadingState } from "../../src/components/LoadingState";
import { PageHeader } from "../../src/components/PageHeader";
import { StatusBadge } from "../../src/components/StatusBadge";
import { Surface } from "../../src/components/Surface";

export default function TasksPage() {
  const router = useRouter();
  const workspaceQuery = typeof router.query.workspace === "string" ? router.query.workspace : "all";

  const [tasks, setTasks] = useState<Task[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("Analyze auth flow");
  const [taskType, setTaskType] = useState("analysis");
  const [complexity, setComplexity] = useState("medium");
  const [workspaceId, setWorkspaceId] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [workspaceFilter, setWorkspaceFilter] = useState("all");

  useEffect(() => {
    if (workspaceQuery && workspaceQuery !== workspaceFilter) {
      setWorkspaceFilter(workspaceQuery);
    }
  }, [workspaceFilter, workspaceQuery]);

  const filtered = useMemo(
    () => tasks.filter((task) => statusFilter === "all" || task.status === statusFilter),
    [tasks, statusFilter]
  );

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const selectedWorkspaceId = workspaceFilter === "all" ? undefined : workspaceFilter;
      const [taskData, workspaceData] = await Promise.all([
        listTasks(100, selectedWorkspaceId),
        listWorkspaces(),
      ]);
      setTasks(taskData);
      setWorkspaces(workspaceData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [workspaceFilter]);

  async function onCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await createTask({
        title,
        task_type: taskType,
        complexity,
        workspace_id: workspaceId || null,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    }
  }

  return (
    <Layout title="Tasks">
      <div className="page-shell">
        <PageHeader
          title="Task Orchestration"
          subtitle="Create scoped work, filter the queue, and inspect what the orchestrator is handing off to planner, implementer, reviewer, and analyst roles."
          kicker="Execution Queue"
          actions={
            <>
              <button className="secondary-button" onClick={() => void load()}>Refresh Queue</button>
              <Link href="/runs" className="ghost-button">View Agent Runs</Link>
            </>
          }
          metrics={[
            { label: "Visible Tasks", value: filtered.length },
            { label: "Workspace Scope", value: workspaceFilter === "all" ? "all" : (workspaces.find((w) => w.id === workspaceFilter)?.name ?? "filtered") },
          ]}
        />

        {loading && <LoadingState message="Loading tasks..." />}
        {error && <ErrorState message={error} />}

        <div className="content-grid two-column">
          <div className="stack">
            <Surface title="Create Task" description="Open a new unit of work with explicit type and complexity. Attach a workspace when the task should mutate a repo.">
              <form onSubmit={onCreateTask} className="form-grid two-up">
                <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                  Task title
                  <input className="field" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Analyze auth flow" required />
                </label>
                <label className="field-label">
                  Workspace
                  <select className="field" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
                    <option value="">No workspace</option>
                    {workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Task type
                  <select className="field" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
                    <option value="analysis">analysis</option>
                    <option value="implementation">implementation</option>
                    <option value="integration">integration</option>
                    <option value="review">review</option>
                    <option value="memory_retrieval">memory_retrieval</option>
                    <option value="memory_update">memory_update</option>
                  </select>
                </label>
                <label className="field-label">
                  Complexity
                  <select className="field" value={complexity} onChange={(event) => setComplexity(event.target.value)}>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                </label>
                <div className="control-row" style={{ gridColumn: "1 / -1" }}>
                  <button className="button" type="submit">Create Task</button>
                </div>
              </form>
            </Surface>
          </div>

          <div className="stack">
            <Surface title="Queue Filters" description="Narrow the current view to the tasks that matter now." tone="inset">
              <div className="form-grid two-up">
                <label className="field-label">
                  Status
                  <select className="field" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                    <option value="all">all</option>
                    <option value="new">new</option>
                    <option value="in_progress">in_progress</option>
                    <option value="blocked">blocked</option>
                    <option value="completed">completed</option>
                  </select>
                </label>
                <label className="field-label">
                  Workspace
                  <select className="field" value={workspaceFilter} onChange={(event) => setWorkspaceFilter(event.target.value)}>
                    <option value="all">all</option>
                    {workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                    ))}
                  </select>
                </label>
              </div>
            </Surface>
          </div>
        </div>

        <Surface title="Task List" description="Queue state, ownership surface, and detail links.">
          {filtered.length === 0 ? (
            <EmptyState message="No tasks found." />
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Complexity</th>
                    <th>Workspace</th>
                    <th>Status</th>
                    <th>Updated</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((task) => (
                    <tr key={task.id}>
                      <td>
                        <div>{task.title}</div>
                        <div className="helper-text">{task.id}</div>
                      </td>
                      <td>{task.task_type}</td>
                      <td>{task.complexity}</td>
                      <td>{workspaces.find((workspace) => workspace.id === task.workspace_id)?.name || "none"}</td>
                      <td><StatusBadge status={task.status} /></td>
                      <td>{new Date(task.updated_at).toLocaleString()}</td>
                      <td><Link href={`/tasks/${task.id}`}>Open detail</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Surface>
      </div>
    </Layout>
  );
}
