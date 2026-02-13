
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from app.agents.classifier import ClassifierAgent
from app.agents.planner import PlannerAgent
from app.models import PipelineContext, Incident, Classification, Plan
from langchain_core.messages import AIMessage

# Mock Repo
class MockRepo:
    async def upsert(self, *args):
        pass

# Mock AWX Client
class MockAWXClient:
    pass

async def test_ntp_scenario():
    print("Testing 'Install NTP' Scenario...")
    
    # --- SETUP ---
    # Mock LLM response for Classifier
    # explicitly NOT returning high_cpu
    classifier_response = '{"labels": ["software_install", "ntp"], "severity": "P3", "eligibility": "auto", "confidence": 0.9}'
    
    # Mock LLM response for Planner
    # Explicitly returning NO playbook
    planner_response = '{"playbook_id": "0", "playbook_name": "No suitable playbook", "prechecks": [], "rollback_steps": [], "risk_score": 0.0, "eligibility": "human-only"}'

    params = {
        "short_description": "install ntp on server",
        "description": "Please install ntp package on lin-server-01",
        "service": "compute",
        "severity": "low",
        "resource_id": "lin-server-01"
    }
    
    incident = Incident(
        number="INC_NTP_TEST",
        source="manual",
        **params
    )
    
    # --- TEST CLASSIFIER ---
    print("\n--- Testing Classifier (Heuristics Removed) ---")
    
    # Patch Classifier LLM
    import app.agents.classifier as classifier_module
    original_classifier_llm = classifier_module.llm
    mock_classifier_llm = AsyncMock()
    mock_classifier_llm.ainvoke.return_value = AIMessage(content=classifier_response)
    classifier_module.llm = mock_classifier_llm
    
    try:
        classifier = ClassifierAgent(repo=MockRepo())
        ctx = PipelineContext(incident=incident)
        
        ctx = await classifier.run(ctx, playbooks=[])
        
        print(f"Classifier Labels: {ctx.classification.labels}")
        
        if "high_cpu" in ctx.classification.labels:
            print("FAILURE: Classifier added 'high_cpu' label (Heuristics likely still active).")
        else:
            print("SUCCESS: Classifier did NOT add 'high_cpu' label.")
            
    finally:
        classifier_module.llm = original_classifier_llm

    # --- TEST PLANNER ---
    print("\n--- Testing Planner (Keyword Matching Removed) ---")
    
    # Patch Planner LLM
    import app.agents.planner as planner_module
    original_planner_llm = planner_module.llm
    mock_planner_llm = AsyncMock()
    mock_planner_llm.ainvoke.return_value = AIMessage(content=planner_response)
    planner_module.llm = mock_planner_llm
    
    try:
        planner = PlannerAgent(repo=MockRepo(), awx_client=MockAWXClient())
        
        # Provide playbooks that MIGHT have triggered keywords before
        playbooks = [
            {"id": 10, "name": "linux-cpu-cleanup", "description": "Fixes high cpu on linux"},
            {"id": 11, "name": "resize_disk", "description": "Resizes disk volume"},
        ]
        
        ctx = await planner.run(ctx, playbooks=playbooks)
        
        print(f"Selected Playbook ID: {ctx.plan.playbook_id}")
        print(f"Selected Playbook Name: {ctx.plan.playbook_name}")
        
        if ctx.plan.playbook_id == "0":
            print("SUCCESS: Planner returned ID '0' (No suitable playbook).")
        elif str(ctx.plan.playbook_id) == "10":
            print("FAILURE: Planner matched 'linux-cpu-cleanup' (Keyword matching likely still active).")
        else:
            print(f"FAILURE: Planner selected ID {ctx.plan.playbook_id} unexpected.")

    finally:
        planner_module.llm = original_planner_llm

if __name__ == "__main__":
    asyncio.run(test_ntp_scenario())
