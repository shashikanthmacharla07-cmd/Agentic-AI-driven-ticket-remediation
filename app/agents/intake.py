# app/agents/intake.py
import os
import uuid
import time
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, Incident
from app.data.repositories import IncidentRepository

llm = ChatOllama(
    model=os.getenv("LLM_MODEL"),
    base_url=os.getenv("OLLAMA_BASE_URL"),
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an intake agent. Output only a valid JSON object with the following required fields: source, resource_id, service, severity, short_description, description. Use the actual values from the payload if present, otherwise use sensible defaults (e.g., source='servicenow', resource_id='unknown', service='orchestrator')."),
    ("user", "Extract the incident from this payload: {raw}\n\nOutput JSON with all required fields present and filled with values from the payload where possible.")
])

parser = JsonOutputParser(pydantic_object=Incident)

class IntakeAgent:
    def __init__(self, repo: IncidentRepository):
        self.repo = repo

    # Incident number generation removed; always use number from ServiceNow

    async def run(self, ctx: PipelineContext, raw_incident: dict) -> PipelineContext:

        # Always normalize and set incident number from ServiceNow
        msg = await llm.ainvoke(prompt.format(raw=raw_incident))
        print(f"LLM output: {repr(msg.content)}")
        try:
            parsed_dict = parser.parse(msg.content)
            print(f"Parsed dict: {parsed_dict}")
            # Fix severity to allowed values (P1-P4)
            allowed_severities = {"p1", "p2", "p3", "p4"}
            sev = parsed_dict.get("severity", "").strip().upper()
            if sev.lower() not in allowed_severities:
                # Map common severities to allowed values
                mapping = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
                sev = mapping.get(sev.lower(), "P3")
            parsed_dict["severity"] = sev
            # Always use incident number from ServiceNow payload, and error if missing
            incident_number = parsed_dict.get("number") or raw_incident.get("number")
            if not incident_number:
                raise HTTPException(status_code=400, detail="Incident number is required from ServiceNow payload.")
            parsed_dict["number"] = incident_number
            incident = Incident(**parsed_dict)
            print(f"Incident object: {incident}")
        except ValidationError as e:
            print(f"ValidationError: {e.errors()}")
            raise HTTPException(status_code=400, detail=f"Invalid incident intake: {e.errors()}")
        except Exception as e:
            print(f"Failed to parse or create incident: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to parse or create incident: {e}")

        # Only persist if incident was created
        if 'incident' in locals():
            if self.repo:
                try:
                    await self.repo.upsert(incident)
                except Exception as e:
                    print(f"Failed to upsert incident: {e}")
            ctx.incident = incident
            return ctx
        else:
            raise HTTPException(status_code=400, detail="Incident could not be created from LLM output.")

