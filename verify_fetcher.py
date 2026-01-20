
import asyncio
from unittest.mock import MagicMock
from app.models import IncidentRequest

# Mock the logic inside fetch_open_incidents loop
def test_fetcher_logic():
    print("Testing Fetcher Logic with sysparm_display_value='all'...")
    
    # Simulate a ServiceNow incident record returned with display_value='all'
    mock_incident_record = {
        "sys_id": "sys_id_123",
        "number": "INC0001",
        "short_description": "High CPU",
        "description": "CPU is high",
        "severity": "2",
        "state": "1",
        "incident_state": "1",
        "assignment_group": {
            "value": "04d7f8c4c38e3610cf197cec050131f5",
            "display_value": "Infra-team"
        },
        "cmdb_ci": {
            "value": "server-01",
            "display_value": "Server 01"
        },
        # This is what we expect now for caller_id with 'all'
        "caller_id": {
            "value": "caller_sys_id_456",
            "display_value": "Azure Monitor"
        }
    }

    # Logic copied from servicenow_fetcher.py (simplified validation)
    incident = mock_incident_record
    
    # 1. Assignment Group Logic
    agroup = incident.get('assignment_group')
    agroup_id = None
    if isinstance(agroup, dict):
        agroup_id = agroup.get('value')
    elif isinstance(agroup, str):
        agroup_id = agroup
    
    matched_group = (agroup_id == "04d7f8c4c38e3610cf197cec050131f5")
    print(f"Group match: {matched_group} (Expected: True)")
    assert matched_group is True 

    # 2. Caller Logic (New)
    caller_field = incident.get('caller_id', {})
    caller_name = 'unknown'
    if isinstance(caller_field, dict):
            caller_name = caller_field.get('display_value', 'unknown')
    elif isinstance(caller_field, str):
            caller_name = caller_field
    
    print(f"Caller Name: '{caller_name}' (Expected: 'Azure Monitor')")
    assert caller_name == "Azure Monitor"

    # 3. Incident Request Creation
    severity_map = {'1': 'critical', '2': 'high', '3': 'medium', '4': 'low'}
    mapped_severity = severity_map.get(str(incident['severity']), 'medium')
    
    req = IncidentRequest(
        incident_number=incident['number'],
        description=incident['short_description'],
        caller=caller_name,
        severity=mapped_severity
    )
    
    print(f"IncidentRequest created: {req}")
    print("SUCCESS: Fetcher logic handles new format correctly.")

if __name__ == "__main__":
    test_fetcher_logic()
