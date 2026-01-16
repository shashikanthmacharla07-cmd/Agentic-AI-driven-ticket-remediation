# PlaybookSelectionValidator.py
def validate_playbook_selection(plan_data: dict, labels: list, known_playbooks: dict) -> dict:
    """
    Ensure the LLM-selected playbook matches incident labels.
    If mismatch, override with correct mapping.
    """
    labels = [lbl.lower() for lbl in labels]

    # CPU incidents → enforce CPU playbook
    if "high_cpu" in labels:
        cpu_pb = known_playbooks.get("high_cpu")
        if plan_data.get("playbook_name") != cpu_pb["name"]:
            print(f"[Validator] Override: Incident label 'high_cpu' requires {cpu_pb['name']}")
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
