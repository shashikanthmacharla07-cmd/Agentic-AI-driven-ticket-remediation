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

llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a remediation planner. Choose the most suitable AWX playbook for the incident. Return only JSON."),
    ("user", "Incident: {incident}\nClassification: {classification}\nAvailable playbooks: {playbooks}\n\n"
             "Return JSON with keys: playbook_id (string), prechecks (list), rollback_steps (list), risk_score (0-1), eligibility (auto or human-only).")
])

parser = JsonOutputParser(pydantic_object=Plan)

class PlannerAgent:
    def __init__(self, repo: PlanRepository, awx_client: AWXClient):
        self.repo = repo
        self.awx_client = awx_client

    def _get_playbook_for_classification(self, category: str) -> dict:
        """Map incident category to appropriate AWX playbook ID."""
        playbook_mapping = {
            "server_down": {"id": "7", "name": "Demo Job Template", "description": "Demo playbook for server remediation"},
            "high_cpu": {"id": "9", "name": "check_cpu_utilization", "description": "Check CPU utilization on Linux"},
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

        # Catch-all for storage related labels
        if any(keyword in category.lower() for keyword in ["disk", "storage", "filesystem", "space"]):
            return playbook_mapping.get("disk_full")

        return playbook_mapping.get(category, {"id": "7", "name": "Demo Job Template", "description": "Default remediation playbook"})

    def _filter_playbooks(self, ctx: PipelineContext, playbooks: List[dict], suggested: dict) -> List[dict]:
        """
        Filter playbooks to reduce noise for the LLM.
        Criteria:
        1. Always include the suggested playbook.
        2. Always include a default/demo playbook if available (ID 7).
        3. Score others by keyword matching with incident description/classification.
        4. Return top N (e.g. 5).
        """
        if not playbooks:
            return []

        # Keywords from incident
        text = (ctx.incident.short_description + " " + ctx.incident.description).lower()
        if ctx.classification and ctx.classification.labels:
             text += " " + " ".join(ctx.classification.labels)
        
        scored = []
        keep_ids = set()

        # 1. Suggested
        if suggested:
            keep_ids.add(str(suggested.get("id")))
        
        # 2. Default (ID 7 - Demo Job Template)
        keep_ids.add("7")

        for pb in playbooks:
            pid = str(pb.get("id"))
            if pid in keep_ids:
                continue
            
            # 3. Score
            score = 0
            pb_text = (pb.get("name", "") + " " + pb.get("description", "")).lower()
            
            # Simple token overlap (could be improved)
            # Check for tokens in incident text
            # We'll just check if significant words from incident appear in playbook text
            # For simplicity in this heuristic: check if any word > 3 chars from incident is in pb
            incident_tokens = set(w for w in text.split() if len(w) > 3)
            matches = sum(1 for t in incident_tokens if t in pb_text)
            score += matches

            scored.append((score, pb))

        # Sort by score desc
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Take top 3 from scored
        top_candidates = [x[1] for x in scored[:3]]

        # Construct final list
        final_list = []
        
        # Add force-kept playbooks first to ensure they are present
        for pb in playbooks:
            if str(pb.get("id")) in keep_ids:
                final_list.append(pb)
        
        for pb in top_candidates:
            final_list.append(pb)
            
        return final_list

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.classification:
            raise HTTPException(status_code=400, detail="PlannerAgent: classification missing")

        number = ctx.incident.number
        playbooks = playbooks or []

        # 1. Deterministic suggestion based on classification labels
        suggested_playbook = None
        for label in ctx.classification.labels:
            pb = self._get_playbook_for_classification(label)
            if pb and pb.get("id") != "7": # Prefer specific over default
                suggested_playbook = pb
                break
        
        if not suggested_playbook:
            suggested_playbook = self._get_playbook_for_classification("default")
        
        # Final Safeguard: Double check raw description for storage keywords regardless of labels
        incident_text = f"{ctx.incident.short_description} {ctx.incident.description}".lower()
        if any(k in incident_text for k in ["/var", "/tmp", "disk full", "storage full", "filesystem full", "out of space"]):
            print("Fallback: Storage keywords detected in description. Forcing disk cleanup playbook ID 10.")
            suggested_playbook = {"id": "10", "name": "Clean up var filesystem", "description": "Forced fallback for storage issue"}

        print(f"Deterministic suggestion: {suggested_playbook['name']} (ID: {suggested_playbook['id']})")

        # FILTERING STEP
        filtered_playbooks = self._filter_playbooks(ctx, playbooks, suggested_playbook)
        
        formatted_playbooks = [
            f"ID: {pb['id']}, Name: {pb['name']}" for pb in filtered_playbooks
        ]
        print(f"Playbooks sent to LLM ({len(formatted_playbooks)}/{len(playbooks)}): {formatted_playbooks}")

        # Prepare prompt inputs
        inputs = {
            "incident": ctx.incident.dict() if ctx.incident else {},
            "classification": ctx.classification.dict() if ctx.classification else {},
            "playbooks": '\n'.join(formatted_playbooks),
            "suggested_id": suggested_playbook["id"],
            "suggested_name": suggested_playbook["name"]
        }

        # Compose prompt with explicit suggestion
        prompt_with_suggestions = ChatPromptTemplate.from_messages([
            ("system",
             "You are a remediation planner. You have access to the following AWX playbooks: {playbooks}.\n"
             "Based on the classification labels, the RECOMMENDED playbook is: ID {suggested_id} ({suggested_name}).\n"
             "If this recommendation is appropriate, use it. Otherwise, choose the most suitable playbook.\n"
             "Return only JSON. Always include both playbook_id and playbook_name in your output."),
            ("user",
             "Incident: {incident}\nClassification: {classification}\n\n"
             "Return JSON with keys: playbook_id (string), playbook_name (string), prechecks (list), rollback_steps (list), risk_score (0-1), eligibility (auto or human-only)."
            )
        ])

        msg = await llm.ainvoke(prompt_with_suggestions.format(**inputs))
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

            # Ensure prechecks and rollback_steps are lists
            if not plan_data.get("prechecks"):
                plan_data["prechecks"] = []
            if not plan_data.get("rollback_steps"):
                plan_data["rollback_steps"] = []
            
            selected_id = str(plan_data.get("playbook_id"))
            
            # If we had a specific suggestion (not default) and LLM picked something else, override
            if suggested_playbook["id"] != "7" and selected_id != suggested_playbook["id"]:
                print(f"Overriding LLM selection {selected_id} with deterministic suggestion {suggested_playbook['id']}")
                plan_data["playbook_id"] = suggested_playbook["id"]
                plan_data["playbook_name"] = suggested_playbook["name"]
            
            if "playbook_id" in plan_data:
                plan_data["playbook_id"] = str(plan_data["playbook_id"])
            
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


