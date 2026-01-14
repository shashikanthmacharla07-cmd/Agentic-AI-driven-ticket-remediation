# AWX Playbooks for Incident Remediation

This directory contains Ansible playbooks that can be imported into AWX/Tower to automate incident remediation.

## Available Playbooks

### 1. restart-service.yml
**Purpose**: Restart an unresponsive service
**Variables**:
- `incident_number`: Incident ID (auto-populated)
- `incident_system`: Service name to restart
- `incident_severity`: Severity level
**Performs**:
- Checks if service exists
- Restarts the service
- Verifies service is running
- Performs health checks

### 2. restart-app.yml
**Purpose**: Restart the main application
**Variables**:
- `incident_number`: Incident ID
- `incident_system`: Application name
**Performs**:
- Stops running application
- Restarts application (systemd/docker/native)
- Waits for application readiness
- Validates health endpoint

### 3. restart-database.yml
**Purpose**: Restart database service
**Variables**:
- `incident_number`: Incident ID
**Performs**:
- Detects if database is containerized
- Restarts database container or service
- Waits for port readiness
- Tests database connection

### 4. cleanup-disk.yml
**Purpose**: Free up disk space
**Variables**:
- `incident_number`: Incident ID
**Performs**:
- Archives old logs
- Cleans Docker resources
- Clears pip/system caches
- Removes old temp files
- Reports before/after disk usage

## Setting Up AWX Job Templates

### Step 1: Create SCM Project (Git)
1. In AWX, go to **Projects** → **Create**
2. Name: `orchestrator-playbooks`
3. SCM Type: `Git`
4. SCM URL: `https://github.com/yourusername/orchestrator.git` (or local path)
5. SCM Branch: `main`
6. Save

### Step 2: Create Job Templates
Create one job template for each playbook:

#### Template 1: restart-service
- **Name**: `restart-service`
- **Project**: `orchestrator-playbooks`
- **Playbook**: `playbooks/restart-service.yml`
- **Inventory**: `Localhost` or your inventory
- **Credentials**: Machine credentials
- **Variables** (prompt on launch):
  ```yaml
  incident_number: ""
  incident_system: ""
  incident_severity: ""
  ```
- **Save** → Note the **Job Template ID** (e.g., 7)

#### Template 2: restart-app
- **Name**: `restart-app`
- **Project**: `orchestrator-playbooks`
- **Playbook**: `playbooks/restart-app.yml`
- **Inventory**: `Localhost`
- **Credentials**: Machine credentials
- **Save** → Note the **Job Template ID** (e.g., 8)

#### Template 3: restart-database
- **Name**: `restart-database`
- **Project**: `orchestrator-playbooks`
- **Playbook**: `playbooks/restart-database.yml`
- **Inventory**: `Localhost`
- **Credentials**: Machine credentials
- **Save** → Note the **Job Template ID** (e.g., 9)

#### Template 4: cleanup-disk
- **Name**: `cleanup-disk`
- **Project**: `orchestrator-playbooks`
- **Playbook**: `playbooks/cleanup-disk.yml`
- **Inventory**: `Localhost`
- **Credentials**: Machine credentials
- **Save** → Note the **Job Template ID** (e.g., 10)

### Step 3: Update Orchestrator Planner Mapping
Update `app/agents/planner.py` with your actual job template IDs:

```python
playbook_mapping = {
    "server_down": {"id": "7", "name": "restart-service", ...},
    "database_down": {"id": "9", "name": "restart-database", ...},
    "application_crash": {"id": "8", "name": "restart-app", ...},
    "disk_full": {"id": "10", "name": "cleanup-disk", ...},
}
```

### Step 4: Configure AWX Authentication
Ensure the orchestrator has valid AWX credentials:

**.env**:
```
AWX_BASE_URL=http://10.0.1.5:30080
AWX_TOKEN=<your-awx-token>
```

Get your token from AWX: **Settings** → **Users** → **Select User** → **Tokens** → **Create**

## Testing

### Test from Orchestrator
```bash
curl -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_number": "INC-TEST001",
    "description": "Test database connection failure",
    "system": "postgres",
    "severity": "high"
  }'
```

Expected response:
```json
{
  "status": "partial",
  "incident": "INC-TEST001",
  "job_id": "42"
}
```

### Monitor Job in AWX
Go to AWX → **Jobs** → Search for the job ID → Watch execution in real-time

## Variable Passing

The orchestrator automatically passes incident context to playbooks:
```yaml
incident_number: "INC-AF2DBBDE"
incident_description: "Database connection failed"
incident_system: "postgres"
incident_severity: "high"
classification_category: "database_down"
plan_prechecks: ["Check connectivity to postgres", "Verify incident classification"]
```

Access in playbooks with `{{ variable_name }}`

## Customization

### Add New Playbook
1. Create `playbooks/my-remediation.yml`
2. Use standard variable names for incident context
3. Create AWX job template pointing to it
4. Add mapping in `app/agents/planner.py`
5. Redeploy orchestrator

### Modify Existing Playbook
Edit `.yml` file, commit to Git, and AWX will auto-sync (if sync on launch is enabled)

## Troubleshooting

- **Job fails to launch**: Check AWX token, base URL, and job template ID exists
- **Variables not passed**: Verify playbook uses `{{ variable_name }}` syntax
- **Job template not found**: Verify ID is correct in planner mapping
- **Task failures**: Check playbook syntax and permissions (systemd restart requires sudo)

## References

- [Ansible Playbook Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)
- [AWX API Documentation](https://docs.ansible.com/automation-platform/latest/html/userguide/api.html)
- [AWX Job Templates](https://docs.ansible.com/automation-platform/latest/html/userguide/job_templates.html)
