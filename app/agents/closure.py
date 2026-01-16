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
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
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
            try:
                parsed_dict = parser.parse(msg.content)
            except Exception:
                parsed_dict = json.loads(msg.content)

            print(f"[ClosureAgent] Parsed closure dict: {parsed_dict}")

            if isinstance(parsed_dict, dict):
                parsed_dict.setdefault("closed_by", "orchestrator")
                parsed_dict.setdefault("incident_id", ctx.incident.number)

                exec_status = getattr(ctx.execution, 'status', 'unknown')
                val_decision = getattr(ctx.validation, 'decision', 'unknown')

                # Resolution fallback
                if parsed_dict.get("resolution") not in ["resolved", "duplicate", "false-positive", "escalated"]:
                    parsed_dict["resolution"] = "resolved" if exec_status == "successful" else "escalated"

                # Override hallucinated failure notes if execution was successful
                if exec_status == "successful" and val_decision == "success":
                    print("[ClosureAgent] Overriding LLM notes to reflect successful remediation.")
                    parsed_dict["resolution"] = "resolved"
                    parsed_dict["resolution_summary"] = "Automated remediation successful"
                    parsed_dict["work_notes"] = f"Executed playbook {ctx.plan.playbook_name} successfully. Validation confirmed resolution."

                # Ensure non-empty fields
                if not parsed_dict.get("work_notes") or not str(parsed_dict["work_notes"]).strip():
                    parsed_dict["work_notes"] = "Closed by orchestrator."
                if not parsed_dict.get("resolution_summary") or not str(parsed_dict["resolution_summary"]).strip():
                    parsed_dict["resolution_summary"] = "Incident processed by orchestration agent."

                closure = Closure(**parsed_dict)
            else:
                closure = parsed_dict

            print(f"[ClosureAgent] Closure object created: {closure}")

        except Exception as e:
            print(f"[ClosureAgent] Fatal parse error: {e}")
            raise HTTPException(status_code=500, detail=f"ClosureAgent: invalid LLM output {e}")

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
                exec_status = getattr(ctx.execution, 'status', 'unknown')
                val_decision = getattr(ctx.validation, 'decision', 'unknown')

                if exec_status == "successful" and val_decision == "success":
                    print(f"[ClosureAgent] Execution and validation successful. Closing incident.")
                    await self.sn_client.update_incident(number, closure.work_notes, closure.resolution_summary)
                else:
                    print(f"[ClosureAgent] Incident not resolved (Execution: {exec_status}, Validation: {val_decision}). Adding work notes only.")
                    note = (closure.work_notes or "") + "\n\n" + (closure.resolution_summary or "")
                    await self.sn_client.add_work_notes(number, note.strip())
            except Exception as e:
                print(f"[ClosureAgent] Warning: Failed to update ServiceNow incident: {e}")

        ctx.closure = closure
        return ctx
