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

export interface TaskCreate {
  title: string;
  taskType: TaskType;
  complexity: ComplexityLevel;
}

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  taskType: TaskType;
  complexity: ComplexityLevel;
  createdAt: string;
  updatedAt: string;
}

export interface BatonPacketCreate {
  taskId: string;
  fromAgent: string;
  toAgent?: string;
  summary: string;
  payload?: Record<string, unknown>;
}

export interface BatonPacket {
  id: string;
  taskId: string;
  fromAgent: string;
  toAgent?: string;
  summary: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface ProjectEventCreate {
  taskId: string;
  eventType: string;
  eventData?: Record<string, unknown>;
}

export interface ProjectEvent {
  id: string;
  taskId: string;
  eventType: string;
  eventData: Record<string, unknown>;
  createdAt: string;
}

export interface MemoryLookupRequest {
  taskId: string;
  limit?: number;
}

export interface RoutingRequest {
  taskType: TaskType;
  complexity: ComplexityLevel;
  requiresMemory?: boolean;
}

export interface RoutingDecision {
  workerRole: WorkerRole;
  modelTier: ModelTier;
  reasoning: string;
}
