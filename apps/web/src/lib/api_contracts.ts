import type {
  ApiError,
  ContextReference,
  DashboardSummary,
  DiagnosticsOverview,
  HealthResponse,
  ProjectEvent,
  ServicesHealthResponse,
  Task,
  TaskDetail,
  TaskExecutionArtifact,
  TaskExecutionCommand,
  TaskExecutionReport,
  TaskExecutionRunOutput
} from "./types";

type JsonObject = Record<string, unknown>;
type Parser<T> = (value: unknown) => T;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function expectObject(value: unknown, label: string): JsonObject {
  if (!isObject(value)) throw contractError(`${label} must be an object`, value);
  return value;
}

function expectString(value: unknown, label: string): string {
  if (typeof value !== "string") throw contractError(`${label} must be a string`, value);
  return value;
}

function expectBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw contractError(`${label} must be a boolean`, value);
  return value;
}

function expectNullableString(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  return expectString(value, label);
}

function expectStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw contractError(`${label} must be an array`, value);
  return value.map((item, index) => expectString(item, `${label}[${index}]`));
}

function expectProjectEvents(value: unknown, label: string): ProjectEvent[] {
  if (!Array.isArray(value)) throw contractError(`${label} must be an array`, value);
  return value.map((item, index) => {
    const obj = expectObject(item, `${label}[${index}]`);
    return {
      id: expectString(obj.id, `${label}[${index}].id`),
      task_id: expectString(obj.task_id, `${label}[${index}].task_id`),
      event_type: expectString(obj.event_type, `${label}[${index}].event_type`),
      event_data: isObject(obj.event_data) ? (obj.event_data as Record<string, string | number | boolean | null>) : {},
      created_at: expectString(obj.created_at, `${label}[${index}].created_at`)
    };
  });
}

function expectTask(value: unknown, label: string): Task {
  const obj = expectObject(value, label);
  return {
    id: expectString(obj.id, `${label}.id`),
    title: expectString(obj.title, `${label}.title`),
    status: expectString(obj.status, `${label}.status`),
    task_type: expectString(obj.task_type, `${label}.task_type`),
    complexity: expectString(obj.complexity, `${label}.complexity`),
    workspace_id: expectNullableString(obj.workspace_id, `${label}.workspace_id`),
    created_at: expectString(obj.created_at, `${label}.created_at`),
    updated_at: expectString(obj.updated_at, `${label}.updated_at`)
  };
}

function expectTaskExecutionCommand(value: unknown, label: string): TaskExecutionCommand {
  const obj = expectObject(value, label);
  return {
    command: expectString(obj.command, `${label}.command`),
    status: expectString(obj.status, `${label}.status`),
    output_preview: expectNullableString(obj.output_preview, `${label}.output_preview`)
  };
}

function expectTaskExecutionArtifact(value: unknown, label: string): TaskExecutionArtifact {
  const obj = expectObject(value, label);
  return {
    ref_id: expectString(obj.ref_id, `${label}.ref_id`),
    path: expectString(obj.path, `${label}.path`),
    content_type: expectString(obj.content_type, `${label}.content_type`),
    summary: expectString(obj.summary, `${label}.summary`),
    retrieval_hint: expectString(obj.retrieval_hint, `${label}.retrieval_hint`),
    preview: expectString(obj.preview, `${label}.preview`),
    created_at: expectString(obj.created_at, `${label}.created_at`)
  };
}

function expectTaskExecutionRunOutput(value: unknown, label: string): TaskExecutionRunOutput {
  const obj = expectObject(value, label);
  return {
    run_id: expectString(obj.run_id, `${label}.run_id`),
    role: expectString(obj.role, `${label}.role`),
    status: expectString(obj.status, `${label}.status`),
    provider: expectNullableString(obj.provider, `${label}.provider`),
    target_model: expectNullableString(obj.target_model, `${label}.target_model`),
    output_ref_id: expectNullableString(obj.output_ref_id, `${label}.output_ref_id`),
    output_preview: expectNullableString(obj.output_preview, `${label}.output_preview`),
    error_message: expectNullableString(obj.error_message, `${label}.error_message`),
    updated_at: expectString(obj.updated_at, `${label}.updated_at`)
  };
}

function contractError(message: string, detail: unknown): ApiError {
  return { status: -1, message: `API contract error: ${message}`, detail };
}

export const parseHealthResponse: Parser<HealthResponse> = (value) => {
  const obj = expectObject(value, "HealthResponse");
  return {
    status: expectString(obj.status, "HealthResponse.status"),
    service: expectString(obj.service, "HealthResponse.service"),
    environment: expectString(obj.environment, "HealthResponse.environment")
  };
};

export const parseServicesHealthResponse: Parser<ServicesHealthResponse> = (value) => {
  const obj = expectObject(value, "ServicesHealthResponse");
  const deps = Array.isArray(obj.dependencies) ? obj.dependencies : [];
  return {
    status: expectString(obj.status, "ServicesHealthResponse.status") as "ok" | "degraded",
    service: expectString(obj.service, "ServicesHealthResponse.service"),
    environment: expectString(obj.environment, "ServicesHealthResponse.environment"),
    dependencies: deps.map((item, index) => {
      const dep = expectObject(item, `ServicesHealthResponse.dependencies[${index}]`);
      return {
        name: expectString(dep.name, `ServicesHealthResponse.dependencies[${index}].name`),
        status: expectString(dep.status, `ServicesHealthResponse.dependencies[${index}].status`) as "ok" | "unavailable",
        detail: expectString(dep.detail, `ServicesHealthResponse.dependencies[${index}].detail`)
      };
    })
  };
};

