CREATE TABLE IF NOT EXISTS executions (
  id SERIAL PRIMARY KEY,
  incident_number TEXT NOT NULL,
  job_id TEXT NOT NULL,
  status TEXT NOT NULL,
  events JSONB,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_executions_incident ON executions(incident_number);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);

