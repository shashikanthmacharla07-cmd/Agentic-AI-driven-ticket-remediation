import os
import httpx

SNOW_URL = os.getenv("SNOW_URL")
SNOW_USER = os.getenv("SNOW_USER")
SNOW_PASS = os.getenv("SNOW_PASS")
SNOW_TOKEN = os.getenv("SNOW_TOKEN")  # optional for MFA/token auth

class ServiceNowClient:
    def __init__(self):
        if not SNOW_URL:
            raise ValueError("SNOW_URL must be set")
        # Prefer token if available
        if SNOW_TOKEN:
            self.headers = {
                "Authorization": f"Bearer {SNOW_TOKEN}",
                "Content-Type": "application/json",
            }
            self.auth = None
        else:
            if not SNOW_USER or not SNOW_PASS:
                raise ValueError("SNOW_USER and SNOW_PASS must be set if SNOW_TOKEN is not used")
            self.headers = {"Content-Type": "application/json"}
            self.auth = (SNOW_USER, SNOW_PASS)

    async def create_incident(self, payload: dict) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{SNOW_URL}/api/now/table/incident",
                json=payload,
                headers=self.headers,
                auth=self.auth,
            )
            r.raise_for_status()
            return r.json().get("result", r.json())

    async def update_incident(self, sys_id: str, payload: dict) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{SNOW_URL}/api/now/table/incident/{sys_id}",
                json=payload,
                headers=self.headers,
                auth=self.auth,
            )
            r.raise_for_status()
            return r.json().get("result", r.json())

    async def add_work_note(self, sys_id: str, note: str) -> dict:
        return await self.update_incident(sys_id, {"work_notes": note})

