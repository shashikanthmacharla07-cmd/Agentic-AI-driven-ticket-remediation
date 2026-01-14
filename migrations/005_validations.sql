CREATE TABLE IF NOT EXISTS validations (
  id SERIAL PRIMARY KEY,
  incident_number TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success','partial','rollback','escalate')),
  signals JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validations_incident ON validations(incident_number);
CREATE INDEX IF NOT EXISTS idx_validations_status ON validations(status);

