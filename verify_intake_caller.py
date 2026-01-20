
import os
import asyncio
# Set env var BEFORE importing app modules that use it
os.environ["LLM_MODEL"] = "dummy"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

from unittest.mock import MagicMock, AsyncMock
from app.agents.intake import IntakeAgent
from app.models import PipelineContext, Incident
from app.data.repositories import IncidentRepository

async def test_intake_caller_fallback():
    print("Testing Intake Agent Caller Fallback...")
    
    # Mock Repo
    repo = MagicMock(spec=IncidentRepository)
    repo.upsert = AsyncMock()
    
    agent = IntakeAgent(repo=repo)
    
    # Mock LLM to return JSON *without* caller
    # We need to mock the global 'llm' in intake.py or patch it.
    # Since we can't easily patch globals in this environment without reloading, 
    # lets assume we can patch 'agent.llm' if it was a simpler setup, 
    # but 'llm' is global in 'app.agents.intake'.
    
    # Actually, we can just run the logic effectively by mocking `llm.ainvoke`.
    from app.agents import intake
    
    mock_llm_response = MagicMock()
    mock_llm_response.content = '{"short_description": "Test", "description": "Desc", "service": "Test", "severity": "P3", "source": "test", "resource_id": "r1"}'
    
    # Mock the entire llm object to avoid Pydantic validation errors
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    intake.llm = mock_llm
    
    # Raw incident WITH caller
    raw_incident = {
        "number": "INC123",
        "short_description": "Test",
        "description": "Desc",
        "caller": "Azure Monitor",
        "severity": "3"
    }
    
    ctx = PipelineContext()
    
    # Run
    result_ctx = await agent.run(ctx, raw_incident)
    
    # Verify
    incident = result_ctx.incident
    print(f"Incident Created: {incident}")
    print(f"Caller: '{incident.caller}'")
    
    assert incident.caller == "Azure Monitor"
    print("SUCCESS: Caller explicitly mapped from raw input.")

if __name__ == "__main__":
    asyncio.run(test_intake_caller_fallback())
