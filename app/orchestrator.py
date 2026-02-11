from app.models import PipelineContext, OrchestratorResponse
from app.agents.intake import IntakeAgent
from app.agents.classifier import ClassifierAgent
from app.agents.planner import PlannerAgent
from app.agents.executor import ExecutorAgent
from app.agents.validator import ValidatorAgent
from app.agents.closure import ClosureAgent

class OrchestrationAgent:
    def __init__(self, intake, classifier, planner, executor, validator, closure, pipeline_repo=None):
        self.intake = intake
        self.classifier = classifier
        self.planner = planner
        self.executor = executor
        self.validator = validator
        self.closure = closure
        self.pipeline_repo = pipeline_repo

    async def run(self, raw_incident: dict) -> OrchestratorResponse:
        ctx = PipelineContext()
        # Map 'incident_number' to 'number' if present (from ServiceNow fetcher)
        if 'incident_number' in raw_incident and 'number' not in raw_incident:
            raw_incident['number'] = raw_incident['incident_number']

        # Create pipeline run for tracking
        run_id = None
        incident_number = raw_incident.get("number") or raw_incident.get("incident_number") or "unknown"
        if self.pipeline_repo:
            try:
                run_id = await self.pipeline_repo.create(incident_number)
            except Exception as e:
                print(f"Failed to create pipeline run: {e}")

        try:
            # --- INTAKE ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "intake")
            print("Starting intake")
            ctx = await self.intake.run(ctx, raw_incident)
            print("Intake done")
            if not ctx.incident:
                print("Intake failed: ctx.incident is None")
                if run_id and self.pipeline_repo:
                    await self.pipeline_repo.complete(run_id, "error", "Intake failed: no incident produced")
                return OrchestratorResponse(
                    status="error",
                    incident=incident_number,
                    job_id=None
                )
            
            # Pre-fetch playbooks once for use in multiple agents
            playbooks = []
            awx_client = getattr(self.planner, 'awx_client', None)
            if awx_client:
                try:
                    playbooks = await awx_client.list_job_templates()
                except Exception as e:
                    print(f"Failed to pre-fetch playbooks: {e}")

            # --- CLASSIFIER ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "classifying")
            ctx = await self.classifier.run(ctx, playbooks=playbooks)
            print("Classifier done")

            # Policy gate
            if ctx.classification.eligibility == "human-only":
                if run_id and self.pipeline_repo:
                    await self.pipeline_repo.complete(run_id, "awaiting_approval")
                return OrchestratorResponse(
                    status="awaiting_approval",
                    incident=ctx.incident.number,
                    job_id=None
                )

            # --- PLANNER ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "planning")
            print("Starting planner")
            ctx = await self.planner.run(ctx, playbooks=playbooks)
            print("Planner done")
            
            # Check if planner decided to escalate (playbook_id='0')
            if ctx.plan.playbook_id == "0":
                print("Planner returned playbook_id='0' (No suitable playbook). Escalating to human.")
                if run_id and self.pipeline_repo:
                    await self.pipeline_repo.complete(run_id, "awaiting_approval", "No suitable playbook found")
                return OrchestratorResponse(
                    status="awaiting_approval",
                    incident=ctx.incident.number,
                    job_id=None
                )

            # --- EXECUTOR ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "executing")
            print("Starting executor")
            ctx = await self.executor.run(ctx)
            print("Executor done")

            # --- VALIDATOR ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "validating")
            print("Starting validator")
            ctx = await self.validator.run(ctx, {})
            print("Validator done")

            if ctx.validation.decision == "rollback":
                # Replace with explicit rollback plan if available
                ctx = await self.executor.run(ctx)

            # --- CLOSURE ---
            if run_id and self.pipeline_repo:
                await self.pipeline_repo.update_stage(run_id, "closing")
            print("Starting closure")
            ctx = await self.closure.run(ctx)
            print("Closure done")

            # --- COMPLETE ---
            final_status = ctx.validation.decision
            if run_id and self.pipeline_repo:
                # Map validation decision to pipeline status
                # 'success' -> 'success', 'rollback' -> 'error' (if rollback happened), 'failure' -> 'error'
                db_status = "success" if final_status == "success" else "error"
                await self.pipeline_repo.complete(run_id, db_status, f"Completed with status: {final_status}")

            return OrchestratorResponse(
                status=final_status,
                incident=ctx.incident.number,
                job_id=ctx.execution.job_id if ctx.execution else None
            )
        except Exception as e:
            print(f"Error in orchestration: {e}")
            if run_id and self.pipeline_repo:
                try:
                    await self.pipeline_repo.complete(run_id, "error", str(e))
                except Exception as pe:
                    print(f"Failed to update pipeline run on error: {pe}")
            return OrchestratorResponse(
                status="error",
                incident=raw_incident.get("number") or "unknown",
                job_id=None
            )
