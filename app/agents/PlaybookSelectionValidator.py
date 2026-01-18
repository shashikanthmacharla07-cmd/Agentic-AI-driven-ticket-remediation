# PlaybookSelectionValidator.py
def validate_playbook_selection(plan_data: dict, labels: list, known_playbooks: dict, os_type: str = None) -> dict:
    """
    Ensure the LLM-selected playbook matches incident labels.
    If mismatch, override with correct mapping.
    """
    labels = [lbl.lower() for lbl in labels]

    # CPU incidents → enforce CPU playbook
    if "high_cpu" in labels:
        # Select playbook based on OS
        target_key = "high_cpu" # default to Linux/Generic
        if os_type and os_type.lower() == "windows":
             target_key = "windows_high_cpu"
        
        # Fallback if windows key missing but windows requested
        if target_key not in known_playbooks:
            print(f"[Validator] Warning: {target_key} not in known_playbooks, falling back to high_cpu")
            target_key = "high_cpu"

        cpu_pb = known_playbooks.get(target_key)
        if cpu_pb and plan_data.get("playbook_name") != cpu_pb["name"]:
            print(f"[Validator] Override: Incident label 'high_cpu' (OS: {os_type}) requires {cpu_pb['name']}")
            plan_data["playbook_id"] = str(cpu_pb["id"])
            plan_data["playbook_name"] = cpu_pb["name"]
            plan_data["description"] = cpu_pb["description"]

    # Disk/storage incidents → enforce filesystem cleanup
    if any(lbl in labels for lbl in [
        "disk_full", "storage_full", "var_full", "tmp_full", "fs_full", "file_system_full"
    ]):
        disk_pb = known_playbooks.get("disk_full")
        if plan_data.get("playbook_name") != disk_pb["name"]:
            print(f"[Validator] Override: Incident label 'disk/storage' requires {disk_pb['name']}")
            plan_data["playbook_id"] = str(disk_pb["id"])
            plan_data["playbook_name"] = disk_pb["name"]
            plan_data["description"] = disk_pb["description"]

    # Severity override: P1 incidents → force human-only eligibility
    # Check if plan_data is a dict (it should be)
    if plan_data.get("eligibility") == "auto":
        if "severity" in labels or "p1" in labels:
            print("[Validator] Override: P1 severity requires human-only eligibility")
            plan_data["eligibility"] = "human-only"

    return plan_data
