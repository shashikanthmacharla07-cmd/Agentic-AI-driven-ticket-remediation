from app.models import PipelineContext, OrchestratorResponse
from app.agents.intake import IntakeAgent
from app.agents.classifier import ClassifierAgent
from app.agents.planner import PlannerAgent
from app.agents.executor import ExecutorAgent
from app.agents.validator import ValidatorAgent
from app.agents.closure import ClosureAgent

class OrchestrationAgent:
    def __init__(self, intake, classifier, planner, executor, validator, closure):
        self.intake = intake
        self.classifier = classifier
        self.planner = planner
        self.executor = executor
        self.validator = validator
        self.closure = closure

    async def run(self, raw_incident: dict) -> OrchestratorResponse:
        ctx = PipelineContext()
        # Map 'incident_number' to 'number' if present (from ServiceNow fetcher)
        if 'incident_number' in raw_incident and 'number' not in raw_incident:
            raw_incident['number'] = raw_incident['incident_number']
        try:
            print("Starting intake")
            ctx = await self.intake.run(ctx, raw_incident)
            print("Intake done")
            if not ctx.incident:
                print("Intake failed: ctx.incident is None")
                return OrchestratorResponse(
                    status="error",
                    incident=raw_incident.get("number") or "unknown",
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

            ctx = await self.classifier.run(ctx, playbooks=playbooks)
            print("Classifier done")

            # Policy gate
            if ctx.classification.eligibility == "human-only":
                return OrchestratorResponse(
                    status="awaiting_approval",
                    incident=ctx.incident.number,
                    job_id=None
                )

            print("Starting planner")
            ctx = await self.planner.run(ctx, playbooks=playbooks)
            print("Planner done")
            print("Starting executor")
            ctx = await self.executor.run(ctx)
            print("Executor done")
            print("Starting validator")
            ctx = await self.validator.run(ctx, {})
            print("Validator done")

            if ctx.validation.decision == "rollback":
                # Replace with explicit rollback plan if available
                ctx = await self.executor.run(ctx)

            print("Starting closure")
            ctx = await self.closure.run(ctx)
            print("Closure done")

            return OrchestratorResponse(
                status=ctx.validation.decision,
                incident=ctx.incident.number,
                job_id=ctx.execution.job_id if ctx.execution else None
            )
        except Exception as e:
            print(f"Error in orchestration: {e}")
            return OrchestratorResponse(
                status="error",
                incident=raw_incident.get("number") or "unknown",
                job_id=None
            )

