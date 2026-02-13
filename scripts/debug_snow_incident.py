
import asyncio
import os
from app.clients.servicenow_client import ServiceNowClient

async def debug_incident():
    url = os.getenv("SNOW_URL")
    user = os.getenv("SNOW_USER")
    password = os.getenv("SNOW_PASS")
    
    if not url or not user or not password:
        print("Missing SNOW credentials")
        return

    client = ServiceNowClient(url, user, password)
    
    incident_number = "INC0010048"
    print(f"Fetching details for {incident_number}...")
    
    incidents = await client.query_incidents(f"number={incident_number}")
    
    if incidents:
        inc = incidents[0]
        print(f"Number: {inc.get('number')}")
        print(f"State: {inc.get('state')}")
        print(f"Incident State: {inc.get('incident_state')}")
        print(f"Assignment Group: {inc.get('assignment_group')}")
        print(f"Short Description: {inc.get('short_description')}")
    else:
        print("Incident not found in ServiceNow")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(debug_incident())
