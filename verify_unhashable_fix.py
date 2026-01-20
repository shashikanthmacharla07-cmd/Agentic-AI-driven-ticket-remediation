
def test_sys_id_extraction_fixed():
    print("Testing Fixed sys_id extraction with sysparm_display_value='all'...")
    
    incident = {
        "sys_id": {
            "value": "sys_123",
            "display_value": "SYS123"
        },
        "number": "INC001"
    }

    processed_incidents = set()
    
    # Logic copied from the FIXED servicenow_fetcher.py
    sys_id_field = incident.get('sys_id')
    sys_id = None
    if isinstance(sys_id_field, dict):
        sys_id = sys_id_field.get('value')
    else:
        sys_id = sys_id_field
        
    print(f"Extracted sys_id: {sys_id} (Type: {type(sys_id)})")
    
    try:
        # This should SUCCEED now
        if sys_id in processed_incidents:
            pass
        processed_incidents.add(sys_id)
        print("SUCCESS: sys_id added to set.")
    except TypeError as e:
        print(f"FAILURE: Caught error: {e}")

if __name__ == "__main__":
    test_sys_id_extraction_fixed()
