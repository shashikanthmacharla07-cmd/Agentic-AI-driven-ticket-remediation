
def test_sys_id_extraction():
    print("Testing sys_id extraction with sysparm_display_value='all'...")
    
    # Simulate a ServiceNow incident record returned with display_value='all'
    incident = {
        "sys_id": {
            "value": "sys_123",
            "display_value": "SYS123"
        },
        "number": "INC001"
    }

    # Current flawed logic in fetcher loop (conceptually)
    processed_incidents = set()
    
    try:
        sys_id = incident.get('sys_id')
        print(f"Extracted sys_id: {sys_id} (Type: {type(sys_id)})")
        
        # This should fail if sys_id is a dict
        if sys_id in processed_incidents:
            pass
        processed_incidents.add(sys_id)
        
    except TypeError as e:
        print(f"FAILURE: Caught expected error: {e}")
        if "unhashable type: 'dict'" in str(e):
            print("Confirmed: sys_id is a dict and cannot be added to a set.")
            return

    print("Unexpected SUCCESS: Did not get TypeError.")

if __name__ == "__main__":
    test_sys_id_extraction()
