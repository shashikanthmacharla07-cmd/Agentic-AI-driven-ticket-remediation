# tests/test_agents.py
"""
Unit tests for agent logic (with mocked LLM).
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set required environment variables before importing agents
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")


class TestIntakeAgentHelpers:
    """Tests for IntakeAgent helper methods."""

    def test_detect_os_linux(self):
        """Test OS detection for Linux hostname."""
        from app.agents.intake import IntakeAgent
        agent = IntakeAgent(repo=None)
        
        assert agent._detect_os("High CPU on lin-server-01") == "linux"
        assert agent._detect_os("Issue with linuxbox") == "linux"
        assert agent._detect_os("Check lin123 server") == "linux"

    def test_detect_os_windows(self):
        """Test OS detection for Windows hostname."""
        from app.agents.intake import IntakeAgent
        agent = IntakeAgent(repo=None)
        
        assert agent._detect_os("Problem on win-server-01") == "windows"
        assert agent._detect_os("windows-prod-server down") == "windows"
        assert agent._detect_os("Check WIN2019 machine") == "windows"

    def test_detect_os_unknown(self):
        """Test OS detection returns None for unknown."""
        from app.agents.intake import IntakeAgent
        agent = IntakeAgent(repo=None)
        
        assert agent._detect_os("High CPU on server-01") is None
        assert agent._detect_os("Database connection issue") is None
        assert agent._detect_os("") is None
        assert agent._detect_os(None) is None


class TestClassifierAgentHelpers:
    """Tests for ClassifierAgent helper methods."""

    def test_heuristic_labeler_cpu(self):
        """Test heuristic labeling for CPU issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("High CPU utilization on server")
        assert "high_cpu" in labels

    def test_heuristic_labeler_memory(self):
        """Test heuristic labeling for memory issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("High memory usage detected")
        assert "high_memory" in labels

    def test_heuristic_labeler_disk(self):
        """Test heuristic labeling for disk issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("Disk full on /var partition")
        assert "disk_full" in labels
        assert "var_full" in labels

    def test_heuristic_labeler_disk_tmp(self):
        """Test heuristic labeling for /tmp issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("No space left on /tmp")
        assert "disk_full" in labels
        assert "tmp_full" in labels

    def test_heuristic_labeler_cleanup(self):
        """Test heuristic labeling for cleanup issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("Storage cleanup required")
        assert "disk_full" in labels
        assert "filesystem_cleanup" in labels

    def test_heuristic_labeler_vm_availability(self):
        """Test heuristic labeling for VM availability."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("VM availability issue detected")
        assert "vm_availability" in labels
        assert "high_cpu" in labels  # Requirement: invoke CPU playbook

    def test_heuristic_labeler_no_match(self):
        """Test heuristic labeling returns empty for unrecognized issues."""
        from app.agents.classifier import ClassifierAgent
        agent = ClassifierAgent(repo=None)
        
        labels = agent._heuristic_labeler("General network connectivity problem")
        # Should not match any specific heuristics (no keywords present)
        assert "high_cpu" not in labels
        assert "high_memory" not in labels


class TestPlannerAgentHelpers:
    """Tests for PlannerAgent helper methods."""

    def test_get_playbook_for_classification_disk(self):
        """Test playbook mapping for disk issues."""
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent(repo=None, awx_client=None)
        
        result = agent._get_playbook_for_classification("disk_full")
        assert result is not None
        assert result["name"] == "Clean up var filesystem"

    def test_get_playbook_for_classification_storage(self):
        """Test playbook mapping for storage issues."""
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent(repo=None, awx_client=None)
        
        result = agent._get_playbook_for_classification("storage issue")
        assert result is not None
        assert result["name"] == "Clean up var filesystem"

    def test_get_playbook_for_classification_cpu(self):
        """Test playbook mapping for CPU issues."""
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent(repo=None, awx_client=None)
        
        result = agent._get_playbook_for_classification("high_cpu")
        assert result is not None
        assert result["name"] == "Linux_Kill_CPU_Utilization"

    def test_get_playbook_for_classification_unknown(self):
        """Test playbook mapping returns None for unknown category."""
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent(repo=None, awx_client=None)
        
        result = agent._get_playbook_for_classification("unknown_category")
        assert result is None

    def test_filter_playbooks_by_os_linux(self, sample_incident, sample_classification, sample_playbooks):
        """Test playbook filtering for Linux OS."""
        from app.agents.planner import PlannerAgent
        from app.models import PipelineContext
        
        agent = PlannerAgent(repo=None, awx_client=None)
        ctx = PipelineContext(incident=sample_incident, classification=sample_classification)
        
        # Ensure OS is linux
        ctx.incident.context["os"] = "linux"
        
        filtered = agent._filter_playbooks(ctx, sample_playbooks)
        
        # Should not include Windows playbook
        playbook_names = [pb["name"] for pb in filtered]
        assert "Windows_Kill_CPU_Utilization" not in playbook_names

    def test_filter_playbooks_by_os_windows(self, sample_incident, sample_classification, sample_playbooks):
        """Test playbook filtering for Windows OS."""
        from app.agents.planner import PlannerAgent
        from app.models import PipelineContext
        
        agent = PlannerAgent(repo=None, awx_client=None)
        ctx = PipelineContext(incident=sample_incident, classification=sample_classification)
        
        # Set OS to windows
        ctx.incident.context["os"] = "windows"
        
        filtered = agent._filter_playbooks(ctx, sample_playbooks)
        
        # Should not include Linux playbook
        playbook_names = [pb["name"] for pb in filtered]
        assert "Linux_Kill_CPU_Utilization" not in playbook_names


class TestPlaybookSelectionValidator:
    """Tests for PlaybookSelectionValidator."""

    def test_validate_playbook_selection_cpu_linux(self):
        """Test validator overrides to correct CPU playbook for Linux."""
        from app.agents.PlaybookSelectionValidator import validate_playbook_selection
        
        known_playbooks = {
            "high_cpu": {"id": "dynamic", "name": "Linux_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Linux"},
            "windows_high_cpu": {"id": "dynamic", "name": "Windows_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Windows"},
        }
        
        plan_data = {
            "playbook_id": "7",
            "playbook_name": "Demo Job Template",
        }
        
        result = validate_playbook_selection(plan_data, ["high_cpu"], known_playbooks, os_type="linux")
        assert result["playbook_name"] == "Linux_Kill_CPU_Utilization"

    def test_validate_playbook_selection_cpu_windows(self):
        """Test validator overrides to correct CPU playbook for Windows."""
        from app.agents.PlaybookSelectionValidator import validate_playbook_selection
        
        known_playbooks = {
            "high_cpu": {"id": "dynamic", "name": "Linux_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Linux"},
            "windows_high_cpu": {"id": "dynamic", "name": "Windows_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Windows"},
        }
        
        plan_data = {
            "playbook_id": "7",
            "playbook_name": "Demo",
        }
        
        result = validate_playbook_selection(plan_data, ["high_cpu"], known_playbooks, os_type="windows")
        assert result["playbook_name"] == "Windows_Kill_CPU_Utilization"
