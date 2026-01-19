# System Architecture

## Overview
The solution is an **Intelligent Incident Remediation Orchestrator** driven by LLMs. It automates the lifecycle of infrastructure incidents by fetching them from ServiceNow, planning remediation, executing Ansible playbooks via AWX, and validating the results.

## Architecture Diagram

```mermaid
graph TD
    subgraph External Systems
        SNOW[ServiceNow Instance]
        AWX[Ansible AWX]
        OLLAMA[Ollama LLM Service]
    end

    subgraph Orchestrator Application
        subgraph Core Components
            API[FastAPI Main]
            SCHED[Incident Scheduler]
            ORCH[Orchestration Agent]
            FETCHER[ServiceNow Fetcher]
        end

        subgraph Agents
            INTAKE[Intake Agent]
            CLASS[Classifier Agent]
            PLAN[Planner Agent]
            EXEC[Executor Agent]
            VALID[Validator Agent]
            CLOSE[Closure Agent]
        end

        subgraph Data Layer
            REPO[Repositories]
            DB[(PostgreSQL)]
        end
    end

    %% Data Flow
    SCHED -- "Polls (every 30s)" --> FETCHER
    FETCHER -- "Fetch Incidents" --> SNOW
    FETCHER -- "Returns Incidents" --> SCHED
    SCHED -- "Triggers" --> ORCH

    %% Agent orchestration
    ORCH -- "1. Contextualize" --> INTAKE
    ORCH -- "2. Analyze" --> CLASS
    ORCH -- "3. Select Strategy" --> PLAN
    ORCH -- "4. Execute" --> EXEC
    ORCH -- "5. Verify" --> VALID
    ORCH -- "6. Resolve" --> CLOSE

    %% Agent dependencies
    INTAKE -. "Parse & Normalize" .-> OLLAMA
    CLASS -. "Classify" .-> OLLAMA
    PLAN -. "Select Playbook" .-> OLLAMA
    PLAN -- "List Templates" --> AWX
    EXEC -- "Launch Job" --> AWX
    VALID -. "Evaluate Success" .-> OLLAMA
    CLOSE -. "Summarize" .-> OLLAMA
    CLOSE -- "Update Ticket" --> SNOW

    %% Persistence
    INTAKE --> REPO
    CLASS --> REPO
    PLAN --> REPO
    EXEC --> REPO
    VALID --> REPO
    CLOSE --> REPO
    REPO -- "Persist State" --> DB
```

## Component Description

### Core Components
- **Incident Scheduler**: Periodically polls ServiceNow for new active incidents.
- **ServiceNow Fetcher**: Adapter to communicate with ServiceNow API.
- **Orchestration Agent**: The central controller that manages the sequential execution of the agentic pipeline.

### Agents
1.  **Intake Agent**: structuring the raw incident data into a clean, canonical format.
2.  **Classifier Agent**: Analyzes the incident to determine severity, category, and eligibility for auto-remediation.
3.  **Planner Agent**: matches the incident to the most appropriate Ansible playbook template available in AWX.
4.  **Executor Agent**: Triggers the selected playbook in AWX and monitors its execution status.
5.  **Validator Agent**: Analyzes execution logs and telemetry to determine if the remediation was successful.
6.  **Closure Agent**: Updates the ServiceNow ticket with execution notes, resolution summary, and closes it if successful.

### Infrastructure
- **PostgreSQL**: Stores the state of every orchestration (Incidents, Plans, Executions, Validations).
- **Ollama**: Provides local LLM inference for agent decision-making.
- **Ansible AWX**: The execution engine for infrastructure changes.
