
import pytest
from app.agents.classifier import ClassifierAgent
from app.models import PipelineContext, Incident

class TestUsernameExtraction:
    """Tests for username extraction in ClassifierAgent."""

    def test_extract_username_simple_pattern(self):
        """Test extraction with 'user: <name>' pattern."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Issue for user: jdoe",
            description="Please check",
            service="test",
            severity="3", # mapped to P3
            source="servicenow",
            resource_id="unknown"
        )
        
        username = agent._extract_username(ctx)
        assert username == "jdoe"

    def test_extract_username_userid_pattern(self):
        """Test extraction with 'userid: <name>' pattern."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Login failure userid: bsmith",
            description="Cannot login",
            service="test",
            severity="3",
            source="servicenow",
            resource_id="unknown"
        )
        
        username = agent._extract_username(ctx)
        assert username == "bsmith"

    def test_extract_username_for_user_pattern(self):
        """Test extraction with 'for user <name>' pattern."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Create account for user alice",
            description="New hire",
            service="test",
            severity="3",
            source="servicenow",
            resource_id="unknown"
        )
        
        username = agent._extract_username(ctx)
        assert username == "alice"

    def test_extract_username_on_behalf_of_pattern(self):
        """Test extraction with 'on behalf of <name>' pattern."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Ticket raised on behalf of bob",
            description="Issue",
            service="test",
            severity="3",
            source="servicenow",
            resource_id="unknown"
        )
        
        username = agent._extract_username(ctx)
        assert username == "bob"

    def test_extract_username_from_description(self):
        """Test extraction when username is in description but not short description."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Email issue",
            description="User charlie cannot send emails", # This might require sophisticated NLP or specific pattern "User <name>"
            service="test",
            severity="3",
            source="servicenow",
            resource_id="unknown"
        )
        # using a supported pattern in description
        ctx.incident.description = "details for user: charlie regarding email"
        
        username = agent._extract_username(ctx)
        assert username == "charlie"

    def test_extract_username_none(self):
        """Test no username found."""
        agent = ClassifierAgent(repo=None)
        ctx = PipelineContext()
        ctx.incident = Incident(
            short_description="Server down",
            description="Critical failure",
            service="test",
            severity="1",
            source="servicenow",
            resource_id="unknown"
        )
        
        username = agent._extract_username(ctx)
        assert username is None
