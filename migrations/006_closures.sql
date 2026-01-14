CREATE TABLE IF NOT EXISTS closures (
  id SERIAL PRIMARY KEY,
  incident_number TEXT NOT NULL,
  work_notes TEXT NOT NULL,
  resolution_summary TEXT NOT NULL,
  closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_closures_incident ON closures(incident_number);

