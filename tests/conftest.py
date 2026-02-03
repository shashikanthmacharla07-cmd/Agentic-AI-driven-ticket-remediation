# tests/conftest.py
"""
Shared pytest fixtures for the agentic ticket remediation project.
"""
import os

# Set required environment variables before any app imports
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# ========================================
# Sample Data Fixtures
# ========================================

@pytest.fixture
def sample_raw_incident() -> Dict[str, Any]:
    """Sample raw incident payload from ServiceNow."""
    return {
        "number": "INC0010001",
        "sys_id": "abc123def456",
        "short_description": "High CPU on lin-server-01",
        "description": "CPU utilization is at 95% on production server lin-server-01",
        "severity": "2",
        "state": "1",
        "cmdb_ci": {"value": "server-123", "display_value": "lin-server-01"},
        "assignment_group": {"value": "04d7f8c4c38e3610cf197cec050131f5", "display_value": "Infra-team"},
    }

@pytest.fixture
def sample_incident():
    """Sample parsed Incident model."""
    from app.models import Incident
    return Incident(
        sys_id="abc123def456",
        number="INC0010001",
        source="servicenow",
        resource_id="server-123",
        service="orchestrator",
        severity="P2",
        short_description="High CPU on lin-server-01",
        description="CPU utilization is at 95% on production server lin-server-01",
        context={"os": "linux"}
    )

@pytest.fixture
def sample_classification():
    """Sample Classification model."""
    from app.models import Classification
    return Classification(
        labels=["high_cpu"],
        confidence=0.9,
        eligibility="auto",
        severity="P2"
    )

@pytest.fixture
def sample_plan():
    """Sample Plan model."""
    from app.models import Plan
    return Plan(
        playbook_id="9",
        playbook_name="Linux_Kill_CPU_Utilization",
        prechecks=["Check current CPU usage"],
        rollback_steps=["Restart affected services"],
        risk_score=0.3,
        eligibility="auto"
    )

@pytest.fixture
def sample_execution():
    """Sample ExecutionLog model."""
    from app.models import ExecutionLog
    return ExecutionLog(
        job_id="12345",
        steps=[{"event": "runner_on_ok", "task": "Kill high CPU process"}],
        outputs=[],
        status="successful",
        finished_at="2026-02-03T14:00:00Z"
    )

@pytest.fixture
def sample_validation():
    """Sample ValidationSignals model."""
    from app.models import ValidationSignals
    return ValidationSignals(
        metrics={"cpu_after": 45},
        logs={},
        synthetics={},
        decision="success"
    )

@pytest.fixture
def sample_playbooks() -> List[Dict[str, Any]]:
    """Sample AWX playbooks list."""
    return [
        {"id": "7", "name": "Demo Job Template", "description": "Demo playbook"},
        {"id": "9", "name": "Linux_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Linux"},
        {"id": "10", "name": "Clean up var filesystem", "description": "Archive old logs and clean up disk space"},
        {"id": "11", "name": "Windows_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Windows"},
    ]

# ========================================
# Mock Fixtures
# ========================================

@pytest.fixture
def mock_llm_response():
    """Factory fixture to create mock LLM responses."""
    def _create_mock(content: str):
        mock_msg = MagicMock()
        mock_msg.content = content
        return mock_msg
    return _create_mock

@pytest.fixture
def mock_pg_pool():
    """Mock PostgreSQL connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool

@pytest.fixture
def mock_awx_client(sample_playbooks):
    """Mock AWX client."""
    from app.clients.awx_client import AWXClient
    client = MagicMock(spec=AWXClient)
    client.list_job_templates = AsyncMock(return_value=sample_playbooks)
    client.launch_job = AsyncMock(return_value=12345)
    client.poll_job = AsyncMock(return_value=("successful", [], "2026-02-03T14:00:00Z"))
    client.job_status = AsyncMock(return_value="successful")
    return client

@pytest.fixture
def mock_snow_client():
    """Mock ServiceNow client."""
    from app.clients.servicenow_client import ServiceNowClient
    client = MagicMock(spec=ServiceNowClient)
    client.get_incident = AsyncMock(return_value={"sys_id": "abc123", "number": "INC0010001"})
    client.update_incident = AsyncMock(return_value=True)
    client.add_work_notes = AsyncMock(return_value=True)
    client.query_incidents = AsyncMock(return_value=[])
    return client

@pytest.fixture
def mock_repos(mock_pg_pool):
    """Mock all repository classes."""
    from app.data.repositories import (
        IncidentRepository, ClassificationRepository, PlanRepository,
        ExecutionRepository, ValidationRepository, ClosureRepository
    )
    return {
        "incident": MagicMock(spec=IncidentRepository, upsert=AsyncMock()),
        "classification": MagicMock(spec=ClassificationRepository, upsert=AsyncMock()),
        "plan": MagicMock(spec=PlanRepository, upsert=AsyncMock()),
        "execution": MagicMock(spec=ExecutionRepository, insert=AsyncMock()),
        "validation": MagicMock(spec=ValidationRepository, insert=AsyncMock()),
        "closure": MagicMock(spec=ClosureRepository, insert=AsyncMock()),
    }
