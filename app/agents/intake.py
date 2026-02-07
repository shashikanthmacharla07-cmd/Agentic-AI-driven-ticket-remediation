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

    def _detect_os(self, text: str) -> str:
        if not text:
            return None
        
        words = text.lower().split()
        for word in words:
            # Check for specific prefixes mentioned in requirements
            # "lin" -> Linux, "win" -> Windows
            # We look for words that are likely hostnames (e.g. contain dashes or digits, or just start with these prefixes)
            # Simplest implementation based on user prompt "first 3 letters in the hostname"
            
            # Clean common punctuation from end of word
            clean_word = word.rstrip(".,;:?!")
            
            if clean_word.startswith("lin"):
                return "linux"
            elif clean_word.startswith("win"):
                return "windows"
        return None

    async def run(self, ctx: PipelineContext, raw_incident: dict) -> PipelineContext:
        """
        OPTIMIZED: Deterministic intake - extract fields directly from ServiceNow payload.
        No LLM call needed since ServiceNow already provides structured data.
        """
        # Extract incident number (required)
        incident_number = raw_incident.get("number") or raw_incident.get("incident_number")
        if not incident_number:
            raise HTTPException(status_code=400, detail="Incident number is required from ServiceNow payload.")
        
        # Extract fields directly from ServiceNow payload
        short_description = raw_incident.get("short_description", "")
        description = raw_incident.get("description", short_description)
        
        # Map ServiceNow severity to P1-P4
        sn_severity = str(raw_incident.get("severity", "3"))
        severity_map = {"1": "P1", "2": "P2", "3": "P3", "4": "P4"}
        severity = severity_map.get(sn_severity, "P3")
        
        # Extract other fields
        resource_id = raw_incident.get("cmdb_ci", {})
        if isinstance(resource_id, dict):
            resource_id = resource_id.get("value", "unknown")
        resource_id = resource_id or "unknown"
        
        service = raw_incident.get("business_service", {})
        if isinstance(service, dict):
            service = service.get("value", "orchestrator")
        service = service or "orchestrator"
        
        # Create incident object directly
        try:
            incident = Incident(
                number=incident_number,
                source="servicenow",
                resource_id=resource_id,
                service=service,
                severity=severity,
                short_description=short_description,
                description=description
            )
            print(f"Incident object: {incident}")
        except ValidationError as e:
            print(f"ValidationError: {e.errors()}")
            raise HTTPException(status_code=400, detail=f"Invalid incident intake: {e.errors()}")

        # Detect OS from short_description
        detected_os = self._detect_os(incident.short_description)
        if detected_os:
            incident.context["os"] = detected_os
            print(f"Detected OS: {detected_os}")

        # Persist incident
        if self.repo:
            try:
                await self.repo.upsert(incident)
            except Exception as e:
                print(f"Failed to upsert incident: {e}")
        
        ctx.incident = incident
        return ctx

