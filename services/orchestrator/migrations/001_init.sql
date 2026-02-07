CREATE TABLE IF NOT EXISTS jobs (
  id VARCHAR(64) PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
  status VARCHAR(32) NOT NULL,
  session_id VARCHAR(128),
  workspace_dir TEXT NOT NULL,
  requirement_text TEXT NOT NULL,
  selected_skill VARCHAR(64) NOT NULL,
  agent VARCHAR(64) NOT NULL DEFAULT 'build',
  model_json JSONB,
  output_contract_json JSONB,
  error_code VARCHAR(64),
  error_message TEXT,
  created_by VARCHAR(128) NOT NULL DEFAULT 'system',
  result_bundle_path TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_created_at ON jobs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_session_id ON jobs(session_id);

CREATE TABLE IF NOT EXISTS job_files (
  id BIGSERIAL PRIMARY KEY,
  job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  category VARCHAR(16) NOT NULL,
  relative_path TEXT NOT NULL,
  mime_type VARCHAR(128),
  size_bytes BIGINT NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_files_job_category ON job_files(job_id, category);

CREATE TABLE IF NOT EXISTS job_events (
  id BIGSERIAL PRIMARY KEY,
  job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  status VARCHAR(32),
  source VARCHAR(16) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  message TEXT,
  payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_created_at ON job_events(job_id, created_at);

CREATE TABLE IF NOT EXISTS permission_actions (
  id BIGSERIAL PRIMARY KEY,
  job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  request_id VARCHAR(128) NOT NULL,
  action VARCHAR(16) NOT NULL,
  actor VARCHAR(128) NOT NULL DEFAULT 'policy-engine',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permission_actions_job_request ON permission_actions(job_id, request_id);

CREATE TABLE IF NOT EXISTS idempotency_records (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  requirement_hash VARCHAR(64) NOT NULL,
  job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_idempotency_tenant_key_hash UNIQUE (tenant_id, idempotency_key, requirement_hash)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_job_id ON idempotency_records(job_id);
