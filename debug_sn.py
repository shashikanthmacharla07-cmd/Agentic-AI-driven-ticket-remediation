import asyncio
import os
from app.clients.servicenow_client import ServiceNowClient
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    client = ServiceNowClient(
        base_url=os.getenv("SNOW_URL"),
        username=os.getenv("SNOW_USER"),
        password=os.getenv("SNOW_PASS")
    )
    
    number = "INC0010134"
    print(f"Testing ServiceNow update for {number}...")
    
    # Try 1: Just work notes
    print("\nTry 1: Just work_notes")
    incident = await client.get_incident(number)
    if not incident:
        print("Incident not found")
        return
    
    sys_id = incident["sys_id"]
    payload_1 = {"work_notes": "Test work note from orchestrator debug script."}
    
    async with client._client() as hclient:
        resp = await hclient.patch(f"api/now/table/incident/{sys_id}", json=payload_1)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
    # Try 2: Work notes + Resolution state
    print("\nTry 2: work_notes + state 6 (Resolved)")
    payload_2 = {
        "work_notes": "Automated resolution test.",
        "close_notes": "Resolved via debug script.",
        "close_code": "Solved (Permanently)",
        "state": "6"
    }
    
    async with client._client() as hclient:
        resp = await hclient.patch(f"api/now/table/incident/{sys_id}", json=payload_2)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    asyncio.run(main())
