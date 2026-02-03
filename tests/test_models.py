# tests/test_models.py
"""
Unit tests for Pydantic models.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError


class TestIncidentModel:
    """Tests for the Incident model."""

    def test_incident_valid(self):
        """Test creating a valid Incident."""
        from app.models import Incident
        incident = Incident(
            number="INC0010001",
            source="servicenow",
            resource_id="server-123",
            service="orchestrator",
            severity="P2",
            short_description="Test incident",
            description="Full description"
        )
        assert incident.number == "INC0010001"
        assert incident.source == "servicenow"
        assert incident.tags == {}
        assert incident.context == {}

    def test_incident_with_context(self):
        """Test Incident with context dictionary."""
        from app.models import Incident
        incident = Incident(
            source="servicenow",
            resource_id="server-123",
            service="orchestrator",
            severity="P1",
            short_description="Test",
            description="Test",
            context={"os": "linux", "region": "us-east"}
        )
        assert incident.context["os"] == "linux"

    def test_incident_optional_fields(self):
        """Test Incident with optional fields set to None."""
        from app.models import Incident
        incident = Incident(
            source="servicenow",
            resource_id="server-123",
            service="orchestrator",
            severity="P3",
            short_description="Test",
            description="Test"
        )
        assert incident.sys_id is None
        assert incident.number is None


class TestClassificationModel:
    """Tests for the Classification model."""

    def test_classification_valid(self):
        """Test creating a valid Classification."""
        from app.models import Classification
        classification = Classification(
            labels=["high_cpu", "linux"],
            confidence=0.95,
            eligibility="auto",
            severity="P2"
        )
        assert "high_cpu" in classification.labels
        assert classification.eligibility == "auto"

    def test_classification_human_only(self):
        """Test Classification with human-only eligibility."""
        from app.models import Classification
        classification = Classification(
            labels=["database_down"],
            confidence=0.8,
            eligibility="human-only",
            severity="P1"
        )
        assert classification.eligibility == "human-only"

    def test_classification_invalid_eligibility(self):
        """Test Classification with invalid eligibility fails validation."""
        from app.models import Classification
        with pytest.raises(ValidationError):
            Classification(
                labels=["test"],
                confidence=0.5,
                eligibility="invalid",  # Must be 'auto' or 'human-only'
                severity="P3"
            )


class TestPlanModel:
    """Tests for the Plan model."""

    def test_plan_valid(self):
        """Test creating a valid Plan."""
        from app.models import Plan
        plan = Plan(
            playbook_id="9",
            playbook_name="Linux_Kill_CPU_Utilization",
            prechecks=["Check CPU"],
            rollback_steps=["Restart service"],
            risk_score=0.3,
            eligibility="auto"
        )
        assert plan.playbook_id == "9"
        assert len(plan.prechecks) == 1
        assert plan.risk_score == 0.3

    def test_plan_empty_lists(self):
        """Test Plan with empty prechecks and rollback_steps."""
        from app.models import Plan
        plan = Plan(
            playbook_id="7",
            playbook_name="Demo",
            prechecks=[],
            rollback_steps=[],
            risk_score=0.0,
            eligibility="auto"
        )
        assert plan.prechecks == []
        assert plan.rollback_steps == []


class TestExecutionLogModel:
    """Tests for the ExecutionLog model."""

    def test_execution_successful(self):
        """Test ExecutionLog with successful status."""
        from app.models import ExecutionLog
        execution = ExecutionLog(
            job_id="12345",
            steps=[{"event": "ok"}],
            outputs=[],
            status="successful",
            finished_at="2026-01-01T00:00:00Z"
        )
        assert execution.status == "successful"

    def test_execution_failed(self):
        """Test ExecutionLog with failed status."""
        from app.models import ExecutionLog
        execution = ExecutionLog(
            job_id="12346",
            steps=[{"event": "failed"}],
            outputs=[],
            status="failed"
        )
        assert execution.status == "failed"

    def test_execution_defaults(self):
        """Test ExecutionLog default values."""
        from app.models import ExecutionLog
        execution = ExecutionLog()
        assert execution.job_id == "unknown"
        assert execution.steps == []
        assert execution.status == "success"

    def test_execution_invalid_status(self):
        """Test ExecutionLog with invalid status fails."""
        from app.models import ExecutionLog
        with pytest.raises(ValidationError):
            ExecutionLog(status="invalid_status")


class TestValidationSignalsModel:
    """Tests for the ValidationSignals model."""

    def test_validation_success(self):
        """Test ValidationSignals with success decision."""
        from app.models import ValidationSignals
        validation = ValidationSignals(
            metrics={"cpu": 30},
            logs={"message": "ok"},
            synthetics={},
            decision="success"
        )
        assert validation.decision == "success"

    def test_validation_rollback(self):
        """Test ValidationSignals with rollback decision."""
        from app.models import ValidationSignals
        validation = ValidationSignals(decision="rollback")
        assert validation.decision == "rollback"

    def test_validation_invalid_decision(self):
        """Test ValidationSignals with invalid decision fails."""
        from app.models import ValidationSignals
        with pytest.raises(ValidationError):
            ValidationSignals(decision="invalid")


class TestClosureModel:
    """Tests for the Closure model."""

    def test_closure_resolved(self):
        """Test Closure with resolved status."""
        from app.models import Closure
        closure = Closure(
            incident_id="INC0010001",
            closed_by="orchestrator",
            resolution="resolved",
            work_notes="Fixed by automation",
            resolution_summary="CPU issue resolved"
        )
        assert closure.resolution == "resolved"

    def test_closure_defaults(self):
        """Test Closure default values."""
        from app.models import Closure
        closure = Closure()
        assert closure.closed_by == "orchestrator"
        assert closure.resolution == "resolved"
        assert closure.incident_id == ""


class TestPipelineContextModel:
    """Tests for the PipelineContext model."""

    def test_empty_context(self):
        """Test empty PipelineContext."""
        from app.models import PipelineContext
        ctx = PipelineContext()
        assert ctx.incident is None
        assert ctx.classification is None
        assert ctx.plan is None
        assert ctx.execution is None
        assert ctx.validation is None
        assert ctx.closure is None

    def test_context_with_incident(self, sample_incident):
        """Test PipelineContext with incident set."""
        from app.models import PipelineContext
        ctx = PipelineContext(incident=sample_incident)
        assert ctx.incident.number == "INC0010001"


class TestIncidentRequestModel:
    """Tests for the IncidentRequest model."""

    def test_incident_request_valid(self):
        """Test creating a valid IncidentRequest."""
        from app.models import IncidentRequest
        request = IncidentRequest(
            incident_number="INC0010001",
            description="High CPU on server",
            severity="high",
            system="server-01",
            service="app-service"
        )
        assert request.incident_number == "INC0010001"
        assert request.description == "High CPU on server"

    def test_incident_request_minimal(self):
        """Test IncidentRequest with only required fields."""
        from app.models import IncidentRequest
        request = IncidentRequest(description="Test issue")
        assert request.description == "Test issue"
        assert request.incident_number is None


class TestOrchestratorResponseModel:
    """Tests for the OrchestratorResponse model."""

    def test_orchestrator_response(self):
        """Test creating OrchestratorResponse."""
        from app.models import OrchestratorResponse
        response = OrchestratorResponse(
            status="success",
            incident="INC0010001",
            job_id="12345"
        )
        assert response.status == "success"
        assert response.job_id == "12345"
