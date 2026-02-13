
import asyncio
import os
from app.agents.classifier import ClassifierAgent
from app.models import PipelineContext, Incident
from app.data.repositories import ClassificationRepository

# Mock Repo
class MockRepo:
    async def upsert(self, *args):
        pass

async def test_logic():
    print("Testing Classifier Logic...")
    
    agent = ClassifierAgent(repo=MockRepo())
    
    # Create dummy incident
    incident = Incident(
        number="INC0010048",
        source="manual",
        resource_id="lin-us-poc-01",
        service="orchestrator",
        severity="medium",
        short_description="create user john on lin-us-poc-01",
        description="create user john on lin-us-poc-01"
    )
    
    ctx = PipelineContext(incident=incident)
    
    # Run classifier
    # We pass empty playbooks list since we are testing classification labels, 
    # though prompts use playbooks. It should be fine.
    try:
        ctx = await agent.run(ctx, playbooks=[])
        
        print("\n--- Classification Result ---")
        print(f"Labels: {ctx.classification.labels}")
        print(f"Severity: {ctx.classification.severity}")
        print(f"Eligibility: {ctx.classification.eligibility}")
        print(f"Confidence: {ctx.classification.confidence}")
        
        if "create_user" in ctx.classification.labels:
            print("\nSUCCESS: 'create_user' label found!")
        else:
            print("\nFAILURE: 'create_user' label NOT found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Ensure env vars are set for LLM
    if not os.getenv("OLLAMA_BASE_URL"):
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    if not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = "phi:2.7b" # Use same model as env

    asyncio.run(test_logic())
