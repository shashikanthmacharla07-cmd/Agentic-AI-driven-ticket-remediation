from __future__ import annotations
import os
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, Plan
from app.data.repositories import PlanRepository
from app.clients.awx_client import AWXClient
from app.agents.PlaybookSelectionValidator import validate_playbook_selection



llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a remediation planner. You have access to the following AWX playbooks: {playbooks}.\n"
             "Analyze the incident and classification, then choose the most suitable playbook from the list.\n"
             "If no playbook is suitable, set playbook_id to '0' and playbook_name to 'No suitable playbook'.\n"
             "Return only JSON. Always include both playbook_id and playbook_name in your output."),
            ("user",
             "Incident: {incident}\nClassification: {classification}\n\n"
             "Return JSON with keys: playbook_id (string), playbook_name (string), prechecks (list), rollback_steps (list), risk_score (0-1), eligibility (auto or human-only)."
            )
        ])

parser = JsonOutputParser(pydantic_object=Plan)

class PlannerAgent:
    def __init__(self, repo: PlanRepository, awx_client: AWXClient):
        self.repo = repo
        self.awx_client = awx_client
        self.known_playbooks = {
            # Removed hardcoded 'server_down' -> 'Demo Job Template' mapping to prevent auto-selection
            # "server_down": {"id": "7", "name": "Demo Job Template", "description": "Demo playbook for server remediation"},
            # Updated: use name for lookup, ID is placeholder to be resolved dynamically
            "high_cpu": {"id": "dynamic", "name": "Linux_Kill_CPU_Utilization", "description": "Kill high CPU consuming processes on Linux"},
            "high_memory": {"id": "7", "name": "Demo Job Template", "description": "Memory issues require further investigation or service restart"},
            "disk_full": {"id": "10", "name": "Clean up var filesystem", "description": "Archive old logs and clean up disk space on /var"},
            "storage_full": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up /var filesystem"},
            "storage_space_warning": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up /var filesystem"},
            "file_system_full": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up /var filesystem"},
            "filesystem_cleanup": {"id": "10", "name": "Clean up var filesystem", "description": "Cleanup /var filesystem and remove temporary files"},
            "out_of_space": {"id": "10", "name": "Clean up var filesystem", "description": "Free up disk space on /var"},
            "var_full": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up /var partition"},
            "tmp_full": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up /tmp partition"},
            "fs_full": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up filesystem"},
            "disk_usage_high": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up disk space"},
            "disk_space": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up disk space"},
            "filesystem_issue": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up filesystem"},
            "storage_issue": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up filesystem due to storage issue"},
            "critical_disk_space": {"id": "10", "name": "Clean up var filesystem", "description": "Clean up disk space"},
            "database_down": {"id": "7", "name": "Demo Job Template", "description": "Restart database service"},
            "network_error": {"id": "9", "name": "check_cpu_utilization", "description": "Check system metrics during network error"},
            "application_crash": {"id": "7", "name": "Demo Job Template", "description": "Restart application"},
        }

    def _get_playbook_for_classification(self, category: str) -> dict:
        """Map incident category to appropriate AWX playbook ID."""
        # storage related labels
        if any(keyword in category.lower() for keyword in ["disk", "storage", "filesystem", "space"]):
            return self.known_playbooks.get("disk_full")

        return self.known_playbooks.get(category)

    def _filter_playbooks(self, ctx: PipelineContext, playbooks: List[dict]) -> List[dict]:
        """
        Filter playbooks to reduce noise for the LLM.
        Criteria:
        1. Always include a default/demo playbook if available (ID 7).
        2. Score others by keyword matching with incident description/classification.
        3. Return top N (e.g. 5).
        """
        if not playbooks:
            return []

        # Keywords from incident
        text = (ctx.incident.short_description + " " + ctx.incident.description).lower()
        if ctx.classification and ctx.classification.labels:
             text += " " + " ".join(ctx.classification.labels)
        
        scored = []
        
        for pb in playbooks:
            # Score
            score = 0
            pb_text = (pb.get("name", "") + " " + pb.get("description", "")).lower()
            
            # Simple token overlap
            # Updated: changed > 3 to >= 2 to capture 'cpu', 'vm', etc.
            incident_tokens = set(w for w in text.split() if len(w) >= 2)
            matches = sum(1 for t in incident_tokens if t in pb_text)
            score += matches

            scored.append((score, pb))

        # Sort by score desc
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Take top 5 from scored (increased from 3 to give LLM more options)
        top_candidates = [x[1] for x in scored[:5]]

        return top_candidates

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.classification:
            raise HTTPException(status_code=400, detail="PlannerAgent: classification missing")

        number = ctx.incident.number
        playbooks = playbooks or []

        # Removed Deterministic Suggestion Logic as per user request.
        # rely purely on LLM selection.

        # FILTERING STEP
        filtered_playbooks = self._filter_playbooks(ctx, playbooks)
        
        formatted_playbooks = []
        for pb in filtered_playbooks:
            desc = pb.get("description", "")
            
            # Enrich description: PREFER known playbook description if available
            # This ensures high quality descriptions ("Kill high CPU...") override poor AWX descriptions ("processes which consumes CPU")
            for known in self.known_playbooks.values():
                if known.get("name") == pb.get("name"):
                    desc = known.get("description")
                    break
            
            formatted_playbooks.append(f"ID: {pb['id']}, Name: {pb['name']}, Description: {desc or 'N/A'}")
        print(f"Playbooks sent to LLM ({len(formatted_playbooks)}/{len(playbooks)}): {formatted_playbooks}")

        # Prepare prompt inputs
        inputs = {
            "incident": ctx.incident.dict() if ctx.incident else {},
            "classification": ctx.classification.dict() if ctx.classification else {},
            "playbooks": '\n'.join(formatted_playbooks),
        }

        # Compose prompt WITHOUT explicit suggestion
        prompt_pure_llm = ChatPromptTemplate.from_messages([
            ("system",
             "You are a remediation planner. You have access to the following AWX playbooks: {playbooks}.\n"
             "Analyze the incident and classification, then choose the most suitable playbook from the list.\n"
             "If no playbook is suitable, set playbook_id to '0' and playbook_name to 'No suitable playbook'.\n"
             "Return only JSON. Always include both playbook_id and playbook_name in your output."),
            ("user",
             "Incident: {incident}\nClassification: {classification}\n\n"
             "Return JSON with keys: playbook_id (string), playbook_name (string), prechecks (list), rollback_steps (list), risk_score (0-1), eligibility (auto or human-only)."
            )
        ])

        msg = await llm.ainvoke(prompt_pure_llm.format(**inputs))
        print(f"Planner LLM output: {repr(msg.content)}")

        # Parse structured output
        try:
            parsed_raw = parser.parse(msg.content)
            
            # Convert to dict to ensure consistency whether it's a dict or Plan object
            if hasattr(parsed_raw, "dict"):
                plan_data = parsed_raw.dict()
            else:
                plan_data = parsed_raw

            print(f"Post-parsing plan data: {plan_data}")

            # Validate/Override with PlaybookSelectionValidator
            if ctx.classification and ctx.classification.labels:
                 plan_data = validate_playbook_selection(plan_data, ctx.classification.labels, self.known_playbooks)

            # Ensure prechecks and rollback_steps are lists
            if not plan_data.get("prechecks"):
                plan_data["prechecks"] = []
            if not plan_data.get("rollback_steps"):
                plan_data["rollback_steps"] = []
            
            if "playbook_id" in plan_data:
                plan_data["playbook_id"] = str(plan_data["playbook_id"])
            
            # Validating LLM selection against available IDs
            available_ids = set(str(p.get("id")) for p in playbooks)
            selected_id = str(plan_data.get("playbook_id"))

            if selected_id not in available_ids and selected_id != '0':
                 print(f"Warning: LLM selected ID {selected_id} which is not in available playbooks.")
                 # We could raise error or try to find by name.
                 # Try finding by name if ID mismatch
                 match = next((p for p in playbooks if p["name"] == plan_data.get("playbook_name")), None)
                 if match:
                     print(f"Resolved name {plan_data['playbook_name']} to ID {match['id']}")
                     plan_data['playbook_id'] = str(match['id'])
                 else:
                     raise HTTPException(status_code=400, detail=f"PlannerAgent: Selected playbook ID {selected_id} not available.")

            # Ensure playbook_name is present
            if not plan_data.get("playbook_name"):
                 plan_data["playbook_name"] = next((pb["name"] for pb in playbooks if str(pb["id"]) == plan_data["playbook_id"]), "unknown")

            plan = Plan(**plan_data)
            print(f"Plan created: {plan}")
        except Exception as e:
            print(f"PlannerAgent: failed to create plan: {e}")
            raise HTTPException(status_code=500, detail=f"PlannerAgent: invalid plan creation {e}")

        if self.repo:
            try:
                await self.repo.upsert(number, plan)
            except Exception as e:
                print(f"Failed to upsert plan: {e}")
        # Cache removed: do not set plan in cache

        ctx.plan = plan
        return ctx


