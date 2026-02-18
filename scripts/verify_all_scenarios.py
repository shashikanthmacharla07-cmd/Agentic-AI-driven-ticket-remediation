
import asyncio
import os
from app.agents.classifier import ClassifierAgent
from app.agents.planner import PlannerAgent
from app.models import PipelineContext, Incident, Classification
from app.clients.awx_client import AWXClient

# Mock AWX Client
class MockAWXClient(AWXClient):
    def __init__(self):
        pass

async def verify_services():
    print("--- Starting Comprehensive Verification ---")
    
    # Setup Agents
    classifier = ClassifierAgent(repo=None)
    planner = PlannerAgent(repo=None, awx_client=MockAWXClient())
    
    # Test Scenarios
    scenarios = [
        {
            "name": "Service Down",
            "desc": "web service down on lin-us-poc-01", 
            "expected_label": "service_down",
            "expected_playbook": "linux-start-webservice"
        },
        {
            "name": "Disk Full",
            "desc": "var file system full on lin-us-poc-01",
            "expected_label": "var_filesystem_full", # or disk_full
            "expected_playbook": "linux-var-filesystem-cleanup"
        },
        {
            "name": "CPU High",
            "desc": "high cpu utilization on server01",
            "expected_label": "high_cpu",
            "expected_playbook": "linux-cpu-cleanup"
        },
        {
            "name": "Memory High",
            "desc": "memory usage critical on database_vm",
            "expected_label": "high_memory",
            "expected_playbook": "linux-high-memory-cleanup"
        },
        {
            "name": "Create User",
            "desc": "please create user john.doe",
            "expected_label": "create_user",
            "expected_playbook": "linux_create_user"
        }
    ]
    
    # Mock Playbooks
    playbooks = [
        {'id': 10, 'name': 'linux-cpu-cleanup', 'description': 'Identifies and terminates the top CPU consuming processes on linux servers'},
        {'id': 12, 'name': 'linux_create_user', 'description': 'this will create a user in linux'},
        {'id': 11, 'name': 'linux-high-memory-cleanup', 'description': 'this terminates or kill high consuming memory processes on linux'},
        {'id': 13, 'name': 'linux-start-webservice', 'description': 'this templates starts the web service on linux'},
        {'id': 9, 'name': 'linux-var-filesystem-cleanup', 'description': 'this templates free up the var filesystem full incidents'}
    ]
    
    results = []

    for sc in scenarios:
        print(f"\n--- Testing Scenario: {sc['name']} ---")
        incident = Incident(
            number="TEST001",
            short_description=sc["desc"],
            description=sc["desc"],
            service="orchestrator",
            severity="P3",
            source="servicenow",
            resource_id="lin-us-poc-01"
        )
        ctx = PipelineContext(incident=incident)
        
        # 1. Run Classifier
        try:
            ctx = await classifier.run(ctx, playbooks=playbooks)
            print(f"Classifier Intent: {ctx.classification.intent}")
            print(f"Classifier Labels: {ctx.classification.labels}")
            
            # Check Label (loose match)
            label_match = any(sc["expected_label"] in l for l in ctx.classification.labels)
            if not label_match:
                 print(f"FAILED CLASSIFICATION: Expected matching '{sc['expected_label']}' in {ctx.classification.labels}")
        except Exception as e:
            print(f"Classifier Error: {e}")
            results.append((sc['name'], "Classifier Error"))
            continue

        # 2. Run Planner
        try:
            ctx = await planner.run(ctx, playbooks=playbooks)
            if ctx.plan:
                print(f"Planned Playbook: {ctx.plan.playbook_name}")
                if ctx.plan.playbook_name == sc["expected_playbook"]:
                    print("SUCCESS: Correct playbook selected.")
                    results.append((sc['name'], "PASS"))
                else:
                    print(f"FAILED PLAN: Expected '{sc['expected_playbook']}', got '{ctx.plan.playbook_name}'")
                    results.append((sc['name'], "FAIL"))
            else:
                 print("FAILED PLAN: No plan created")
                 results.append((sc['name'], "FAIL - No Plan"))
        except Exception as e:
            print(f"Planner Error: {e}")
            results.append((sc['name'], "Planner Error"))

    print("\n--- Final Results ---")
    for name, result in results:
        print(f"{name}: {result}")

if __name__ == "__main__":
    asyncio.run(verify_services())
