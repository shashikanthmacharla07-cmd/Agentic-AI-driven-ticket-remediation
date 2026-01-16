# app/clients/awx_client.py
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import httpx
import datetime

class AWXClient:
    """
    Async client for AWX/Tower API.
    - Auth: Token-based (Bearer)
    - Base URL example: http://awx.local
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        verify_ssl: bool = True,
    ):
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._cache = {}
        self._cache_ttl = 60  # 1 minute

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            verify=self.verify_ssl,
        )

    # ----------------------------
    # Job templates / playbooks
    # ----------------------------
    async def list_job_templates(self, organization_id: Optional[int] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Returns a simplified list of job templates (playbooks) with id, name, description.
        Includes simple caching to reduce API load.
        """
        cache_key = f"list_templates_{organization_id}"
        now = datetime.datetime.utcnow()
        
        if not force_refresh and cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (now - timestamp).total_seconds() < self._cache_ttl:
                return data

        params = {}
        if organization_id is not None:
            params["organization"] = organization_id

        async with self._client() as client:
            resp = await client.get("api/v2/job_templates/", params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            processed = [
                {"id": str(jt["id"]), "name": jt["name"], "description": jt.get("description")}
                for jt in results
            ]
            self._cache[cache_key] = (processed, now)
            return processed

    async def get_job_template(self, job_template_id: int) -> Dict[str, Any]:
        async with self._client() as client:
            resp = await client.get(f"api/v2/job_templates/{job_template_id}/")
            resp.raise_for_status()
            return resp.json()

    # ----------------------------
    # Job lifecycle
    # ----------------------------
    async def launch_job(self, job_template_id: int, extra_vars: Optional[Dict[str, Any]] = None) -> int:
        """
        Launches a job from a job template. Returns the created job id.
        """
        payload = {}
        if extra_vars:
            payload["extra_vars"] = extra_vars

        async with self._client() as client:
            resp = await client.post(f"api/v2/job_templates/{job_template_id}/launch/", json=payload)
            resp.raise_for_status()
            data = resp.json()
            # AWX returns job as "job": <id> or "id"
            job_id = data.get("job") or data.get("id")
            if not job_id:
                raise RuntimeError("AWX launch response missing job id")
            return int(job_id)

    async def job_details(self, job_id: int) -> Dict[str, Any]:
        async with self._client() as client:
            resp = await client.get(f"api/v2/jobs/{job_id}/")
            resp.raise_for_status()
            return resp.json()

    async def job_status(self, job_id: int) -> str:
        details = await self.job_details(job_id)
        return details.get("status", "unknown")

    async def job_events(self, job_id: int, order_by: str = "created", page_size: int = 200) -> List[Dict[str, Any]]:
        """
        Fetches job events. You can paginate for large runs; this returns the first page ordered by creation time.
        """
        params = {"order_by": order_by, "page_size": page_size}
        async with self._client() as client:
            resp = await client.get(f"api/v2/jobs/{job_id}/events/", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])

    async def poll_job(
        self,
        job_id: int,
        poll_interval: float = 2.0,
        timeout_seconds: float = 30.0,
        collect_events: bool = True,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """
        Polls the job until it reaches a terminal state.
        Returns (status, events, finished_at_iso8601)
        Terminal statuses typically include: successful, failed, error, canceled.
        """
        start = datetime.datetime.utcnow()
        events: List[Dict[str, Any]] = []

        while True:
            status = await self.job_status(job_id)

            if collect_events:
                try:
                    events = await self.job_events(job_id)
                except Exception:
                    # Non-blocking: if events fail, continue polling status
                    pass

            if status in {"successful", "failed", "error", "canceled"}:
                # get finished_at if available
                details = await self.job_details(job_id)
                finished_at = details.get("finished")
                return status, events, finished_at

            elapsed = (datetime.datetime.utcnow() - start).total_seconds()
            if elapsed >= timeout_seconds:
                return "timeout", events, None

            await asyncio.sleep(poll_interval)

    async def cancel_job(self, job_id: int) -> bool:
        """
        Attempts to cancel a running job. Returns True if AWX accepted the cancel request.
        """
        async with self._client() as client:
            resp = await client.post(f"api/v2/jobs/{job_id}/cancel/")
            # AWX returns 202 Accepted if cancel was queued/accepted
            if resp.status_code in (200, 202):
                return True
            # Raise for other statuses
            resp.raise_for_status()
            return True

    # ----------------------------
    # Health / utility
    # ----------------------------
    async def ping(self) -> bool:
        """
        Basic health check: attempts to access API root.
        """
        async with self._client() as client:
            resp = await client.get("api/v2/")
            return resp.status_code == 200

