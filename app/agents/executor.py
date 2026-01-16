# app/agents/executor.py
import os
from fastapi import HTTPException
from app.models import PipelineContext, ExecutionLog
from app.data.repositories import ExecutionRepository
from app.clients.awx_client import AWXClient

class ExecutorAgent:
    def __init__(self, repo: ExecutionRepository, awx_client: AWXClient):
        self.repo = repo
        self.awx_client = awx_client

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.plan:
            raise HTTPException(status_code=400, detail="ExecutorAgent: plan missing")

        number = ctx.incident.number
            # Always execute

        # Prepare variables for the playbook
        extra_vars = {
            "incident_number": ctx.incident.number,
            "incident_description": ctx.incident.description,
            "incident_service": ctx.incident.service,
            "incident_severity": ctx.incident.severity,
            "classification_category": ctx.classification.labels[0] if ctx.classification and ctx.classification.labels else "unknown",
            "plan_prechecks": ctx.plan.prechecks if ctx.plan else [],
        }

        # Trigger AWX job with incident variables
        print(f"Launching job template {ctx.plan.playbook_id} with variables: {extra_vars}")
        try:
            job_id = await self.awx_client.launch_job(ctx.plan.playbook_id, extra_vars)
            print(f"Job launched with ID: {job_id}")

            # Poll job status/events
            status, events, finished_at = await self.awx_client.poll_job(job_id, timeout_seconds=300.0)
            print(f"Job {job_id} completed with status: {status}")
        except Exception as e:
            print(f"AWX job launch failed: {e}. Using mock job ID for testing.")
            # Return mock job ID for testing when AWX is unavailable
            import uuid
            job_id = str(abs(hash(uuid.uuid4())) % 10000)
            status = "failed"  # Correctly report failure
            events = [{"event": "error", "message": f"Execution failed (AWX unavailable: {str(e)})"}]
            finished_at = None

        execution = ExecutionLog(
            job_id=str(job_id),
            steps=events,
            outputs=[],
            status=status,
            finished_at=finished_at,
        )

            # Persist execution
        if self.repo:
            try:
                await self.repo.insert(number, execution)
            except Exception as e:
                print(f"Failed to insert execution: {e}")

        ctx.execution = execution
        return ctx

