import os
import asyncio
from mcp.server.fastmcp import FastMCP
from app.clients.servicenow_client import ServiceNowClient

# Initialize FastMCP server
mcp = FastMCP("itsm-server")

# Configuration
SNOW_URL = os.getenv("SNOW_URL")
SNOW_USER = os.getenv("SNOW_USER")
SNOW_PASS = os.getenv("SNOW_PASS")

if not SNOW_URL or not SNOW_USER or not SNOW_PASS:
    print("Warning: ServiceNow credentials not fully set in environment variables.")

# Initialize client
client = ServiceNowClient(
    base_url=SNOW_URL or "https://dev266373.service-now.com",
    username=SNOW_USER,
    password=SNOW_PASS
)

@mcp.tool()
async def query_incidents(query: str = "", limit: int = 10) -> str:
    """
    Fetch open incidents from ServiceNow with an optional filter.
    query: ServiceNow query string (e.g., "state=1^ORstate=2")
    limit: Max number of incidents to return (default 10)
    """
    try:
        incidents = await client.query_incidents(query=query, limit=limit)
        return str(incidents)
    except Exception as e:
        return f"Error querying incidents: {str(e)}"

@mcp.tool()
async def get_incident(number: str) -> str:
    """
    Get detailed information for a specific incident by its number.
    number: Incident number (e.g., INC0010015)
    """
    try:
        incident = await client.get_incident(number=number)
        if incident:
            return str(incident)
        return f"Incident {number} not found."
    except Exception as e:
        return f"Error fetching incident {number}: {str(e)}"

@mcp.tool()
async def update_incident(number: str, work_notes: str, resolution_summary: str) -> str:
    """
    Close an incident with a resolution summary and work notes.
    number: Incident number (e.g., INC0010015)
    work_notes: Internal notes about the work done
    resolution_summary: Public facing resolution summary
    """
    try:
        success = await client.update_incident(number, work_notes, resolution_summary)
        if success:
            return f"Successfully closed incident {number}."
        return f"Failed to close incident {number}."
    except Exception as e:
        return f"Error updating incident {number}: {str(e)}"

@mcp.tool()
async def add_work_notes(number: str, notes: str) -> str:
    """
    Append work notes to an incident without closing it.
    number: Incident number (e.g., INC0010015)
    notes: The notes to append
    """
    try:
        success = await client.add_work_notes(number, notes)
        if success:
            return f"Successfully added notes to {number}."
        return f"Failed to add notes to {number}."
    except Exception as e:
        return f"Error adding notes to incident {number}: {str(e)}"

@mcp.tool()
async def ping() -> str:
    """
    Check connectivity to the ServiceNow instance.
    """
    try:
        is_alive = await client.ping()
        return "ServiceNow is reachable." if is_alive else "ServiceNow is unreachable."
    except Exception as e:
        return f"Error pinging ServiceNow: {str(e)}"

if __name__ == "__main__":
    mcp.run()
