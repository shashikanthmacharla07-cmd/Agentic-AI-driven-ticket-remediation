from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal
from datetime import datetime

class Incident(BaseModel):
    sys_id: Optional[str] = None
    number: Optional[str] = None
    source: str
    resource_id: str
    service: str
    severity: str
    short_description: str
    description: str
    tags: Dict = Field(default_factory=dict)
    timestamps: Dict = Field(default_factory=dict)
    context: Dict = Field(default_factory=dict)

class Classification(BaseModel):
    labels: List[str]
    confidence: float
    eligibility: Literal["auto", "human-only"]
    severity: str

class Plan(BaseModel):
    playbook_id: str
    prechecks: List[str]
    rollback_steps: List[str]
    risk_score: float
    eligibility: str

class ExecutionLog(BaseModel):
    job_id: str = "unknown"
    steps: List[Dict] = Field(default_factory=list)
    outputs: List[Dict] = Field(default_factory=list)
    status: Literal["running", "success", "successful", "failed", "error", "canceled", "timeout"] = "success"
    finished_at: Optional[str] = None

class ValidationSignals(BaseModel):
    metrics: Dict = Field(default_factory=dict)
    logs: Dict = Field(default_factory=dict)
    synthetics: Dict = Field(default_factory=dict)
    decision: Literal["success", "partial", "rollback", "escalate"]

class Closure(BaseModel):
    incident_id: str = ""
    closed_by: str = "orchestrator"
    closed_at: datetime = Field(default_factory=datetime.utcnow)
    resolution: Literal["resolved", "duplicate", "false-positive", "escalated"] = "resolved"
    notes: Optional[str] = None
    work_notes: Optional[str] = None
    resolution_summary: Optional[str] = None

class PipelineContext(BaseModel):
    incident: Optional[Incident] = None
    classification: Optional[Classification] = None
    plan: Optional[Plan] = None
    execution: Optional[ExecutionLog] = None
    validation: Optional[ValidationSignals] = None
    closure: Optional[Closure] = None

class IncidentRequest(BaseModel):
    incident_number: Optional[str] = None
    description: str
    severity: Optional[str] = None
    system: Optional[str] = None
    service: Optional[str] = None

class OrchestratorResponse(BaseModel):
    status: str
    incident: str
    job_id: Optional[str]

