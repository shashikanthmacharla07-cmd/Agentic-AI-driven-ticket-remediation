
def test_state_logic_fixed():
    print("Testing Fixed State Logic with sysparm_display_value='all'...")
    
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

    # Fixed Logic copied from servicenow_fetcher.py
    def get_val(field):
        if isinstance(field, dict):
            return str(field.get('value', '')).strip()
        return str(field).strip()

    state_val = get_val(incident.get('state', ''))
    incident_state_val = get_val(incident.get('incident_state', ''))
    
    print(f"Extracted state_val: '{state_val}'")
    
    is_new = (state_val == '1' or incident_state_val == '1')
    
    print(f"Is New? {is_new}")
    
    if is_new:
        print("SUCCESS: State '1' (New) was detected correctly!")
    else:
        print("FAILURE: State '1' (New) was NOT detected.")

if __name__ == "__main__":
    test_state_logic_fixed()
