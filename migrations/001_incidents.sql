CREATE TABLE IF NOT EXISTS incidents (
  number TEXT PRIMARY KEY,
  source TEXT,
  resource_id TEXT,
  service TEXT,
  severity TEXT CHECK (severity IN ('P1','P2','P3','P4')),
  short_description TEXT,
  description TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_service ON incidents(service);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);

