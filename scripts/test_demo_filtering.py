
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from app.agents.planner import PlannerAgent
from app.models import PipelineContext, Incident, Classification
from langchain_core.messages import AIMessage

# Mock Repo
class MockRepo:
    async def upsert(self, *args):
        pass

# Mock AWX Client
class MockAWXClient:
    pass

async def test_demo_playbook_selection():
    print("Testing 'Demo Playbook' Selection...")
    
    # We want to see if the REAL LLM selects it. 
    # But since we can't easily rely on the real LLM in this script without Docker/Env setup working perfectly (which failed before with 404),
    # I will simulate the "bad" behavior with a mock to prove *my fix* would stop it IF it happened, 
    # OR I can try to run with the real LLM if I fix the URL. 
    # The previous error was `model 'llama3' not found`. The env var in docker-compose is `http://host.docker.internal:11434`. 
    # If I run locally on the VM, I should use `http://localhost:11434` (if ollama is running there) or the container URL.
    
    # Actually, the user's output `Planner LLM output: ...` confirms the behavior. I don't necessarily need to reproduce it with a live LLM to know I need to fix it.
    # I can just verify that `_filter_playbooks` REMOVES it.
    
    agent = PlannerAgent(repo=MockRepo(), awx_client=MockAWXClient())
    
    params = {
        "short_description": "install ntp on server",
        "description": "Please install ntp package on lin-server-01",
        "service": "compute",
        "severity": "low",
        "resource_id": "lin-server-01"
    }
    incident = Incident(number="INC_DEMO_TEST", source="manual", **params)
    classification = Classification(labels=["software_install"], severity="P3", eligibility="auto", confidence=0.9)
    ctx = PipelineContext(incident=incident, classification=classification)
    
    # Playbooks including the Demo one
    playbooks = [
        {"id": 7, "name": "Demo Job Template", "description": "A demo playbook"},
        {"id": 10, "name": "linux-cpu-cleanup", "description": "Fixes high cpu on linux"},
    ]
    
    # Test Filtering
    filtered = agent._filter_playbooks(ctx, playbooks)
    print(f"Filtered Playbooks: {[p['name'] for p in filtered]}")
    
    demo_present = any(p['id'] == 7 for p in filtered)
    if demo_present:
        print("FAILURE: 'Demo Job Template' (ID 7) was NOT filtered out.")
    else:
        print("SUCCESS: 'Demo Job Template' (ID 7) WAS filtered out.")

if __name__ == "__main__":
    asyncio.run(test_demo_playbook_selection())
