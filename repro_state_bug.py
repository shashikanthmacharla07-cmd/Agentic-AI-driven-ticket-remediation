
def test_state_logic():
    print("Testing State Logic with sysparm_display_value='all'...")
    
    # Simulate a ServiceNow incident record returned with display_value='all'
    # 'state' is now a DICT, not a string!
    incident = {
        "number": "INC001",
        "state": {
            "value": "1",
            "display_value": "New"
        },
        "incident_state": {
             "value": "1",
             "display_value": "New"
        }
    }

    # Logic copied from servicenow_fetcher.py (failed logic)
    state_val = str(incident.get('state', '')).strip()
    incident_state_val = str(incident.get('incident_state', '')).strip()
    
    print(f"Extracted state_val: '{state_val}'")
    
    # The check in the code:
    is_new = (state_val == '1' or incident_state_val == '1')
    
    print(f"Is New? {is_new}")
    
    if not is_new:
        print("FAILURE: State '1' (New) was NOT detected because it was stringified as a dict!")
    else:
        print("SUCCESS: State detected correctly (Unexpected).")

if __name__ == "__main__":
    test_state_logic()
