CREATE TABLE IF NOT EXISTS classifications (
  incident_number TEXT PRIMARY KEY,
  labels TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('P1','P2','P3','P4')),
  eligibility TEXT NOT NULL CHECK (eligibility IN ('auto','human-only')),
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classifications_severity ON classifications(severity);
CREATE INDEX IF NOT EXISTS idx_classifications_eligibility ON classifications(eligibility);

-- Optional trigger to update updated_at
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_classifications_updated_at ON classifications;
CREATE TRIGGER trg_classifications_updated_at
BEFORE UPDATE ON classifications
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

