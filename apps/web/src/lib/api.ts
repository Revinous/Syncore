import {
  AgentRun,
  AnalystDigest,
  ApiError,
  BatonPacket,
  BenchmarkReport,
  ContextReference,
  DashboardSummary,
  ContextEfficiencyMetrics,
  DiagnosticsConfig,
  DiagnosticsOverview,
  DiagnosticsRoutes,
  HealthResponse,
  ProjectEvent,
  RoutingDecision,
  NotificationItem,
  NotificationListResponse,
  ProviderCapability,
  ServicesHealthResponse,
  Task,
  TaskChildrenBoard,
  TaskCreatePayload,
  TaskDetail,
  TaskExecutionReport,
  TaskModelPolicy,
  TaskUpdatePayload,
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceFile,
  WorkspaceScanResult,
  WorkspaceUpdatePayload,
} from "./types";
import {
  parseContextReference,
  parseDashboardSummary,
  parseDiagnosticsOverview,
  parseHealthResponse,
  parseServicesHealthResponse,
  parseTaskDetail,
  parseTaskExecutionReport
} from "./api_contracts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

type Parser<T> = (value: unknown) => T;

async function request<T>(path: string, init?: RequestInit, parse?: Parser<T>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    const networkError: ApiError = {
      status: 0,
      message: `Could not reach Syncore API at ${API_BASE_URL}`,
      detail: error instanceof Error ? error.message : error,
    };
    throw networkError;
  }

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

  return parse ? parse(payload) : (payload as T);
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function getHealth() {
  return request<HealthResponse>("/health", undefined, parseHealthResponse);
}

export function getServicesHealth() {
  return request<ServicesHealthResponse>("/health/services", undefined, parseServicesHealthResponse);
}

export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary", undefined, parseDashboardSummary);
}

export function getContextEfficiencyMetrics(limit = 200) {
  return request<ContextEfficiencyMetrics>(
    `/metrics/context-efficiency?limit=${encodeURIComponent(String(limit))}`
  );
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
  return request<TaskDetail>(`/tasks/${id}`, undefined, parseTaskDetail);
}

export function getTaskChildren(id: string) {
  return request<TaskChildrenBoard>(`/tasks/${id}/children`);
}

export function getTaskExecutionReport(id: string) {
  return request<TaskExecutionReport>(`/tasks/${id}/execution-report`, undefined, parseTaskExecutionReport);
}

export function getContextReference(refId: string) {
  return request<ContextReference>(`/context/references/${encodeURIComponent(refId)}`, undefined, parseContextReference);
}

export function getTaskModelPolicy(id: string) {
  return request<TaskModelPolicy>(`/tasks/${id}/model-policy`);
}

export function updateTaskModelPolicy(
  id: string,
  payload: Partial<TaskModelPolicy> & Record<string, unknown>
) {
  return request<TaskModelPolicy>(`/tasks/${id}/model-policy`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
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

export function executeTaskAuto(payload: {
  task_id: string;
  stage?: string;
  prompt: string;
  target_agent: string;
  token_budget?: number;
  provider?: string;
  target_model?: string;
  agent_role?: string;
  system_prompt?: string;
  max_output_tokens?: number;
  temperature?: number;
  timeout_seconds?: number;
}) {
  return request<{
    run_id: string;
    task_id: string;
    status: string;
    provider: string;
    target_agent: string;
    target_model: string;
    output_text: string;
    estimated_input_tokens: number;
    estimated_output_tokens: number;
    total_estimated_tokens: number;
    optimized_bundle_id?: string;
    included_refs: string[];
    warnings: string[];
    created_at: string;
    completed_at: string;
  }>("/runs/execute-auto", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  return request<DiagnosticsOverview>("/diagnostics", undefined, parseDiagnosticsOverview);
}

export function getDiagnosticsConfig() {
  return request<DiagnosticsConfig>("/diagnostics/config");
}

export function getDiagnosticsRoutes() {
  return request<DiagnosticsRoutes>("/diagnostics/routes");
}

export function getLatestBenchmarkReport() {
  return request<BenchmarkReport>("/benchmarks/latest");
}

export function listProviderCapabilities() {
  return request<ProviderCapability[]>("/runs/providers");
}

export function listNotifications(acknowledged?: boolean, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (acknowledged !== undefined) {
    params.set("acknowledged", acknowledged ? "true" : "false");
  }
  return request<NotificationListResponse>(`/notifications?${params.toString()}`);
}

export function getNotification(id: string) {
  return request<NotificationItem>(`/notifications/${id}`);
}

export function acknowledgeNotification(id: string) {
  return request<{ notification: NotificationItem }>(`/notifications/${id}/ack`, {
    method: "POST",
  });
}
