import asyncio
import os
from app.clients.servicenow_client import ServiceNowClient

async def main():
    base_url = os.getenv("SNOW_URL")
    username = os.getenv("SNOW_USER")
    password = os.getenv("SNOW_PASS")
    client = ServiceNowClient(base_url=base_url, username=username, password=password)
    
    print("Querying all incidents (limit 5)...")
    all_incidents = await client.query_incidents(limit=5)
    print(f"Total found: {len(all_incidents)}")
    for inc in all_incidents:
        print(f"- {inc.get('number')}: Group={inc.get('assignment_group')}, State={inc.get('state')}")

    print("\nQuerying Infra-team incidents...")
    infra_incidents = await client.query_incidents(query="assignment_group.name=Infra-team", limit=5)
    print(f"Total found: {len(infra_incidents)}")
    for inc in infra_incidents:
        print(inc)

if __name__ == "__main__":
    asyncio.run(main())
