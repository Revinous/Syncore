export type ApiError = {
  status: number;
  message: string;
  detail?: unknown;
};

export type ServiceStatus = {
  name: string;
  status: "ok" | "unavailable";
  detail: string;
};

export type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

export type ServicesHealthResponse = {
  status: "ok" | "degraded";
  service: string;
  environment: string;
  dependencies: ServiceStatus[];
};

export type DashboardSummary = {
  runtime_mode: string;
  db_backend: string;
  health: string;
  services: Record<string, string>;
  workspace_count: number;
  open_task_count: number;
  active_run_count: number;
  recent_events: ProjectEvent[];
  recent_batons: BatonPacket[];
  latest_digest: AnalystDigest | null;
};

export type Workspace = {
  id: string;
  name: string;
  root_path: string;
  repo_url: string | null;
  branch: string | null;
  runtime_mode: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkspaceScanMetadata = {
  languages: string[];
  frameworks: string[];
  package_managers: string[];
  test_commands: string[];
  entrypoints: string[];
  docs: string[];
  important_files: string[];
};

export type WorkspaceScanResult = {
  workspace: Workspace;
  scan: WorkspaceScanMetadata;
};

export type WorkspaceFile = {
  workspace_id: string;
  root_path: string;
  files: string[];
  count: number;
};

export type Task = {
  id: string;
  title: string;
  status: string;
  task_type: string;
  complexity: string;
  workspace_id: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: string;
  task_id: string;
  role: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectEvent = {
  id: string;
  task_id: string;
  event_type: string;
  event_data: Record<string, string | number | boolean | null>;
  created_at: string;
};

export type BatonPayload = {
  objective: string;
  completed_work: string[];
  constraints: string[];
  open_questions: string[];
  next_best_action: string;
  relevant_artifacts: string[];
};

export type BatonPacket = {
  id: string;
  task_id: string;
  from_agent: string;
  to_agent: string | null;
  summary: string;
  payload: BatonPayload;
  created_at: string;
};

export type RoutingDecision = {
  worker_role: string;
  model_tier: string;
  reasoning: string;
};

export type AnalystDigest = {
  task_id: string;
  generated_at: string;
  headline: string;
  summary: string;
  highlights: string[];
  event_breakdown: Record<string, number>;
  risk_level: string;
  total_events: number;
};

export type DiagnosticsConfig = {
  environment: string;
  runtime_mode: string;
  db_backend: string;
  redis_required: boolean;
  redis_url: string;
  postgres_dsn: string;
  sqlite_db_path: string;
};

export type DiagnosticsOverview = {
  service: string;
  environment: string;
  runtime_mode: string;
  db_backend: string;
  redis_required: boolean;
};

export type DiagnosticsRoutes = {
  routes: string[];
};

export type TaskDetail = {
  task: Task;
  agent_runs: AgentRun[];
  baton_packets: BatonPacket[];
  event_count: number;
  digest_path: string;
};

export type WorkspaceCreatePayload = {
  name: string;
  root_path: string;
  repo_url?: string | null;
  branch?: string | null;
  runtime_mode?: string;
  metadata?: Record<string, unknown>;
};

export type WorkspaceUpdatePayload = Partial<WorkspaceCreatePayload>;

export type TaskCreatePayload = {
  title: string;
  task_type: string;
  complexity?: string;
  workspace_id?: string | null;
};

export type TaskUpdatePayload = {
  title?: string;
  status?: string;
  task_type?: string;
  complexity?: string;
};
