# tests/test_orchestrator.py
"""
Unit tests for the OrchestrationAgent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestOrchestrationAgent:
    """Tests for OrchestrationAgent."""

    @pytest.fixture
    def mock_agents(self, sample_incident, sample_classification, sample_plan, sample_execution, sample_validation):
        """Create mock agents for testing orchestration."""
        from app.models import PipelineContext, Closure
        
        # Create mock agents
        intake = MagicMock()
        classifier = MagicMock()
        planner = MagicMock()
        executor = MagicMock()
        validator = MagicMock()
        closure = MagicMock()
        
        # Setup return contexts
        async def intake_run(ctx, raw):
            ctx.incident = sample_incident
            return ctx
        
        async def classifier_run(ctx, **kwargs):
            ctx.classification = sample_classification
            return ctx
        
        async def planner_run(ctx, **kwargs):
            ctx.plan = sample_plan
            return ctx
        
        async def executor_run(ctx):
            ctx.execution = sample_execution
            return ctx
        
        async def validator_run(ctx, telemetry):
            ctx.validation = sample_validation
            return ctx
        
        async def closure_run(ctx):
            ctx.closure = Closure(
                incident_id=sample_incident.number,
                resolution="resolved",
                work_notes="Fixed",
                resolution_summary="Issue resolved"
            )
            return ctx
        
        intake.run = AsyncMock(side_effect=intake_run)
        classifier.run = AsyncMock(side_effect=classifier_run)
        planner.run = AsyncMock(side_effect=planner_run)
        planner.awx_client = MagicMock()
        planner.awx_client.list_job_templates = AsyncMock(return_value=[])
        executor.run = AsyncMock(side_effect=executor_run)
        validator.run = AsyncMock(side_effect=validator_run)
        closure.run = AsyncMock(side_effect=closure_run)
        
        return {
            "intake": intake,
            "classifier": classifier,
            "planner": planner,
            "executor": executor,
            "validator": validator,
            "closure": closure,
        }

    @pytest.mark.asyncio
    async def test_orchestration_full_pipeline(self, mock_agents, sample_raw_incident):
        """Test full orchestration pipeline execution."""
        from app.orchestrator import OrchestrationAgent
        
        orchestrator = OrchestrationAgent(**mock_agents)
        
        result = await orchestrator.run(sample_raw_incident)
        
        assert result.status == "success"
        assert result.incident == "INC0010001"
        assert result.job_id == "12345"
        
        # Verify all agents were called
        mock_agents["intake"].run.assert_called_once()
        mock_agents["classifier"].run.assert_called_once()
        mock_agents["planner"].run.assert_called_once()
        mock_agents["executor"].run.assert_called_once()
        mock_agents["validator"].run.assert_called_once()
        mock_agents["closure"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestration_human_only_gate(self, mock_agents, sample_raw_incident, sample_incident):
        """Test orchestration stops at human-only classification."""
        from app.orchestrator import OrchestrationAgent
        from app.models import Classification
        
        # Override classifier to return human-only
        async def classifier_human_only(ctx, **kwargs):
            ctx.classification = Classification(
                labels=["critical_issue"],
                confidence=0.9,
                eligibility="human-only",
                severity="P1"
            )
            return ctx
        
        mock_agents["classifier"].run = AsyncMock(side_effect=classifier_human_only)
        
        orchestrator = OrchestrationAgent(**mock_agents)
        
        result = await orchestrator.run(sample_raw_incident)
        
        assert result.status == "awaiting_approval"
        assert result.job_id is None
        
        # Verify planner and beyond were NOT called
        mock_agents["planner"].run.assert_not_called()
        mock_agents["executor"].run.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestration_intake_failure(self, mock_agents, sample_raw_incident):
        """Test orchestration handles intake failure."""
        from app.orchestrator import OrchestrationAgent
        
        # Make intake not set incident
        async def intake_fail(ctx, raw):
            return ctx  # Don't set ctx.incident
        
        mock_agents["intake"].run = AsyncMock(side_effect=intake_fail)
        
        orchestrator = OrchestrationAgent(**mock_agents)
        
        result = await orchestrator.run(sample_raw_incident)
        
        assert result.status == "error"
        # Classifier should not be called
        mock_agents["classifier"].run.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestration_exception_handling(self, mock_agents, sample_raw_incident):
        """Test orchestration handles exceptions gracefully."""
        from app.orchestrator import OrchestrationAgent
        
        # Make executor raise an exception
        mock_agents["executor"].run = AsyncMock(side_effect=Exception("AWX connection failed"))
        
        orchestrator = OrchestrationAgent(**mock_agents)
        
        result = await orchestrator.run(sample_raw_incident)
        
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_orchestration_incident_number_mapping(self, mock_agents, sample_incident):
        """Test orchestration maps incident_number to number."""
        from app.orchestrator import OrchestrationAgent
        
        # Incident with incident_number instead of number
        raw_incident = {
            "incident_number": "INC0099999",
            "description": "Test incident"
        }
        
        async def intake_check_number(ctx, raw):
            # Verify the number was mapped
            assert raw.get("number") == "INC0099999"
            ctx.incident = sample_incident
            return ctx
        
        mock_agents["intake"].run = AsyncMock(side_effect=intake_check_number)
        
        orchestrator = OrchestrationAgent(**mock_agents)
        await orchestrator.run(raw_incident)
        
        mock_agents["intake"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestration_rollback_on_validation_failure(self, mock_agents, sample_raw_incident, sample_validation):
        """Test orchestration triggers rollback when validation says rollback."""
        from app.orchestrator import OrchestrationAgent
        from app.models import ValidationSignals
        
        # Override validator to return rollback
        async def validator_rollback(ctx, telemetry):
            ctx.validation = ValidationSignals(
                decision="rollback",
                metrics={},
                logs={},
                synthetics={}
            )
            return ctx
        
        mock_agents["validator"].run = AsyncMock(side_effect=validator_rollback)
        
        orchestrator = OrchestrationAgent(**mock_agents)
        
        result = await orchestrator.run(sample_raw_incident)
        
        # Executor should be called twice (once for main run, once for rollback)
        assert mock_agents["executor"].run.call_count == 2
        assert result.status == "rollback"
