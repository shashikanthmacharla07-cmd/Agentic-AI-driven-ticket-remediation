import asyncio
import os
import sys
from unittest.mock import MagicMock
from app.agents.planner import PlannerAgent
from app.models import PipelineContext, Incident, Classification
from app.data.repositories import PlanRepository

# Mock data
PLAYBOOKS = [
    {"id": 1, "name": "Linux Disk Cleanup", "description": "Cleanup disk space on Linux servers"},
    {"id": 2, "name": "Windows Disk Cleanup", "description": "Cleanup disk space on Windows servers"},
    {"id": 3, "name": "Restart Service", "description": "Restart generic service"},
]

async def test_planner_os_filtering():
    print("--- Testing Planner OS Filtering ---")
    
    # Setup
    repo = MagicMock(spec=PlanRepository)
    repo.upsert = MagicMock(return_value=None)
    
    awx = MagicMock()
    planner = PlannerAgent(repo, awx)
    
    print("Testing _get_playbook_for_classification for Windows...")
    match = planner._get_playbook_for_classification("disk_full", PLAYBOOKS, detected_os="windows")
    if match and match['id'] == 2:
        print("✅ Correctly matched Windows playbook for Windows OS")
    else:
        print(f"❌ Failed: matched {match}")

    print("Testing _get_playbook_for_classification for Linux...")
    match = planner._get_playbook_for_classification("disk_full", PLAYBOOKS, detected_os="linux")
    if match and match['id'] == 1:
        print("✅ Correctly matched Linux playbook for Linux OS")
    else:
        print(f"❌ Failed: matched {match}")

    print("Testing Cross-OS rejection (Linux playbook on Windows)...")
    # Only provide Linux playbook
    linux_only = [p for p in PLAYBOOKS if p['id'] == 1]
    match = planner._get_playbook_for_classification("disk_full", linux_only, detected_os="windows")
    if match is None:
        print("✅ Correctly rejected Linux playbook containing 'Linux' in name for Windows OS")
    else:
        print(f"❌ Failed: Should have rejected but matched {match}. Make sure PlannerAgent update is applied.")

if __name__ == "__main__":
    asyncio.run(test_planner_os_filtering())
