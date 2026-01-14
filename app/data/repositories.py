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

