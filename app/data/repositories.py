# app/data/repositories.py
from typing import Optional, Any, Dict, List
import asyncpg
import json
from app.models import (
    Incident,
    Classification,
    Plan,
    ExecutionLog,
    ValidationSignals,
    Closure,
)

class BaseRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def _execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def _fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)


class IncidentRepository(BaseRepository):
    async def upsert(self, incident: Incident) -> None:
        await self._execute(
            """
            INSERT INTO incidents (number, source, resource_id, service, severity, short_description, description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (number) DO UPDATE SET
              source = EXCLUDED.source,
              resource_id = EXCLUDED.resource_id,
              service = EXCLUDED.service,
              severity = EXCLUDED.severity,
              short_description = EXCLUDED.short_description,
              description = EXCLUDED.description
            """,
            incident.number,
            incident.source,
            incident.resource_id,
            incident.service,
            incident.severity,
            incident.short_description,
            incident.description,
        )

    async def get(self, number: str) -> Optional[Incident]:
        row = await self._fetchrow(
            "SELECT number, source, resource_id, service, severity, short_description, description FROM incidents WHERE number = $1",
            number,
        )
        if not row:
            return None
        return Incident(
            number=row["number"],
            source=row["source"],
            resource_id=row["resource_id"],
            service=row["service"],
            severity=row["severity"],
            short_description=row["short_description"],
            description=row["description"],
        )


class ClassificationRepository(BaseRepository):
    async def upsert(self, incident_number: str, classification: Classification) -> None:
        await self._execute(
            """
            INSERT INTO classifications (incident_number, labels, severity, eligibility, confidence)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (incident_number) DO UPDATE SET
              labels = EXCLUDED.labels,
              severity = EXCLUDED.severity,
              eligibility = EXCLUDED.eligibility,
              confidence = EXCLUDED.confidence
            """,
            incident_number,
            json.dumps(classification.labels),
            classification.severity,
            classification.eligibility,
            classification.confidence,
        )

    async def get(self, incident_number: str) -> Optional[Classification]:
        row = await self._fetchrow(
            "SELECT incident_number, labels, severity, eligibility, confidence FROM classifications WHERE incident_number = $1",
            incident_number,
        )
        if not row:
            return None
        return Classification(
            labels=json.loads(row["labels"]),
            severity=row["severity"],
            eligibility=row["eligibility"],
            confidence=row["confidence"],
        )


class PlanRepository(BaseRepository):
    async def upsert(self, incident_number: str, plan: Plan) -> None:
        await self._execute(
            """
            INSERT INTO plans (incident_number, playbook_id, prechecks, rollback_steps, risk_score, eligibility)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (incident_number) DO UPDATE SET
              playbook_id = EXCLUDED.playbook_id,
              prechecks = EXCLUDED.prechecks,
              rollback_steps = EXCLUDED.rollback_steps,
              risk_score = EXCLUDED.risk_score,
              eligibility = EXCLUDED.eligibility
            """,
            incident_number,
            plan.playbook_id,
            json.dumps(plan.prechecks),
            json.dumps(plan.rollback_steps),
            plan.risk_score,
            plan.eligibility,
        )

    async def get(self, incident_number: str) -> Optional[Plan]:
        row = await self._fetchrow(
            "SELECT incident_number, playbook_id, prechecks, rollback_steps, risk_score, eligibility FROM plans WHERE incident_number = $1",
            incident_number,
        )
        if not row:
            return None
        return Plan(
            playbook_id=row["playbook_id"],
            prechecks=json.loads(row["prechecks"]),
            rollback_steps=json.loads(row["rollback_steps"]),
            risk_score=row["risk_score"],
            eligibility=row["eligibility"],
        )