export const parseDashboardSummary: Parser<DashboardSummary> = (value) => {
  const obj = expectObject(value, "DashboardSummary");
  return {
    runtime_mode: expectString(obj.runtime_mode, "DashboardSummary.runtime_mode"),
    db_backend: expectString(obj.db_backend, "DashboardSummary.db_backend"),
    health: expectString(obj.health, "DashboardSummary.health"),
    services: isObject(obj.services) ? (obj.services as Record<string, string>) : {},
    workspace_count: Number(obj.workspace_count ?? 0),
    open_task_count: Number(obj.open_task_count ?? 0),
    active_run_count: Number(obj.active_run_count ?? 0),
    recent_events: expectProjectEvents(obj.recent_events ?? [], "DashboardSummary.recent_events"),
    recent_batons: Array.isArray(obj.recent_batons) ? (obj.recent_batons as DashboardSummary["recent_batons"]) : [],
    latest_digest: (isObject(obj.latest_digest) ? (obj.latest_digest as DashboardSummary["latest_digest"]) : null)
  };
};

export const parseTaskDetail: Parser<TaskDetail> = (value) => {
  const obj = expectObject(value, "TaskDetail");
  return {
    task: expectTask(obj.task, "TaskDetail.task"),
    agent_runs: Array.isArray(obj.agent_runs) ? (obj.agent_runs as TaskDetail["agent_runs"]) : [],
    baton_packets: Array.isArray(obj.baton_packets) ? (obj.baton_packets as TaskDetail["baton_packets"]) : [],
    event_count: Number(obj.event_count ?? 0),
    digest_path: expectString(obj.digest_path ?? "", "TaskDetail.digest_path")
  };
};

export const parseTaskExecutionReport: Parser<TaskExecutionReport> = (value) => {
  const obj = expectObject(value, "TaskExecutionReport");
  return {
    task_id: expectString(obj.task_id, "TaskExecutionReport.task_id"),
    outcome_status: expectString(obj.outcome_status, "TaskExecutionReport.outcome_status"),
    summary_reason: expectString(obj.summary_reason ?? "", "TaskExecutionReport.summary_reason"),
    meaningful_change: expectBoolean(obj.meaningful_change, "TaskExecutionReport.meaningful_change"),
    changed_files: expectStringArray(obj.changed_files ?? [], "TaskExecutionReport.changed_files"),
    planned_actions: expectStringArray(obj.planned_actions ?? [], "TaskExecutionReport.planned_actions"),
    verification_status: expectNullableString(obj.verification_status, "TaskExecutionReport.verification_status"),
    verification_reason: expectNullableString(obj.verification_reason, "TaskExecutionReport.verification_reason"),
    verification_commands: Array.isArray(obj.verification_commands)
      ? obj.verification_commands.map((item, index) =>
          expectTaskExecutionCommand(item, `TaskExecutionReport.verification_commands[${index}]`)
        )
      : [],
    diff_artifacts: Array.isArray(obj.diff_artifacts)
      ? obj.diff_artifacts.map((item, index) =>
          expectTaskExecutionArtifact(item, `TaskExecutionReport.diff_artifacts[${index}]`)
        )
      : [],
    output_artifacts: Array.isArray(obj.output_artifacts)
      ? obj.output_artifacts.map((item, index) =>
          expectTaskExecutionRunOutput(item, `TaskExecutionReport.output_artifacts[${index}]`)
        )
      : [],
    report_ref_id: expectNullableString(obj.report_ref_id, "TaskExecutionReport.report_ref_id"),
    last_event_type: expectNullableString(obj.last_event_type, "TaskExecutionReport.last_event_type"),
    last_updated_at: expectNullableString(obj.last_updated_at, "TaskExecutionReport.last_updated_at")
  };
};

export const parseDiagnosticsOverview: Parser<DiagnosticsOverview> = (value) => {
  const obj = expectObject(value, "DiagnosticsOverview");
  return {
    service: expectString(obj.service, "DiagnosticsOverview.service"),
    environment: expectString(obj.environment, "DiagnosticsOverview.environment"),
    runtime_mode: expectString(obj.runtime_mode, "DiagnosticsOverview.runtime_mode"),
    db_backend: expectString(obj.db_backend, "DiagnosticsOverview.db_backend"),
    redis_required: expectBoolean(obj.redis_required, "DiagnosticsOverview.redis_required")
  };
};

export const parseContextReference: Parser<ContextReference> = (value) => {
  const obj = expectObject(value, "ContextReference");
  return {
    ref_id: expectString(obj.ref_id, "ContextReference.ref_id"),
    task_id: expectString(obj.task_id, "ContextReference.task_id"),
    content_type: expectString(obj.content_type, "ContextReference.content_type"),
    original_content: expectString(obj.original_content, "ContextReference.original_content"),
    summary: expectString(obj.summary, "ContextReference.summary"),
    retrieval_hint: expectString(obj.retrieval_hint, "ContextReference.retrieval_hint"),
    created_at: expectString(obj.created_at, "ContextReference.created_at")
  };
};
