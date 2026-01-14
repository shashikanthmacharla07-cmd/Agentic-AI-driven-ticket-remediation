
import asyncio
from unittest.mock import MagicMock
from app.agents.planner import PlannerAgent
from app.models import PipelineContext, Classification, Incident

async def test_mapping():
    planner = PlannerAgent(repo=None, awx_client=None)
    
    test_cases = [
        ("var_full", "10"),
        ("tmp_full", "10"),
        ("disk_full", "10"),
        ("storage_issue", "10"),
        ("critical_disk_space", "10"),
        ("high_memory", "7"),  # Fixed mapping
        ("high_cpu", "9"),
        ("random_label_with_disk", "10"), # Catch-all
        ("filesystem_problem", "10"), # Catch-all
    ]
    
    print("Testing playbook mapping logic...")
    all_passed = True
    for label, expected_id in test_cases:
        pb = planner._get_playbook_for_classification(label)
        if pb["id"] == expected_id:
            print(f"✅ Label '{label}' -> Playbook ID {pb['id']} (Expected {expected_id})")
        else:
            print(f"❌ Label '{label}' -> Playbook ID {pb['id']} (Expected {expected_id})")
            all_passed = False
            
    if all_passed:
        print("\nAll mapping tests passed!")
    else:
        print("\nSome mapping tests failed.")

if __name__ == "__main__":
    asyncio.run(test_mapping())
