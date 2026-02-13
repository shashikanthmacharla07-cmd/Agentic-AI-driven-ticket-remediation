
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from app.agents.classifier import ClassifierAgent
from app.models import PipelineContext, Incident, Classification
from langchain_core.messages import AIMessage

# Mock Repo
class MockRepo:
    async def upsert(self, *args):
        pass

async def test_classifier_eligibility_override():
    print("Testing Classifier Eligibility Override...")
    
    # Mock LLM
    mock_llm = AsyncMock()
    # Return a response that says 'human-only' to see if we override it
    mock_response_content = '{"labels": ["server_down"], "severity": "P1", "eligibility": "human-only", "confidence": 0.8}'
    mock_llm.ainvoke.return_value = AIMessage(content=mock_response_content)
    
    # Patch the global 'llm' in classifier module
    import app.agents.classifier as classifier_module
    original_llm = classifier_module.llm
    classifier_module.llm = mock_llm
    
    try:
        agent = ClassifierAgent(repo=MockRepo())
        
        incident = Incident(
            number="INC00TEST",
            source="manual",
            resource_id="server-01",
            service="compute",
            severity="high",
            short_description="Server is down",
            description="Server is completely unreachable"
        )
        ctx = PipelineContext(incident=incident)
        
        # Run classifier
        ctx = await agent.run(ctx, playbooks=[])
        
        print(f"LLM returned eligibility: human-only (mocked)")
        print(f"Final Classification Eligibility: {ctx.classification.eligibility}")
        
        if ctx.classification.eligibility == "auto":
            print("SUCCESS: Eligibility forced to 'auto'.")
        else:
            print("FAILURE: Eligibility was not overridden.")
            
    finally:
        # Restore
        classifier_module.llm = original_llm

if __name__ == "__main__":
    asyncio.run(test_classifier_eligibility_override())
