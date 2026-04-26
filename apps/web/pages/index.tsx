import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import { apiBaseUrl } from "../lib/config";

type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

type DependencyStatus = {
  name: string;
  status: "ok" | "unavailable";
  detail: string;
};

type ServicesHealthResponse = {
  status: "ok" | "degraded";
  service: string;
  environment: string;
  dependencies: DependencyStatus[];
};

type TaskItem = {
  id: string;
  title: string;
  status: string;
  task_type: string;
  complexity: string;
  created_at: string;
  updated_at: string;
};

type TaskDetail = {
  task: TaskItem;
  agent_runs: Array<{ id: string; role: string; status: string }>;
  baton_packets: Array<{ id: string; from_agent: string; to_agent?: string; summary: string }>;
  event_count: number;
  digest_path: string;
};

type ExecutiveDigest = {
  headline: string;
  summary: string;
  risk_level: string;
  total_events: number;
  event_breakdown: Record<string, number>;
  highlights: string[];
};

type RoutingDecision = {
  worker_role: string;
  model_tier: string;
  reasoning: string;
};

type MemoryLookupResponse = {
  task_id: string;
  latest_baton_packet: unknown | null;
  recent_events: unknown[];
  event_count: number;
};

type ContextBundle = {
  objective: string | null;
  next_best_action: string | null;
  open_issues: string[];
  constraints: string[];
  relevant_artifacts: string[];
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Request failed (${response.status}) for ${url}: ${body}`);
  }
  return (await response.json()) as T;
}

export default function Home() {
  const router = useRouter();
  const selectedTaskIdFromUrl =
    typeof router.query.taskId === "string" ? router.query.taskId.trim() : "";

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [servicesHealth, setServicesHealth] = useState<ServicesHealthResponse | null>(null);
  const [recentTasks, setRecentTasks] = useState<TaskItem[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState(selectedTaskIdFromUrl);
  const [selectedTaskDetail, setSelectedTaskDetail] = useState<TaskDetail | null>(null);
  const [selectedTaskDigest, setSelectedTaskDigest] = useState<ExecutiveDigest | null>(null);
  const [routingDecision, setRoutingDecision] = useState<RoutingDecision | null>(null);
  const [memoryLookup, setMemoryLookup] = useState<MemoryLookupResponse | null>(null);
  const [contextBundle, setContextBundle] = useState<ContextBundle | null>(null);
  const [consoleErrors, setConsoleErrors] = useState<string[]>([]);
  const [createTaskTitle, setCreateTaskTitle] = useState("Validate local workflow");
  const [createTaskType, setCreateTaskType] = useState("implementation");
  const [createTaskComplexity, setCreateTaskComplexity] = useState("medium");

  const selectedTask = useMemo(
    () => recentTasks.find((task) => task.id === selectedTaskId) ?? selectedTaskDetail?.task,
    [recentTasks, selectedTaskId, selectedTaskDetail]
  );

  function addError(message: string) {
    setConsoleErrors((errors) => [...errors, message]);
  }

  async function loadCoreState() {
    setConsoleErrors([]);
    try {
      const data = await fetchJson<HealthResponse>(`${apiBaseUrl}/health`);
      setHealth(data);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load /health");
    }

    try {
      const data = await fetchJson<ServicesHealthResponse>(`${apiBaseUrl}/health/services`);
      setServicesHealth(data);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load /health/services");
    }

    try {
      const data = await fetchJson<TaskItem[]>(`${apiBaseUrl}/tasks?limit=20`);
      setRecentTasks(data);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load /tasks");
    }
  }

  async function loadTask(taskId: string) {
    if (!taskId) {
      return;
    }

    try {
      const detail = await fetchJson<TaskDetail>(`${apiBaseUrl}/tasks/${taskId}`);
      setSelectedTaskDetail(detail);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load task detail");
      return;
    }

    try {
      const digest = await fetchJson<ExecutiveDigest>(`${apiBaseUrl}/analyst/digest/${taskId}`);
      setSelectedTaskDigest(digest);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load digest");
    }

    try {
      const memory = await fetchJson<MemoryLookupResponse>(`${apiBaseUrl}/memory/lookup`, {
        method: "POST",
        body: JSON.stringify({ task_id: taskId, limit: 20 }),
      });
      setMemoryLookup(memory);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load memory lookup");
    }

    try {
      const context = await fetchJson<ContextBundle>(`${apiBaseUrl}/context/${taskId}`);
      setContextBundle(context);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load context bundle");
    }
  }

  useEffect(() => {
    void loadCoreState();
  }, []);

  useEffect(() => {
    if (selectedTaskIdFromUrl) {
      setSelectedTaskId(selectedTaskIdFromUrl);
      void loadTask(selectedTaskIdFromUrl);
    }
  }, [selectedTaskIdFromUrl]);

  async function onCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      const created = await fetchJson<TaskItem>(`${apiBaseUrl}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          title: createTaskTitle,
          task_type: createTaskType,
          complexity: createTaskComplexity,
        }),
      });
      setSelectedTaskId(created.id);
      await router.push(`/?taskId=${created.id}`, undefined, { shallow: true });
      await loadCoreState();
      await loadTask(created.id);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to create task");
    }
  }

  async function onLoadTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTaskId) {
      return;
    }
    await router.push(`/?taskId=${selectedTaskId}`, undefined, { shallow: true });
    await loadTask(selectedTaskId);
  }

  async function onDecideRoute() {
    if (!selectedTask) {
      addError("Select a task before requesting routing decision");
      return;
    }

    try {
      const decision = await fetchJson<RoutingDecision>(`${apiBaseUrl}/routing/decide`, {
        method: "POST",
        body: JSON.stringify({
          task_type: selectedTask.task_type,
          complexity: selectedTask.complexity,
          requires_memory: true,
        }),
      });
      setRoutingDecision(decision);
    } catch (error) {
      addError(error instanceof Error ? error.message : "Failed to load routing decision");
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif", maxWidth: 1080, margin: "0 auto" }}>
      <h1>Syncore Local Prototype Console</h1>
      <p>
        Create tasks, inspect routing output, review baton history, and verify context + digest generation
        for the local MVP workflow.
      </p>
      <p>API Base URL: {apiBaseUrl}</p>

      <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <h2>System Health</h2>
        <p>Orchestrator: {health ? `${health.status} (${health.environment})` : "unavailable"}</p>
        <p>Dependencies: {servicesHealth ? servicesHealth.status : "unavailable"}</p>
        {servicesHealth && (
          <ul>
            {servicesHealth.dependencies.map((dependency) => (
              <li key={dependency.name}>
                {dependency.name}: {dependency.status}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <h2>Create Task</h2>
        <form onSubmit={onCreateTask}>
          <label htmlFor="taskTitle">Title:</label>{" "}
          <input
            id="taskTitle"
            value={createTaskTitle}
            onChange={(event) => setCreateTaskTitle(event.target.value)}
            style={{ width: 320 }}
          />{" "}
          <label htmlFor="taskType">Type:</label>{" "}
          <select
            id="taskType"
            value={createTaskType}
            onChange={(event) => setCreateTaskType(event.target.value)}
          >
            <option value="analysis">analysis</option>
            <option value="implementation">implementation</option>
            <option value="integration">integration</option>
            <option value="review">review</option>
            <option value="memory_retrieval">memory_retrieval</option>
            <option value="memory_update">memory_update</option>
          </select>{" "}
          <label htmlFor="taskComplexity">Complexity:</label>{" "}
          <select
            id="taskComplexity"
            value={createTaskComplexity}
            onChange={(event) => setCreateTaskComplexity(event.target.value)}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>{" "}
          <button type="submit">Create Task</button>
        </form>
      </section>

      <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <h2>Task Explorer</h2>
        <form onSubmit={onLoadTask}>
          <label htmlFor="taskId">Task ID:</label>{" "}
          <input
            id="taskId"
            value={selectedTaskId}
            onChange={(event) => setSelectedTaskId(event.target.value)}
            placeholder="Paste a task UUID"
            style={{ width: 360 }}
          />{" "}
          <button type="submit">Load Task</button>
          <button type="button" onClick={onDecideRoute} style={{ marginLeft: 8 }}>
            Decide Route
          </button>
        </form>
        <p style={{ marginTop: 8 }}>
          Tip: run <code>make demo-local</code> to generate a full sample flow quickly.
        </p>

        <h3>Recent Tasks</h3>
        {recentTasks.length === 0 ? (
          <p>No tasks found yet.</p>
        ) : (
          <ul>
            {recentTasks.map((task) => (
              <li key={task.id}>
                <a href={`/?taskId=${task.id}`}>{task.title}</a> — {task.status} ({task.task_type})
              </li>
            ))}
          </ul>
        )}
      </section>

      {routingDecision && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h2>Routing Decision</h2>
          <pre>{JSON.stringify(routingDecision, null, 2)}</pre>
        </section>
      )}

      {selectedTaskDetail && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h2>Selected Task Detail</h2>
          <pre>{JSON.stringify(selectedTaskDetail, null, 2)}</pre>
        </section>
      )}

      {memoryLookup && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h2>Memory Lookup</h2>
          <pre>{JSON.stringify(memoryLookup, null, 2)}</pre>
        </section>
      )}

      {contextBundle && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h2>Context Bundle</h2>
          <pre>{JSON.stringify(contextBundle, null, 2)}</pre>
        </section>
      )}

      {selectedTaskDigest && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h2>Analyst Digest</h2>
          <pre>{JSON.stringify(selectedTaskDigest, null, 2)}</pre>
        </section>
      )}

      {consoleErrors.length > 0 && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #fbb", borderRadius: 8 }}>
          <h2>Load Errors</h2>
          <ul>
            {consoleErrors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
