# tests/test_clients.py
"""
Unit tests for AWX and ServiceNow clients (with mocked HTTP).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestAWXClient:
    """Tests for AWXClient."""

    def test_awx_client_init(self):
        """Test AWXClient initialization."""
        from app.clients.awx_client import AWXClient
        client = AWXClient(base_url="http://awx.local", token="test-token")
        
        assert client.base_url == "http://awx.local/"
        assert client.token == "test-token"
        assert client.timeout == 30.0
        assert client.verify_ssl is True

    def test_awx_client_headers(self):
        """Test AWXClient headers generation."""
        from app.clients.awx_client import AWXClient
        client = AWXClient(base_url="http://awx.local", token="my-secret-token")
        
        headers = client._headers()
        
        assert headers["Authorization"] == "Bearer my-secret-token"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    def test_awx_client_url_trailing_slash(self):
        """Test AWXClient adds trailing slash to base URL."""
        from app.clients.awx_client import AWXClient
        
        client1 = AWXClient(base_url="http://awx.local", token="tok")
        client2 = AWXClient(base_url="http://awx.local/", token="tok")
        
        assert client1.base_url == "http://awx.local/"
        assert client2.base_url == "http://awx.local/"

    @pytest.mark.asyncio
    async def test_list_job_templates_caching(self):
        """Test job templates are cached."""
        from app.clients.awx_client import AWXClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Template 1", "description": "Desc 1"},
                {"id": 2, "name": "Template 2", "description": "Desc 2"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            client = AWXClient(base_url="http://awx.local", token="tok")
            
            # First call should hit the API
            result1 = await client.list_job_templates()
            
            # Second call should use cache
            result2 = await client.list_job_templates()
            
            assert result1 == result2
            assert len(result1) == 2
            assert result1[0]["name"] == "Template 1"

    @pytest.mark.asyncio
    async def test_launch_job_payload(self):
        """Test launch_job sends correct payload."""
        from app.clients.awx_client import AWXClient
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"job": 12345}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            client = AWXClient(base_url="http://awx.local", token="tok")
            extra_vars = {"incident_number": "INC001", "severity": "P2"}
            
            job_id = await client.launch_job(9, extra_vars)
            
            assert job_id == 12345
            # Verify the payload was passed
            call_args = mock_post.call_args
            assert call_args[1]["json"]["extra_vars"] == extra_vars


class TestServiceNowClient:
    """Tests for ServiceNowClient."""

    def test_servicenow_client_init_basic_auth(self):
        """Test ServiceNowClient initialization with basic auth."""
        from app.clients.servicenow_client import ServiceNowClient
        client = ServiceNowClient(
            base_url="https://instance.service-now.com",
            username="admin",
            password="secret"
        )
        
        assert client.base_url == "https://instance.service-now.com/"
        assert client.username == "admin"
        assert client.password == "secret"

    def test_servicenow_client_init_token_auth(self):
        """Test ServiceNowClient initialization with token auth."""
        from app.clients.servicenow_client import ServiceNowClient
        client = ServiceNowClient(
            base_url="https://instance.service-now.com",
            token="bearer-token"
        )
        
        headers = client._headers()
        assert headers["Authorization"] == "Bearer bearer-token"

    def test_servicenow_client_url_trailing_slash(self):
        """Test ServiceNowClient adds trailing slash to base URL."""
        from app.clients.servicenow_client import ServiceNowClient
        
        client1 = ServiceNowClient(base_url="https://snow.local", username="u", password="p")
        client2 = ServiceNowClient(base_url="https://snow.local/", username="u", password="p")
        
        assert client1.base_url == "https://snow.local/"
        assert client2.base_url == "https://snow.local/"

    @pytest.mark.asyncio
    async def test_get_incident_parses_result(self):
        """Test get_incident returns first result from array."""
        from app.clients.servicenow_client import ServiceNowClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "abc123", "number": "INC0010001", "short_description": "Test"}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            client = ServiceNowClient(
                base_url="https://snow.local",
                username="admin",
                password="pass"
            )
            
            result = await client.get_incident("INC0010001")
            
            assert result["sys_id"] == "abc123"
            assert result["number"] == "INC0010001"

    @pytest.mark.asyncio
    async def test_get_incident_returns_none_for_empty(self):
        """Test get_incident returns None when no results."""
        from app.clients.servicenow_client import ServiceNowClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            client = ServiceNowClient(
                base_url="https://snow.local",
                username="admin",
                password="pass"
            )
            
            result = await client.get_incident("INC0099999")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_query_incidents_with_filter(self):
        """Test query_incidents sends correct query parameters."""
        from app.clients.servicenow_client import ServiceNowClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            client = ServiceNowClient(
                base_url="https://snow.local",
                username="admin",
                password="pass"
            )
            
            await client.query_incidents(query="state=1", limit=10)
            
            # Verify query params were passed
            call_args = mock_get.call_args
            assert call_args[1]["params"]["sysparm_query"] == "state=1"
            assert call_args[1]["params"]["sysparm_limit"] == 10
