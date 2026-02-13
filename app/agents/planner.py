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


    def _create_escalation_plan(self, ctx: PipelineContext, reason: str) -> PipelineContext:
        """Create a plan that signals escalation (playbook_id='0')"""
        plan = Plan(
            playbook_id="0",
            playbook_name=reason,
            prechecks=[],
            rollback_steps=[],
            risk_score=0.0,
            eligibility="human-only"
        )
        ctx.plan = plan
        return ctx



    def _filter_playbooks(self, ctx: PipelineContext, playbooks: List[dict]) -> List[dict]:
        """
        Filter playbooks only by OS compatibility.
        No keyword scoring - we let the LLM decide from all available/compatible playbooks.
        """
        if not playbooks:
            return []

        # OS Filtering based on hostname detection from classifier
        detected_os = None
        if ctx.incident and ctx.incident.context:
            detected_os = ctx.incident.context.get("os")
            hostname = ctx.incident.context.get("hostname")
            if detected_os:
                print(f"Planner: Filtering playbooks for OS '{detected_os}' (hostname: {hostname})")
        
        if detected_os:
            filtered_by_os = []
            excluded = []
            for pb in playbooks:
                # Explicitly filter out Default/Demo playbooks
                if str(pb.get("id")) == "7" or "demo" in pb.get("name", "").lower():
                    print(f"Planner: Explicitly excluding Demo playbook: {pb.get('name')} (ID: {pb.get('id')})")
                    continue

                pb_text = (pb.get("name", "") + " " + (pb.get("description") or "")).lower()
                # If OS is linux, skip windows playbooks
                if detected_os == "linux" and "windows" in pb_text:
                    excluded.append(pb.get("name"))
                    continue
                # If OS is windows, skip linux playbooks
                if detected_os == "windows" and "linux" in pb_text:
                    excluded.append(pb.get("name"))
                    continue
                filtered_by_os.append(pb)
            
            if excluded:
                print(f"Planner: Excluded {len(excluded)} playbooks due to OS mismatch: {excluded}")
            
            return filtered_by_os
        
        # If no OS detected, still filter generic/demo playbooks
        final_list = []
        for pb in playbooks:
             if str(pb.get("id")) == "7" or "demo" in pb.get("name", "").lower():
                 print(f"Planner: Explicitly excluding Demo playbook: {pb.get('name')} (ID: {pb.get('id')})")
                 continue
             final_list.append(pb)

        return final_list

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.classification:
            raise HTTPException(status_code=400, detail="PlannerAgent: classification missing")

        number = ctx.incident.number
        playbooks = playbooks or []

        # Removed Deterministic Suggestion Logic as per user request.
        # rely purely on LLM selection.

        # FILTERING STEP
        filtered_playbooks = self._filter_playbooks(ctx, playbooks)
        
        # If no playbooks match the incident criteria (OS, keywords), escalate immediately
        if not filtered_playbooks:
            print("Planner: No playbooks matched filtering criteria. Escalating to human.")
            return self._create_escalation_plan(ctx, "No suitable playbook found after filtering")
        
        formatted_playbooks = []
        for pb in filtered_playbooks:
            desc = pb.get("description") or ""
            # Use AWX description directly - no need for hardcoded overrides
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
             "You are an intelligent remediation planner. You have access to the following AWX playbooks: {playbooks}.\n"
             "Your goal is to carefully analyze the incident details and selecting the *exact* playbook that resolves the specific issue.\n"
             "Instructions:\n"
             "1. Read the incident description and short_description carefully.\n"
             "2. Read the names and descriptions of ALL provided playbooks.\n"
             "3. If a playbook explicitly matches the issue (e.g., 'install ntp' matches a playbook for ntp installation), select it.\n"
             "4. If NO playbook matches the specific issue, YOU MUST set playbook_id to '0' and playbook_name to 'No suitable playbook'.\n"
             "5. Do NOT select a playbook just because it mentions 'linux' or 'cpu' if it doesn't solve the specific problem described.\n"
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

            # Removed manual override logic - relying completely on LLM

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
