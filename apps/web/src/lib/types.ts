export type ApiError = {
  status: number;
  message: string;
  detail?: unknown;
};

export type ContextReference = {
  ref_id: string;
  task_id: string;
  content_type: string;
  original_content: string;
  summary: string;
  retrieval_hint: string;
  created_at: string;
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

export type ContextEfficiencyModelBreakdown = {
  bundle_count: number;
  raw_tokens: number;
  optimized_tokens: number;
  saved_tokens: number;
};

export type ContextEfficiencyMetrics = {
  bundle_count: number;
  totals: {
    raw_tokens: number;
    optimized_tokens: number;
    saved_tokens: number;
    savings_pct: number;
  };
  cost_totals?: {
    raw_usd: number;
    optimized_usd: number;
    saved_usd: number;
  };
  by_model: Record<string, ContextEfficiencyModelBreakdown>;
  layering_modes?: Record<string, number>;
  layering_profiles?: Record<
    string,
    {
      bundle_count: number;
      layering_modes: Record<string, number>;
      legacy_tokens: number;
      layered_tokens: number;
      comparison_count: number;
    }
  >;
  layering_comparison?: {
    bundle_count: number;
    legacy_tokens: number;
    layered_tokens: number;
    saved_tokens: number;
    savings_pct: number;
  };
  recent_bundles: Array<{
    bundle_id: string;
    task_id: string;
    target_model: string;
    raw_estimated_tokens: number;
    optimized_estimated_tokens: number;
    token_savings_estimate: number;
    token_savings_pct: number;
    estimated_cost_saved_usd?: number | null;
    created_at: string;
  }>;
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

export type ProviderCapability = {
  provider: string;
  supports_streaming: boolean;
  supports_system_prompt: boolean;
  supports_temperature: boolean;
  supports_max_tokens: boolean;
  model_hint: string;
  max_context_tokens: number;
  quality_tier: number;
  speed_tier: number;
  cost_tier: number;
  strengths: string[];
};

export type TaskModelPolicyStage = {
  provider: string | null;
  model: string | null;
};

export type TaskModelPolicy = {
  default_provider: string;
  default_model: string;
  plan: TaskModelPolicyStage;
  execute: TaskModelPolicyStage;
  review: TaskModelPolicyStage;
  fallback_order: string[];
  prefer_reviewer_provider: boolean;
  optimization_goal: string;
  allow_cross_provider_switching: boolean;
  maintain_context_continuity: boolean;
  minimum_context_window: number;
  max_latency_tier: string | null;
  max_cost_tier: string | null;
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
  eli5_summary: string;
};

export type NotificationItem = {
  id: string;
  category: string;
  title: string;
  body: string;
  related_task_id: string | null;
  related_workspace_id: string | null;
  finding_id: string | null;
  acknowledged: boolean;
  acknowledged_at: string | null;
  created_at: string;
};

export type NotificationListResponse = {
  items: NotificationItem[];
};

export type DiagnosticsConfig = {
  environment: string;
  runtime_mode: string;
  db_backend: string;
  redis_required: boolean;
  redis_url: string;
  postgres_dsn: string;
  sqlite_db_path: string;
  codex_sidecar: DiagnosticsProviderStatus;
  codex_oauth_experimental: DiagnosticsProviderStatus;
};

export type DiagnosticsOverview = {
  service: string;
  environment: string;
  runtime_mode: string;
  db_backend: string;
  redis_required: boolean;
  codex_sidecar: DiagnosticsProviderStatus;
  codex_oauth_experimental: DiagnosticsProviderStatus;
};

export type DiagnosticsProviderStatus = {
  provider: string | null;
  mode: string | null;
  warning: string | null;
  recommended_action: string | null;
  provider_registered: boolean;
  executable: boolean;
  detail: string | null;
  required_settings: string[];
  enabled: boolean | null;
  configured: boolean | null;
  api_key_configured: boolean | null;
  base_url: string | null;
  reachable: boolean | null;
  implementation_state: string | null;
  authenticated: boolean | null;
  can_refresh: boolean | null;
  storage_secure: boolean | null;
  token_path: string | null;
  expires_at: string | null;
};

export type DiagnosticsRoutes = {
  routes: string[];
};

export type OpenAIAuthStatus = {
  configured: boolean;
  storage_secure: boolean;
  token_path: string;
  detail: string;
  models: string[];
};

export type CodexAuthStatus = {
  provider: string;
  mode: string;
  implementation_state: string;
  authenticated: boolean;
  can_refresh: boolean;
  storage_secure: boolean;
  token_path: string;
  expires_at: string | null;
  detail: string;
  metadata: Record<string, string | number | boolean | null>;
};

export type CodexBrowserLoginStartResponse = {
  auth_url: string;
  pending: boolean;
  detail: string;
};

export type BenchmarkCaseResult = {
  name: string;
  repo_url: string;
  root_path: string;
  baseline_test_command: string;
  baseline_test_passed: boolean;
  workspace_id: string | null;
  languages: string[];
  frameworks: string[];
  package_managers: string[];
  test_commands: string[];
  readiness_pack: string | null;
  readiness_runner: string | null;
  live_execution_attempted: boolean;
  live_execution_passed: boolean;
  task_id: string | null;
  execution_outcome: string | null;
  verification_status: string | null;
  meaningful_change: boolean | null;
  notes: string[];
};

export type BenchmarkReport = {
  available: boolean;
  generated_at: string | null;
  api_url: string | null;
  execute_enabled: boolean;
  provider: string | null;
  model: string | null;
  case_count: number;
  baseline_pass_count: number;
  live_pass_count: number;
  meaningful_change_count: number;
  cases: BenchmarkCaseResult[];
  raw?: Record<string, unknown> | null;
};

export type TaskDetail = {
  task: Task;
  agent_runs: AgentRun[];
  baton_packets: BatonPacket[];
  event_count: number;
  digest_path: string;
};

export type TaskChildStatusItem = {
  task_id: string;
  title: string;
  status: string;
  task_type: string;
  complexity: string;
  updated_at: string;
};

export type TaskChildrenBoard = {
  parent_task_id: string;
  has_children: boolean;
  total_children: number;
  completed_children: number;
  blocked_children: number;
  active_children: number;
  children: TaskChildStatusItem[];
};

export type TaskExecutionCommand = {
  command: string;
  status: string;
  output_preview: string | null;
};

export type TaskExecutionArtifact = {
  ref_id: string;
  path: string;
  content_type: string;
  summary: string;
  retrieval_hint: string;
  preview: string;
  created_at: string;
};

export type TaskExecutionRunOutput = {
  run_id: string;
  role: string;
  status: string;
  provider: string | null;
  target_model: string | null;
  output_ref_id: string | null;
  output_preview: string | null;
  error_message: string | null;
  updated_at: string;
};

export type TaskExecutionReport = {
  task_id: string;
  outcome_status: string;
  summary_reason: string;
  meaningful_change: boolean;
  changed_files: string[];
  planned_actions: string[];
  verification_status: string | null;
  verification_reason: string | null;
  verification_commands: TaskExecutionCommand[];
  diff_artifacts: TaskExecutionArtifact[];
  output_artifacts: TaskExecutionRunOutput[];
  report_ref_id: string | null;
  last_event_type: string | null;
  last_updated_at: string | null;
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
