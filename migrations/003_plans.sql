CREATE TABLE IF NOT EXISTS plans (
  incident_number TEXT PRIMARY KEY,
  playbook_id TEXT NOT NULL,
  prechecks JSONB,
  rollback_steps JSONB,
  risk_score DOUBLE PRECISION CHECK (risk_score >= 0 AND risk_score <= 1),
  eligibility TEXT CHECK (eligibility IN ('auto','human-only')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plans_playbook_id ON plans(playbook_id);

