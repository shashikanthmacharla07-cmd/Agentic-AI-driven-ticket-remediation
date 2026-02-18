# app/agents/closure.py
import os
import json
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, Closure
from app.data.repositories import ClosureRepository
from app.clients.servicenow_client import ServiceNowClient

llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama2:7b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
    num_thread=2,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are a closure agent. Summarize the incident resolution based data provided.\n"
     "CRITICAL INSTRUCTIONS:\n"
     "1. LOOK at the 'Execution' execution status. If status is 'successful', you MUST state that remediation was SUCCESSFUL.\n"
     "2. If status is 'failed', 'timeout', or 'error', you MUST state that remediation FAILED.\n"
     "3. Do NOT invent actions like 'restarting VM' or 'software update' unless they explicitly appear in the 'Execution' steps or 'Plan'.\n"
     "3. If execution failed, 'resolution' must be 'escalated' (internal logic handles this, just describe it).\n"
     "4. 'work_notes' must be a factual summary of what the orchestrator did (e.g., 'Attempted playbook X, execution failed with error Y').\n"
     "5. 'resolution_summary' should be 'Automated remediation failed' if execution failed, or 'Automated remediation successful' if successful.\n"
     "Return only valid JSON, no markdown."),
    ("user", "Incident: {incident}\nClassification: {classification}\nPlan: {plan}\nExecution: {execution}\nValidation: {validation}\n\n"
             "Return JSON with keys: work_notes (string), resolution_summary (string), incident_id (string), closed_by (string), resolution (resolved|duplicate|false-positive|escalated).")
])

parser = JsonOutputParser(pydantic_object=Closure)

class ClosureAgent:
    def __init__(self, repo: ClosureRepository, sn_client: ServiceNowClient):
        self.repo = repo
        self.sn_client = sn_client

    async def escalate_manual(self, number: str, reason: str):
        """
        Manually escalate an incident without full context (e.g. from Orchestrator early exit).
        """
        print(f"[ClosureAgent] Manually escalating incident {number}: {reason}")
        
        # Create a closure record for tracking
        closure = Closure(
            incident_id=number,
            closed_by="orchestrator",
            resolution="escalated",
            work_notes=f"Agentic AI: Escalating to manual review. Reason: {reason}",
            resolution_summary="Automated remediation failed or not possible"
        )
        
        if self.repo:
            try:
                await self.repo.insert(number, closure)
            except Exception as e:
                print(f"[ClosureAgent] Warning: Failed to insert closure for manual escalation: {e}")

        if self.sn_client:
            try:
                await self.sn_client.escalate_incident(number, closure.work_notes)
            except Exception as e:
                print(f"[ClosureAgent] Warning: Failed to escalate ServiceNow incident: {e}")

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        """
        OPTIMIZED: Deterministic closure - generate work notes from templates.
        No LLM call needed since closure notes follow predictable patterns.
        """
        if not ctx.validation:
            raise HTTPException(status_code=400, detail="ClosureAgent: validation missing")

        number = ctx.incident.number
        if not number:
            raise HTTPException(status_code=400, detail="Incident number is required for closure DB insert.")

        # Get status values
        exec_status = getattr(ctx.execution, 'status', 'unknown') if ctx.execution else 'unknown'
        val_decision = getattr(ctx.validation, 'decision', 'unknown')
        playbook_name = ctx.plan.playbook_name if ctx.plan else 'unknown'
        job_id = ctx.execution.job_id if ctx.execution else 'N/A'
        
        # Generate closure notes deterministically based on status
        if exec_status == "successful" and val_decision == "success":
            resolution = "resolved"
            resolution_summary = "Automated remediation successful"
            work_notes = f"Agentic AI: Executed playbook '{playbook_name}' (Job ID: {job_id}) successfully. Validation confirmed resolution."
        elif exec_status == "successful" and val_decision in ["partial", "rollback"]:
            resolution = "escalated"
            resolution_summary = "Automated remediation partially successful - requires review"
            work_notes = f"Agentic AI: Executed playbook '{playbook_name}' (Job ID: {job_id}). Validation status: {val_decision}. Manual review recommended."
        else:
            resolution = "escalated"
            resolution_summary = "Automated remediation failed"
            work_notes = f"Agentic AI: Attempted playbook '{playbook_name}' (Job ID: {job_id}). Execution status: {exec_status}. Validation: {val_decision}. Escalating to manual review."
        
        print(f"[ClosureAgent] Generated closure: resolution={resolution}, exec={exec_status}, val={val_decision}")
        
        # Create closure object directly (no LLM call)
        closure = Closure(
            incident_id=number,
            closed_by="orchestrator",
            resolution=resolution,
            work_notes=work_notes,
            resolution_summary=resolution_summary
        )
        print(f"[ClosureAgent] Closure object created: {closure}")

        if not getattr(closure, "work_notes", None) or not str(closure.work_notes).strip():
            closure.work_notes = "Closed by orchestrator."
        if not getattr(closure, "resolution_summary", None) or not str(closure.resolution_summary).strip():
            closure.resolution_summary = "Incident resolved by orchestration pipeline."

        if self.repo:
            try:
                await self.repo.insert(number, closure)
            except Exception as e:
                print(f"[ClosureAgent] Warning: Failed to insert closure: {e}")

        if self.sn_client:
            print(f"[ClosureAgent] Attempting ServiceNow update: number={number}, user={getattr(self.sn_client, 'username', None)}")
            try:
                if resolution == "resolved":
                    print(f"[ClosureAgent] Execution and validation successful. Closing incident.")
                    await self.sn_client.update_incident(number, closure.work_notes, closure.resolution_summary)
                else:
                    print(f"[ClosureAgent] Incident not resolved (Resolution: {resolution}). Escalating.")
                    # Use escalate_incident for non-resolved cases to change state to On Hold
                    await self.sn_client.escalate_incident(number, closure.work_notes)
            except Exception as e:
                print(f"[ClosureAgent] Warning: Failed to update ServiceNow incident: {e}")

        ctx.closure = closure
        return ctx
