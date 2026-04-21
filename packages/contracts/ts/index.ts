export type TaskStatus = "new" | "in_progress" | "blocked" | "completed";

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  createdAt: string;
  updatedAt: string;
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

export interface ProjectEvent {
  id: string;
  taskId: string;
  eventType: string;
  eventData: Record<string, unknown>;
  createdAt: string;
}
