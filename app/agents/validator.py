# app/agents/validator.py
import os
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, ValidationSignals
from app.data.repositories import ValidationRepository
from app.data.repositories import ValidationRepository

llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama2:7b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
    num_thread=2,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are a validation agent. Evaluate the remediation outcome based on the AWX job status, job events, and telemetry.\n"
     "The decision must be:\n"
     "- success: if the job status is 'successful' and telemetry confirms remediation.\n"
     "- partial: if the job completed but telemetry shows only partial recovery.\n"
     "- rollback: if the job failed or caused further issues.\n"
     "- escalate: if the job timed out or status is unknown, requiring human intervention.\n"
     "Return only valid JSON."),
    ("user", "Incident: {incident}\nExecution: {execution}\nTelemetry: {telemetry}\n\n"
             "Return JSON with keys: decision (success|partial|rollback|escalate), metrics (dict), logs (dict), synthetics (dict).")
])

parser = JsonOutputParser(pydantic_object=ValidationSignals)

class ValidatorAgent:
    def __init__(self, repo: ValidationRepository):
        self.repo = repo

    async def run(self, ctx: PipelineContext, telemetry: dict) -> PipelineContext:
        """
        OPTIMIZED: Deterministic validation - check execution status directly.
        No LLM call needed since validation decision is based on job status.
        """
        if not ctx.execution:
            raise HTTPException(status_code=400, detail="ValidatorAgent: execution missing")

        number = ctx.incident.number
        if not number:
            raise HTTPException(status_code=400, detail="Incident number is required for validation DB insert.")

        # Determine validation decision based on execution status
        exec_status = getattr(ctx.execution, 'status', 'unknown')
        
        # Simple deterministic logic for validation decision
        if exec_status == "successful":
            decision = "success"
        elif exec_status in ["failed", "error", "canceled"]:
            decision = "rollback"
        elif exec_status in ["timeout", "unknown"]:
            decision = "escalate"
        else:
            decision = "partial"
        
        print(f"Validator: Execution status '{exec_status}' -> decision '{decision}'")
        
        # Create validation object directly (no LLM call)
        validation = ValidationSignals(
            decision=decision,
            metrics=telemetry.get("metrics", {}),
            logs=telemetry.get("logs", {}),
            synthetics=telemetry.get("synthetics", {})
        )
        print(f"Validation object: {validation}")

        if self.repo:
            try:
                await self.repo.insert(number, validation)
            except Exception as e:
                print(f"Failed to insert validation: {e}")

        ctx.validation = validation
        return ctx

