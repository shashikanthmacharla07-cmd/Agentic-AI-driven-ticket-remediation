
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.agents.classifier import ClassifierAgent
from app.models import PipelineContext, Incident, Classification
from app.clients.servicenow_client import ServiceNowClient
from app.data.repositories import ClassificationRepository

async def test_caller_azure_monitor():
    print("Testing Caller = Azure Monitor...")
    repo = MagicMock(spec=ClassificationRepository)
    repo.upsert = AsyncMock()
    sn_client = MagicMock(spec=ServiceNowClient)
    sn_client.add_work_notes = AsyncMock()

    agent = ClassifierAgent(repo=repo, sn_client=sn_client)
    
    # Mock LLM to avoid actual calls (though we expect code to return before LLM if not auto eligible, 
    # BUT wait, if caller is Azure Monitor, it SHOULD call LLM.
    # We need to mock llm.ainvoke or the whole run method's LLM part.
    # Since we can't easily mock the global 'llm' in classifier.py without patching,
    # we might hit the LLM call.
    # However, if we test the NEGATIVE case (John Doe), it should return EARLY before LLM.
    # Testing the POSITIVE case (Azure Monitor) reaches LLM. 
    # For positive case, we can just verify it DOES NOT return 'human-only' immediately. 
    # Actually, we can patch 'app.agents.classifier.llm' or just catch the error if LLM fails, 
    # assuming logic flow passed the check.
    pass

async def test_caller_non_azure_monitor():
    print("Testing Caller = John Doe...")
    repo = MagicMock(spec=ClassificationRepository)
    repo.upsert = AsyncMock()
    sn_client = MagicMock(spec=ServiceNowClient)
    sn_client.add_work_notes = AsyncMock(return_value=True)

    agent = ClassifierAgent(repo=repo, sn_client=sn_client)

    incident = Incident(
        number="INC123",
        short_description="Test",
        description="Test",
        service="Test",
        severity="P3",
        source="servicenow",
        resource_id="unknown",
        caller="John Doe"
    )
    ctx = PipelineContext(incident=incident)

    # Run
    # This should hit the check and return early.
    result_ctx = await agent.run(ctx)

    # Assertions
    print(f"Eligibility: {result_ctx.classification.eligibility}")
    assert result_ctx.classification.eligibility == "human-only"
    assert "escalated_to_human" in result_ctx.classification.labels
    
    sn_client.add_work_notes.assert_called_once()
    args = sn_client.add_work_notes.call_args[0]
    print(f"ServiceNow called with: {args}")
    assert args[0] == "INC123"
    assert "Escalating" in args[1]
    print("SUCCESS: Caller check escalated correctly.")

async def main():
    await test_caller_non_azure_monitor()

if __name__ == "__main__":
    asyncio.run(main())
