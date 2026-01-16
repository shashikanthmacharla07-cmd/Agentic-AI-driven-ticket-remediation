# app/clients/servicenow_client.py
from typing import Any, Dict, Optional
import httpx

class ServiceNowClient:
    """
    Async client for ServiceNow Incident API.
    - Auth: Token or Basic (depending on your setup)
    - Base URL example: https://instance.service-now.com
    """

    def __init__(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
    ):
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        auth = None
        if self.username and self.password and not self.token:
            auth = (self.username, self.password)

        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            verify=self.verify_ssl,
            auth=auth,
        )

    # ----------------------------
    # Incident operations
    # ----------------------------
    async def get_incident(self, number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch incident details by number.
        """
        async with self._client() as client:
            resp = await client.get(f"api/now/table/incident", params={"number": number})
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", [])
            return results[0] if results else None

    async def query_incidents(self, query: str = "", limit: int = 100) -> list:
        """
        Query incidents with optional filter.
        query: ServiceNow query string (e.g., "state=1^ORstate=2")
        Returns list of incident dictionaries
        """
        try:
            params = {
                "sysparm_limit": limit,
                "sysparm_query": query if query else "stateIN1,2",  # Default: New or In Progress
                "sysparm_exclude_reference_link": "true",
            }
            async with self._client() as client:
                resp = await client.get(f"api/now/table/incident", params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            print(f"Error querying ServiceNow incidents: {e}")
            return []

    async def update_incident(self, number: str, work_notes: str, resolution_summary: str) -> bool:
        """
        Update incident with closure notes and resolution summary.
        Uses sys_id for PATCH endpoint as required by ServiceNow API.
        """
        # First, get sys_id for the incident number
        sys_id = None
        try:
            incident = await self.get_incident(number)
            if incident:
                sys_id = incident.get("sys_id")
        except Exception as e:
            print(f"Failed to get sys_id for incident {number}: {e}")
        if not sys_id:
            print(f"Cannot update incident {number}: sys_id not found.")
            return False
        payload = {
            "work_notes": work_notes,
            "close_notes": resolution_summary,
            "close_code": "Resolved by Agentic AI driven Incident Remediation",
            "state": "7",  # Closed
        }
        async with self._client() as client:
            resp = await client.patch(f"api/now/table/incident/{sys_id}", json=payload)
            if resp.status_code not in (200, 204):
                print(f"Failed to update ServiceNow incident {number}. Status: {resp.status_code}, Response: {resp.text}")
            resp.raise_for_status()
            return resp.status_code in (200, 204)

    async def add_work_notes(self, number: str, notes: str) -> bool:
        """
        Append work notes to an incident without closing it.
        """
        # First, get sys_id for the incident number
        sys_id = None
        try:
            incident = await self.get_incident(number)
            if incident:
                sys_id = incident.get("sys_id")
        except Exception as e:
            print(f"Failed to get sys_id for incident {number}: {e}")
        
        if not sys_id:
             print(f"Cannot add work notes to incident {number}: sys_id not found.")
             return False

        payload = {"work_notes": notes}
        async with self._client() as client:
            resp = await client.patch(f"api/now/table/incident/{sys_id}", json=payload)
            if resp.status_code not in (200, 204):
                print(f"Failed to add work notes to {number}. Status: {resp.status_code}, Response: {resp.text}")
            resp.raise_for_status()
            return resp.status_code in (200, 204)

    # ----------------------------
    # Health / utility
    # ----------------------------
    async def ping(self) -> bool:
        """
        Basic health check: attempts to access API root.
        """
        async with self._client() as client:
            resp = await client.get("api/now/")
            return resp.status_code == 200