class ExecutionRepository(BaseRepository):
    async def insert(self, incident_number: str, execution: ExecutionLog) -> None:
        # Convert finished_at to datetime if it's a string
        finished_at = execution.finished_at
        if isinstance(finished_at, str):
            from dateutil import parser
            try:
                finished_at = parser.isoparse(finished_at)
            except Exception:
                finished_at = None
        await self._execute(
            """
            INSERT INTO executions (incident_number, job_id, status, events, started_at, finished_at)
            VALUES ($1, $2, $3, $4, NOW(), $5)
            """,
            incident_number,
            execution.job_id,
            execution.status,
            json.dumps(execution.steps),
            finished_at,
        )

    async def latest_by_incident(self, incident_number: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            SELECT id, incident_number, job_id, status, events, started_at, finished_at
            FROM executions
            WHERE incident_number = $1
            ORDER BY id DESC
            LIMIT 1
            """,
            incident_number,
        )
        return dict(row) if row else None

    async def list_by_incident(self, incident_number: str) -> List[Dict[str, Any]]:
        rows = await self._fetch(
            """
            SELECT id, incident_number, job_id, status, events, started_at, finished_at
            FROM executions
            WHERE incident_number = $1
            ORDER BY id ASC
            """,
            incident_number,
        )
        return [dict(r) for r in rows]


class ValidationRepository(BaseRepository):
    async def insert(self, incident_number: str, validation: ValidationSignals) -> None:
        await self._execute(
            """
            INSERT INTO validations (incident_number, status, signals, created_at)
            VALUES ($1, $2, $3, NOW())
            """,
            incident_number,
            validation.decision,
            json.dumps({
                "metrics": validation.metrics,
                "logs": validation.logs,
                "synthetics": validation.synthetics
            }),
        )

    async def latest_by_incident(self, incident_number: str) -> Optional[ValidationSignals]:
        row = await self._fetchrow(
            """
            SELECT id, incident_number, status, signals, created_at
            FROM validations
            WHERE incident_number = $1
            ORDER BY id DESC
            LIMIT 1
            """,
            incident_number,
        )
        if not row:
            return None
        return ValidationSignals(
            status=row["status"],
            signals=row["signals"],
        )


class ClosureRepository(BaseRepository):
    async def insert(self, incident_number: str, closure: Closure) -> None:
        await self._execute(
            """
            INSERT INTO closures (incident_number, work_notes, resolution_summary, closed_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (incident_number) DO UPDATE SET
              work_notes = EXCLUDED.work_notes,
              resolution_summary = EXCLUDED.resolution_summary,
              closed_at = NOW()
            """,
            incident_number,
            closure.work_notes,
            closure.resolution_summary,
        )

    async def latest_by_incident(self, incident_number: str) -> Optional[Closure]:
        row = await self._fetchrow(
            """
            SELECT id, incident_number, work_notes, resolution_summary, closed_at
            FROM closures
            WHERE incident_number = $1
            ORDER BY id DESC
            LIMIT 1
            """,
            incident_number,
        )
        if not row:
            return None
        return Closure(
            work_notes=row["work_notes"],
            resolution_summary=row["resolution_summary"],
        )


class PipelineRunRepository(BaseRepository):
    """Tracks pipeline execution status for each incident processing run."""

    async def create(self, incident_number: str) -> int:
        """Create or reset a pipeline run for an incident and return its id."""
        row = await self._fetchrow(
            """
            INSERT INTO pipeline_runs (incident_number, status, current_stage, started_at, finished_at, duration_ms, error_message)
            VALUES ($1, 'pending', 'pending', NOW(), NULL, NULL, NULL)
            ON CONFLICT (incident_number) DO UPDATE SET
              status = 'pending',
              current_stage = 'pending',
              started_at = NOW(),
              finished_at = NULL,
              duration_ms = NULL,
              error_message = NULL
            RETURNING id
            """,
            incident_number,
        )
        return row["id"]

    async def update_stage(self, run_id: int, stage: str) -> None:
        """Update the current stage of a pipeline run."""
        await self._execute(
            """
            UPDATE pipeline_runs
            SET status = $2, current_stage = $2
            WHERE id = $1
            """,
            run_id,
            stage,
        )

    async def complete(self, run_id: int, status: str, error_message: str = None) -> None:
        """Mark a pipeline run as completed (success or error)."""
        await self._execute(
            """
            UPDATE pipeline_runs
            SET status = $2,
                current_stage = $2,
                error_message = $3,
                finished_at = NOW(),
                duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000
            WHERE id = $1
            """,
            run_id,
            status,
            error_message,
        )

    async def is_recently_processed(self, incident_number: str) -> bool:
        """Check if an incident was successfully processed (replaces in-memory set)."""
        row = await self._fetchrow(
            """
            SELECT id FROM pipeline_runs
            WHERE incident_number = $1
              AND status IN ('success', 'awaiting_approval')
            LIMIT 1
            """,
            incident_number,
        )
        return row is not None

    async def has_active_run(self, incident_number: str) -> bool:
        """Check if an incident currently has an active (in-progress) pipeline run."""
        row = await self._fetchrow(
            """
            SELECT id FROM pipeline_runs
            WHERE incident_number = $1
              AND status NOT IN ('success', 'error', 'awaiting_approval')
            LIMIT 1
            """,
            incident_number,
        )
        return row is not None

    async def dashboard_summary(self) -> Dict[str, Any]:
        """Get aggregate stats for the dashboard."""
        rows = await self._fetch(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'success') AS success,
                COUNT(*) FILTER (WHERE status = 'error') AS errors,
                COUNT(*) FILTER (WHERE status = 'awaiting_approval') AS awaiting_approval,
                COUNT(*) FILTER (WHERE status NOT IN ('success', 'error', 'awaiting_approval')) AS in_progress,
                COALESCE(AVG(duration_ms) FILTER (WHERE status = 'success'), 0)::INTEGER AS avg_duration_ms
            FROM pipeline_runs
            """
        )
        row = rows[0] if rows else None
        if not row:
            return {"total": 0, "success": 0, "errors": 0, "awaiting_approval": 0, "in_progress": 0, "avg_duration_ms": 0}
        return dict(row)

    async def list_runs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List pipeline runs with details, most recent first."""
        rows = await self._fetch(
            """
            SELECT pr.id, pr.incident_number, pr.status, pr.current_stage,
                   pr.error_message, pr.started_at, pr.finished_at, pr.duration_ms,
                   i.short_description, i.severity
            FROM pipeline_runs pr
            LEFT JOIN incidents i ON i.number = pr.incident_number
            ORDER BY pr.started_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        result = []
        for r in rows:
            d = dict(r)
            # Convert datetime to ISO string for JSON serialization
            for key in ('started_at', 'finished_at'):
                if d.get(key):
                    d[key] = d[key].isoformat()
            result.append(d)
        return result

