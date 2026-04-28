import {
  AgentRun,
  AnalystDigest,
  ApiError,
  BatonPacket,
  DashboardSummary,
  DiagnosticsConfig,
  DiagnosticsOverview,
  DiagnosticsRoutes,
  HealthResponse,
  ProjectEvent,
  RoutingDecision,
  ServicesHealthResponse,
  Task,
  TaskCreatePayload,
  TaskDetail,
  TaskUpdatePayload,
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceFile,
  WorkspaceScanResult,
  WorkspaceUpdatePayload,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    const raw = await response.text();
    payload = raw || null;
  }

  if (!response.ok) {
    const error: ApiError = {
      status: response.status,
      message: `API request failed: ${response.status} ${response.statusText}`,
      detail: payload,
    };
    throw error;
  }

  return payload as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function getHealth() {
  return request<HealthResponse>("/health");
}

export function getServicesHealth() {
  return request<ServicesHealthResponse>("/health/services");
}

export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary");
}

export function listWorkspaces() {
  return request<Workspace[]>("/workspaces");
}

export function createWorkspace(payload: WorkspaceCreatePayload) {
  return request<Workspace>("/workspaces", {
    method: "POST",
    body: JSON.stringify({ runtime_mode: "native", metadata: {}, ...payload }),
  });
}

export function getWorkspace(id: string) {
  return request<Workspace>(`/workspaces/${id}`);
}

export function updateWorkspace(id: string, payload: WorkspaceUpdatePayload) {
  return request<Workspace>(`/workspaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspace(id: string) {
  return request<void>(`/workspaces/${id}`, { method: "DELETE" });
}

export function scanWorkspace(id: string) {
  return request<WorkspaceScanResult>(`/workspaces/${id}/scan`, { method: "POST" });
}

export function listWorkspaceFiles(id: string) {
  return request<WorkspaceFile>(`/workspaces/${id}/files`);
}

export function listTasks(limit = 100, workspaceId?: string) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return request<Task[]>(`/tasks?${params.toString()}`);
}

export function createTask(payload: TaskCreatePayload) {
  return request<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) });
}

export function getTask(id: string) {
  return request<TaskDetail>(`/tasks/${id}`);
}

export function updateTask(id: string, payload: TaskUpdatePayload) {
  return request<Task>(`/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listAgentRuns(taskId?: string, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (taskId) params.set("task_id", taskId);
  return request<AgentRun[]>(`/agent-runs?${params.toString()}`);
}

export function createAgentRun(payload: {
  task_id: string;
  role: string;
  status?: string;
  input_summary?: string;
}) {
  return request<AgentRun>("/agent-runs", { method: "POST", body: JSON.stringify(payload) });
}

export function getAgentRun(id: string) {
  return request<AgentRun>(`/agent-runs/${id}`);
}

export function updateAgentRun(
  id: string,
  payload: { status?: string; output_summary?: string; error_message?: string }
) {
  return request<AgentRun>(`/agent-runs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listTaskEvents(taskId: string) {
  return request<ProjectEvent[]>(`/tasks/${taskId}/events`);
}

export function listTaskBatonPackets(taskId: string) {
  return request<BatonPacket[]>(`/tasks/${taskId}/baton-packets`);
}

export function getLatestTaskBatonPacket(taskId: string) {
  return request<BatonPacket>(`/tasks/${taskId}/baton-packets/latest`);
}

export function routeNextAction(payload: {
  task_type: string;
  complexity: string;
  requires_memory?: boolean;
}) {
  return request<RoutingDecision>("/routing/next-action", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTaskRouting(taskId: string) {
  return request<RoutingDecision>(`/tasks/${taskId}/routing`);
}

export function generateDigest(payload: { task_id: string; limit?: number }) {
  return request<AnalystDigest>("/analyst/digest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTaskDigest(taskId: string) {
  return request<AnalystDigest>(`/tasks/${taskId}/digest`);
}

export function getDiagnostics() {
  return request<DiagnosticsOverview>("/diagnostics");
}

export function getDiagnosticsConfig() {
  return request<DiagnosticsConfig>("/diagnostics/config");
}

export function getDiagnosticsRoutes() {
  return request<DiagnosticsRoutes>("/diagnostics/routes");
}
