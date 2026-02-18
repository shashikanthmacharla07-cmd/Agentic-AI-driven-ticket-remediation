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
    model=os.getenv("LLM_MODEL", "llama2:7b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
    num_thread=2,
)

prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a remediation planner. Your job is to select the correct AWX playbook for an IT incident.\n"
             "You have access to these playbooks: {playbooks}.\n"
             "\n"
             "DECISION TREE:\n"
             "1. Read the incident 'labels' from the input.\n"
             "2. Match the label to the correct playbook using these rules:\n"
             "   - IF label is 'service_down' OR 'server_down' -> SELECT playbook 'linux-start-webservice'\n"
             "   - IF label is 'high_cpu' -> SELECT playbook 'linux-cpu-cleanup'\n"
             "   - IF label is 'high_memory' -> SELECT playbook 'linux-high-memory-cleanup'\n"
             "   - IF label includes 'disk' OR 'filesystem' -> SELECT playbook 'linux-var-filesystem-cleanup'\n"
             "   - IF label is 'create_user' -> SELECT playbook 'linux_create_user'\n"
             "3. Return the ID of the selected playbook.\n"
             "4. If no playbook matches, return playbook_id='0'.\n"
             "OUTPUT FORMAT:\n"
             "You must return a single valid JSON object. Do not include any explanation or conversational text.\n"
             "Example:\n"
             "{{\n"
             "  \"playbook_id\": \"9\",\n"
             "  \"playbook_name\": \"linux-var-filesystem-cleanup\",\n"
             "  \"prechecks\": [],\n"
             "  \"risk_score\": 0.5,\n"
             "  \"eligibility\": \"auto\"\n"
             "}}"),
            ("user",
             "Incident: {incident}\n"
             "Classification: {classification}\n"
             "Return ONLY JSON."
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

        # Helper to find playbook ID by fuzzy name match
        def find_playbook_id(name_part: str) -> Optional[str]:
            for pb in filtered_playbooks:
                if name_part in pb.get("name", "").lower():
                    print(f"Planner: Deterministic match found: {pb.get('name')} (ID: {pb.get('id')})")
                    return str(pb.get("id"))
            return None

        # DETERMINISTIC SELECTION (Anti-Hallucination Layer)
        # Check labels for known mappings to enforce reliability
        labels = ctx.classification.labels
        selected_id = None
        playbook_reason = ""
        
        if any(l in labels for l in ['service_down', 'server_down']):
             selected_id = find_playbook_id("start-webservice")
             playbook_reason = "service_down_rule"
        elif any(l in labels for l in ['create_user']):
             selected_id = find_playbook_id("create_user") # matches linux_create_user
             playbook_reason = "create_user_rule"
        elif any(l in labels for l in ['high_cpu']):
             selected_id = find_playbook_id("cpu-cleanup")
             playbook_reason = "high_cpu_rule"
        elif any(l in labels for l in ['high_memory']):
             selected_id = find_playbook_id("memory-cleanup")
             playbook_reason = "high_memory_rule"
        elif any(l in labels for l in ['disk_full', 'var_filesystem_full', 'var_full']):
             selected_id = find_playbook_id("var-filesystem-cleanup")
             playbook_reason = "disk_full_rule"

        if selected_id:
             print(f"Planner: Deterministic logic selected playbook ID {selected_id} based on reason: {playbook_reason}")
             pb = next((p for p in filtered_playbooks if str(p["id"]) == selected_id), None)
             if pb:
                 plan = Plan(
                     playbook_id=selected_id,
                     playbook_name=pb.get("name"),
                     prechecks=[],
                     rollback_steps=[],
                     risk_score=0.1,
                     eligibility="auto"
                 )
                 # Cache update if needed
                 if self.repo:
                     try:
                         await self.repo.upsert(number, plan)
                     except Exception as e:
                         print(f"Failed to upsert plan: {e}")
                 
                 ctx.plan = plan
                 return ctx
             else:
                 print(f"Planner: Deterministic ID {selected_id} valid but playbook object not found in filtered list. Falling back to LLM.")

        
        formatted_playbooks = []
        for pb in filtered_playbooks:
            desc = pb.get("description") or ""
            # Use AWX description directly - no need for hardcoded overrides
            formatted_playbooks.append(f"ID: {pb['id']}, Name: {pb['name']}, Description: {desc or 'N/A'}")
        print(f"Playbooks sent to LLM ({len(formatted_playbooks)}/{len(playbooks)}): {formatted_playbooks}")

        # Prepare prompt inputs
        incident_str = f"Short: {ctx.incident.short_description}\nDescription: {ctx.incident.description}\nOS: {ctx.incident.context.get('os', 'unknown')}"
        classification_str = f"Intent: {ctx.classification.intent}\nLabels: {ctx.classification.labels}"

        inputs = {
            "incident": incident_str,
            "classification": classification_str,
            "playbooks": '\n'.join(formatted_playbooks),
        }

        # Use the robust global prompt
        msg = await llm.ainvoke(prompt.format(**inputs))
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
