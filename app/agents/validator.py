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
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
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
        if not ctx.execution:
            raise HTTPException(status_code=400, detail="ValidatorAgent: execution missing")

        number = ctx.incident.number
        if not number:
            raise HTTPException(status_code=400, detail="Incident number is required for validation DB insert.")

        inputs = {
            "incident": ctx.incident.dict(),
            "execution": ctx.execution.dict(),
            "telemetry": telemetry,
        }

        msg = await llm.ainvoke(prompt.format(**inputs))
        print(f"Validator LLM output: {repr(msg.content)}")

        try:
            parsed_dict = parser.parse(msg.content)
            print(f"Parsed validation dict: {parsed_dict}")
            # Ensure it's a ValidationSignals object, not a dict
            if isinstance(parsed_dict, dict):
                validation = ValidationSignals(**parsed_dict)
            else:
                validation = parsed_dict
            print(f"Validation object: {validation}")
        except Exception as e:
            print(f"ValidatorAgent: failed to parse LLM output: {e}")
            raise HTTPException(status_code=500, detail=f"ValidatorAgent: invalid LLM output {e}")

        if self.repo:
            try:
                await self.repo.insert(number, validation)
            except Exception as e:
                print(f"Failed to insert validation: {e}")
        # Cache removed

        ctx.validation = validation
        return ctx

