CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  task_type TEXT NOT NULL DEFAULT 'analysis',
  complexity TEXT NOT NULL DEFAULT 'medium',
  workspace_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'analysis';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS complexity TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS workspace_id UUID;

CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  input_summary TEXT,
  output_summary TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS baton_packets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  from_agent TEXT NOT NULL,
  to_agent TEXT,
  summary TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  root_path TEXT NOT NULL,
  repo_url TEXT,
  branch TEXT,
  runtime_mode TEXT NOT NULL DEFAULT 'native',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS context_references (
  ref_id TEXT PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  content_type TEXT NOT NULL,
  original_content TEXT NOT NULL,
  summary TEXT NOT NULL,
  retrieval_hint TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS context_bundles (
  bundle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  target_agent TEXT NOT NULL,
  target_model TEXT NOT NULL,
  token_budget INTEGER NOT NULL,
  raw_estimated_tokens INTEGER NOT NULL DEFAULT 0,
  optimized_estimated_tokens INTEGER NOT NULL DEFAULT 0,
  token_savings_estimate INTEGER NOT NULL DEFAULT 0,
  token_savings_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
  estimated_cost_raw_usd DOUBLE PRECISION,
  estimated_cost_optimized_usd DOUBLE PRECISION,
  estimated_cost_saved_usd DOUBLE PRECISION,
  optimized_context JSONB NOT NULL,
  included_refs TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS raw_estimated_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS optimized_estimated_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS token_savings_estimate INTEGER NOT NULL DEFAULT 0;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS token_savings_pct DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS estimated_cost_raw_usd DOUBLE PRECISION;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS estimated_cost_optimized_usd DOUBLE PRECISION;
ALTER TABLE context_bundles ADD COLUMN IF NOT EXISTS estimated_cost_saved_usd DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS run_queue (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT,
  run_id UUID,
  available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS autonomy_snapshots (
  snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  cycle INTEGER NOT NULL,
  stage TEXT NOT NULL,
  state TEXT NOT NULL,
  strategy TEXT NOT NULL,
  quality_score INTEGER NOT NULL DEFAULT 0,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id_created_at
  ON agent_runs (task_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_tasks_workspace_id
  ON tasks (workspace_id);

CREATE INDEX IF NOT EXISTS idx_baton_packets_task_id_created_at
  ON baton_packets (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_events_task_id_created_at
  ON project_events (task_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_workspaces_root_path
  ON workspaces (root_path);

CREATE INDEX IF NOT EXISTS idx_context_references_task_id_created_at
  ON context_references (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_context_bundles_task_id_created_at
  ON context_bundles (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_run_queue_status_available_created
  ON run_queue (status, available_at, created_at);

CREATE INDEX IF NOT EXISTS idx_autonomy_snapshots_task_created
  ON autonomy_snapshots (task_id, created_at DESC);
