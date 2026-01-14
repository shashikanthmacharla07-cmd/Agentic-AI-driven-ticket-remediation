# app/agents/closure.py
import os
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, Closure
from app.data.repositories import ClosureRepository
from app.clients.servicenow_client import ServiceNowClient
from app.data.repositories import ClosureRepository
from app.clients.servicenow_client import ServiceNowClient

llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are a closure agent. Summarize the incident resolution.\n"
     "The 'work_notes' and 'resolution_summary' MUST explicitly mention:\n"
     "1. The AWX playbook name or ID used.\n"
     "2. Whether the execution was successful, timed out, or failed (based on execution status).\n"
     "3. The final validation decision (e.g., 'Verification confirmed full recovery').\n"
     "Return only valid JSON, no markdown."),
    ("user", "Incident: {incident}\nClassification: {classification}\nPlan: {plan}\nExecution: {execution}\nValidation: {validation}\n\n"
             "Return JSON with keys: work_notes (string), resolution_summary (string), incident_id (string), closed_by (string), resolution (resolved|duplicate|false-positive|escalated).")
])

parser = JsonOutputParser(pydantic_object=Closure)

class ClosureAgent:
    def __init__(self, repo: ClosureRepository, sn_client: ServiceNowClient):
        self.repo = repo
        self.sn_client = sn_client

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.validation:
            raise HTTPException(status_code=400, detail="ClosureAgent: validation missing")

        number = ctx.incident.number
        if not number:
            raise HTTPException(status_code=400, detail="Incident number is required for closure DB insert.")

        inputs = {
            "incident": ctx.incident.dict(),
            "classification": ctx.classification.dict(),
            "plan": ctx.plan.dict(),
            "execution": ctx.execution.dict(),
            "validation": ctx.validation.dict(),
        }

        msg = await llm.ainvoke(prompt.format(**inputs))
        print(f"Closure LLM output: {repr(msg.content)}")

        try:
            parsed_dict = parser.parse(msg.content)
            print(f"Parsed closure dict: {parsed_dict}")
            # Normalize values
            if isinstance(parsed_dict, dict):
                # Set defaults for None/invalid values
                if not parsed_dict.get("closed_by"):
                    parsed_dict["closed_by"] = "orchestrator"
                if not parsed_dict.get("incident_id"):
                    parsed_dict["incident_id"] = ctx.incident.number
                # Ensure resolution is valid
                if parsed_dict.get("resolution") not in ["resolved", "duplicate", "false-positive", "escalated"]:
                    parsed_dict["resolution"] = "resolved" # Internal status remains 'resolved'
                # Ensure work_notes and resolution_summary are non-empty strings
                if not parsed_dict.get("work_notes") or not str(parsed_dict["work_notes"]).strip():
                    parsed_dict["work_notes"] = "Closed by orchestrator."
                if not parsed_dict.get("resolution_summary") or not str(parsed_dict["resolution_summary"]).strip():
                    parsed_dict["resolution_summary"] = "The incident has been processed and resolved by the orchestration agent."
                
                closure = Closure(**parsed_dict)
            else:
                closure = parsed_dict
            print(f"Closure object: {closure}")
        except Exception as e:
            print(f"ClosureAgent: failed to parse LLM output: {e}")
            raise HTTPException(status_code=500, detail=f"ClosureAgent: invalid LLM output {e}")

        # FINAL fallback: ensure closure fields are always non-empty strings before DB insert
        if not getattr(closure, "work_notes", None) or not str(closure.work_notes).strip():
            closure.work_notes = "Closed by orchestrator."
        if not getattr(closure, "resolution_summary", None) or not str(closure.resolution_summary).strip():
            closure.resolution_summary = "Incident resolved by orchestration pipeline."

        # Persist (cache removed)
        if self.repo:
            try:
                await self.repo.insert(number, closure)
            except Exception as e:
                print(f"Failed to insert closure: {e}")
        # Cache removed

        # Update ServiceNow
        if self.sn_client:
            print(f"[ClosureAgent] Attempting ServiceNow update: number={number}, sys_id will be resolved, user={getattr(self.sn_client, 'username', None)}")
            try:
                # Check status explicitly
                # If execution timed out or failed, we do NOT close the incident.
                # using ctx.execution.status or defaults.
                exec_status = getattr(ctx.execution, 'status', 'unknown')
                
                if exec_status in ["timeout", "failed"]:
                    print(f"[ClosureAgent] Execution status is '{exec_status}'. Adding work notes only (keeping incident open).")
                    note = (closure.work_notes or "") + "\n\n" + (closure.resolution_summary or "")
                    result = await self.sn_client.add_work_notes(number, note.strip())
                else:
                    # Successful or unknown -> Close it
                    print(f"[ClosureAgent] Execution status is '{exec_status}'. Closing incident.")
                    result = await self.sn_client.update_incident(number, closure.work_notes or "", closure.resolution_summary or "")
                
                print(f"[ClosureAgent] ServiceNow update result: {result}")
            except Exception as e:
                print(f"Warning: Failed to update ServiceNow incident: {e}")

        ctx.closure = closure
        return ctx
