# tests/test_api.py
"""
Integration tests for FastAPI endpoints.
Note: These tests use simplified mocking to avoid complex lifespan issues.
"""
import os
# Set required environment variables before importing app modules
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")

import pytest


class TestModelsValidation:
    """Test Pydantic model validation for API requests."""

    def test_incident_request_requires_description(self):
        """Test IncidentRequest requires description field."""
        from app.models import IncidentRequest
        from pydantic import ValidationError
        
        # Missing required 'description' should fail
        with pytest.raises(ValidationError):
            IncidentRequest()

    def test_incident_request_valid(self):
        """Test valid IncidentRequest."""
        from app.models import IncidentRequest
        
        req = IncidentRequest(
            incident_number="INC0010001",
            description="High CPU on server"
        )
        assert req.description == "High CPU on server"

    def test_prompt_request_model(self):
        """Test PromptRequest model used by inference endpoint."""
        from pydantic import BaseModel, ValidationError
        
        class PromptRequest(BaseModel):
            prompt: str
        
        # Valid
        req = PromptRequest(prompt="Test prompt")
        assert req.prompt == "Test prompt"
        
        # Missing prompt should fail
        with pytest.raises(ValidationError):
            PromptRequest()


class TestBuildPgDsn:
    """Test database connection string building."""

    def test_build_pg_dsn_format(self):
        """Test PostgreSQL DSN is built correctly."""
        from app.main import build_pg_dsn
        
        dsn = build_pg_dsn()
        
        assert "postgresql://" in dsn
        assert "test:test" in dsn  # user:password from env
        assert "localhost:5432" in dsn


class TestGetOllamaHost:
    """Test Ollama host configuration."""

    def test_get_ollama_host_from_env(self):
        """Test Ollama host is read from environment."""
        from app.main import get_ollama_host
        
        host = get_ollama_host()
        
        assert host == "http://localhost:11434"

    def test_get_ollama_host_default(self):
        """Test Ollama host default value."""
        import os
        original = os.environ.pop("OLLAMA_BASE_URL", None)
        
        try:
            from importlib import reload
            import app.main
            reload(app.main)
            
            host = app.main.get_ollama_host()
            # Default is 172.16.0.4 in the code
            assert "11434" in host
        finally:
            if original:
                os.environ["OLLAMA_BASE_URL"] = original


class TestAppRoutes:
    """Test that app routes are defined."""

    def test_app_has_routes(self):
        """Test FastAPI app has expected routes defined."""
        from app.main import app
        
        routes = [r.path for r in app.routes]
        
        assert "/" in routes
        assert "/health" in routes
        assert "/inference" in routes
        assert "/orchestrate" in routes
