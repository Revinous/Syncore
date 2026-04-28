import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { createTask, listTasks, listWorkspaces } from "../../src/lib/api";
import { Task, Workspace } from "../../src/lib/types";
import { EmptyState } from "../../src/components/EmptyState";
import { ErrorState } from "../../src/components/ErrorState";
import { Layout } from "../../src/components/Layout";
import { LoadingState } from "../../src/components/LoadingState";
import { StatusBadge } from "../../src/components/StatusBadge";

export default function TasksPage() {
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
      {loading && <LoadingState message="Loading tasks..." />}
      {error && <ErrorState message={error} />}

      <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
        <h2>Create Task</h2>
        <form onSubmit={onCreateTask} style={{ display: "grid", gap: 8, maxWidth: 640 }}>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Task title" required />
          <select value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
            <option value="">No workspace</option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
          <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            <option value="analysis">analysis</option>
            <option value="implementation">implementation</option>
            <option value="integration">integration</option>
            <option value="review">review</option>
            <option value="memory_retrieval">memory_retrieval</option>
            <option value="memory_update">memory_update</option>
          </select>
          <select value={complexity} onChange={(event) => setComplexity(event.target.value)}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
          <button type="submit">Create Task</button>
        </form>
      </section>

      <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
        <h2>Task List</h2>
        <label>
          Status filter:{" "}
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">all</option>
            <option value="new">new</option>
            <option value="in_progress">in_progress</option>
            <option value="blocked">blocked</option>
            <option value="completed">completed</option>
          </select>
        </label>
        {"  "}
        <label>
          Workspace filter:{" "}
          <select
            value={workspaceFilter}
            onChange={(event) => setWorkspaceFilter(event.target.value)}
          >
            <option value="all">all</option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </label>

        {filtered.length === 0 ? (
          <EmptyState message="No tasks found." />
        ) : (
          <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">Title</th>
                <th align="left">Type</th>
                <th align="left">Complexity</th>
                <th align="left">Workspace</th>
                <th align="left">Status</th>
                <th align="left">Updated</th>
                <th align="left">Open</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => (
                <tr key={task.id}>
                  <td>{task.title}</td>
                  <td>{task.task_type}</td>
                  <td>{task.complexity}</td>
                  <td>
                    {workspaces.find((workspace) => workspace.id === task.workspace_id)?.name ||
                      "none"}
                  </td>
                  <td><StatusBadge status={task.status} /></td>
                  <td>{new Date(task.updated_at).toLocaleString()}</td>
                  <td>
                    <Link href={`/tasks/${task.id}`}>Details</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </Layout>
  );
}
