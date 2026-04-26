export type TaskStatus = "new" | "in_progress" | "blocked" | "completed";
export type TaskType =
  | "analysis"
  | "implementation"
  | "integration"
  | "review"
  | "memory_retrieval"
  | "memory_update";
export type ComplexityLevel = "low" | "medium" | "high";
export type WorkerRole = "analyst" | "orchestrator" | "memory";
export type ModelTier = "economy" | "balanced" | "premium";
export type RiskLevel = "low" | "medium" | "high";
export type AgentRole = "planner" | "coder" | "reviewer" | "analyst" | "memory";
export type AgentRunStatus = "queued" | "running" | "blocked" | "completed" | "failed";
export type RunStreamEventType = "started" | "chunk" | "completed" | "error";

export interface TaskCreate {
  title: string;
  task_type: TaskType;
  complexity: ComplexityLevel;
}

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  task_type: TaskType;
  complexity: ComplexityLevel;
  created_at: string;
  updated_at: string;
}

export interface BatonPayload {
  objective: string;
  completed_work: string[];
  constraints: string[];
  open_questions: string[];
  next_best_action: string;
  relevant_artifacts: string[];
}

export interface BatonPacketCreate {
  task_id: string;
  from_agent: string;
  to_agent?: string;
  summary: string;
  payload: BatonPayload;
}

export interface BatonPacket {
  id: string;
  task_id: string;
  from_agent: string;
  to_agent?: string;
  summary: string;
  payload: BatonPayload;
  created_at: string;
}

export interface ProjectEventCreate {
  task_id: string;
  event_type: string;
  event_data?: Record<string, string | number | boolean | null>;
}

export interface ProjectEvent {
  id: string;
  task_id: string;
  event_type: string;
  event_data: Record<string, string | number | boolean | null>;
  created_at: string;
}

export interface AgentRunCreate {
  task_id: string;
  role: AgentRole;
  status?: AgentRunStatus;
  input_summary?: string;
}

export interface AgentRunUpdate {
  status?: AgentRunStatus;
  output_summary?: string;
  error_message?: string;
}

export interface AgentRun {
  id: string;
  task_id: string;
  role: AgentRole;
  status: AgentRunStatus;
  input_summary?: string;
  output_summary?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskDetail {
  task: Task;
  agent_runs: AgentRun[];
  baton_packets: BatonPacket[];
  event_count: number;
  digest_path: string;
}

export interface MemoryLookupRequest {
  task_id: string;
  limit?: number;
}

export interface MemoryLookupResponse {
  task_id: string;
  latest_baton_packet: BatonPacket | null;
  recent_events: ProjectEvent[];
  event_count: number;
}

export interface ContextAssembleRequest {
  task_id: string;
  event_limit?: number;
}

export interface ContextBundle {
  task: Task;
  latest_baton_packet: BatonPacket | null;
  recent_events: ProjectEvent[];
  objective?: string;
  completed_work: string[];
  constraints: string[];
  open_issues: string[];
  next_best_action?: string;
  relevant_artifacts: string[];
}

export interface RoutingRequest {
  task_type: TaskType;
  complexity: ComplexityLevel;
  requires_memory?: boolean;
}

export interface RoutingDecision {
  worker_role: WorkerRole;
  model_tier: ModelTier;
  reasoning: string;
}

export interface ExecutiveDigest {
  task_id: string;
  generated_at: string;
  headline: string;
  summary: string;
  highlights: string[];
  event_breakdown: Record<string, number>;
  risk_level: RiskLevel;
  total_events: number;
}

export interface RunExecutionRequest {
  task_id: string;
  prompt: string;
  target_agent: string;
  target_model: string;
  token_budget?: number;
  provider?: string;
  agent_role?: AgentRole;
  system_prompt?: string;
  max_output_tokens?: number;
  temperature?: number;
}

export interface RunExecutionResponse {
  run_id: string;
  task_id: string;
  status: AgentRunStatus;
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
}

export interface RunStreamEvent {
  event: RunStreamEventType;
  run_id?: string;
  task_id?: string;
  provider?: string;
  target_model?: string;
  content?: string;
  estimated_output_tokens?: number;
  error?: string;
}
