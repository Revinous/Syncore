PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  task_type TEXT NOT NULL DEFAULT 'analysis',
  complexity TEXT NOT NULL DEFAULT 'medium',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  input_summary TEXT,
  output_summary TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baton_packets (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  from_agent TEXT NOT NULL,
  to_agent TEXT,
  summary TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_events (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_references (
  ref_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  content_type TEXT NOT NULL,
  original_content TEXT NOT NULL,
  summary TEXT NOT NULL,
  retrieval_hint TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_bundles (
  bundle_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  target_agent TEXT NOT NULL,
  target_model TEXT NOT NULL,
  token_budget INTEGER NOT NULL,
  optimized_context TEXT NOT NULL,
  included_refs TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id_created_at
  ON agent_runs (task_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_baton_packets_task_id_created_at
  ON baton_packets (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_events_task_id_created_at
  ON project_events (task_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_context_references_task_id_created_at
  ON context_references (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_context_bundles_task_id_created_at
  ON context_bundles (task_id, created_at DESC);
