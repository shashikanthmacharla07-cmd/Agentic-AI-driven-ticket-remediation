import os
import asyncio
import json
from mcp.server.fastmcp import FastMCP
from app.clients.awx_client import AWXClient

# Initialize FastMCP server
mcp = FastMCP("automation-server")

# Configuration
AWX_URL = os.getenv("AWX_URL")
AWX_TOKEN = os.getenv("AWX_TOKEN")

if not AWX_URL or not AWX_TOKEN:
    print("Warning: AWX credentials not fully set in environment variables.")

# Initialize client
client = AWXClient(
    base_url=AWX_URL or "http://172.18.0.4",
    token=AWX_TOKEN or ""
)

@mcp.tool()
async def list_playbooks(organization_id: int = None, force_refresh: bool = False) -> str:
    """
    List available playbooks (job templates).
    organization_id: Filter by organization ID
    force_refresh: ignore cache and fetch fresh list
    """
    try:
        templates = await client.list_job_templates(organization_id=organization_id, force_refresh=force_refresh)
        return str(templates)
    except Exception as e:
        return f"Error listing playbooks: {str(e)}"

@mcp.tool()
async def get_playbook(playbook_id: int) -> str:
    """
    Get details of a specific playbook (job template).
    playbook_id: The ID of the job template
    """
    try:
        template = await client.get_job_template(playbook_id)
        return str(template)
    except Exception as e:
        return f"Error getting playbook {playbook_id}: {str(e)}"

@mcp.tool()
async def run_playbook(playbook_id: int, extra_vars: str = "{}") -> str:
    """
    Launch a playbook execution.
    playbook_id: The ID of the job template to launch
    extra_vars: JSON string of extra variables to pass to the playbook
    """
    try:
        vars_dict = json.loads(extra_vars)
        job_id = await client.launch_job(playbook_id, extra_vars=vars_dict)
        return f"Job launched successfully. Job ID: {job_id}"
    except json.JSONDecodeError:
        return "Error: extra_vars must be a valid JSON string."
    except Exception as e:
        return f"Error launching playbook: {str(e)}"

@mcp.tool()
async def get_job_status(job_id: int) -> str:
    """
    Check the status of a running job.
    job_id: The ID of the job
    """
    try:
        status = await client.job_status(job_id)
        return f"Job {job_id} status: {status}"
    except Exception as e:
        return f"Error getting job status: {str(e)}"

@mcp.tool()
async def get_job_output(job_id: int) -> str:
    """
    Get the output logs/events of a job.
    job_id: The ID of the job
    """
    try:
        events = await client.job_events(job_id)
        return str(events)
    except Exception as e:
        return f"Error getting job output: {str(e)}"

@mcp.tool()
async def cancel_job(job_id: int) -> str:
    """
    Cancel a running job.
    job_id: The ID of the job to cancel
    """
    try:
        success = await client.cancel_job(job_id)
        if success:
            return f"Job {job_id} cancellation requested."
        return f"Failed to cancel job {job_id}."
    except Exception as e:
        return f"Error cancelling job: {str(e)}"

@mcp.tool()
async def ping() -> str:
    """
    Check connectivity to the AWX server.
    """
    try:
        is_alive = await client.ping()
        return "AWX is reachable." if is_alive else "AWX is unreachable."
    except Exception as e:
        return f"Error pinging AWX: {str(e)}"

if __name__ == "__main__":
    mcp.run()
