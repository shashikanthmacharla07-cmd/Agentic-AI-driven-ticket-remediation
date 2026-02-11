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
        
        # Keyword-based category mapping for dynamic playbook discovery
        # Instead of hardcoding playbook names/IDs, we define keywords that match
        # against AWX playbook names and descriptions dynamically
        self.category_keywords = {
            "high_cpu": {
                "keywords": ["cpu", "utilization", "process", "top", "kill"],
                "priority": 10,
                "description": "High CPU utilization remediation"
            },
            "high_memory": {
                "keywords": ["memory", "ram", "oom", "heap", "leak"],
                "priority": 10,
                "description": "Memory issues remediation"
            },
            "disk_full": {
                "keywords": ["disk", "filesystem", "var", "cleanup", "space", "storage", "log"],
                "priority": 10,
                "description": "Disk space cleanup"
            },
            "service_down": {
                "keywords": ["restart", "service", "start", "stop", "systemctl"],
                "priority": 8,
                "description": "Service restart"
            },
            "database_down": {
                "keywords": ["database", "db", "postgres", "mysql", "mongo", "redis"],
                "priority": 8,
                "description": "Database remediation"
            },
            "application_crash": {
                "keywords": ["app", "application", "restart", "deploy"],
                "priority": 7,
                "description": "Application restart"
            },
            "network_error": {
                "keywords": ["network", "connectivity", "firewall", "port"],
                "priority": 6,
                "description": "Network troubleshooting"
            },
        }
        
        # Cache for resolved playbooks (category -> playbook mapping)
        self._playbook_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes


    def _match_playbook_to_category(self, playbooks: List[dict], category: str, detected_os: str = None) -> Optional[dict]:
        """
        Dynamically match a playbook from AWX to an incident category using keywords.
        Returns the best matching playbook or None.
        """
        if category not in self.category_keywords:
            return None
        
        category_info = self.category_keywords[category]
        keywords = category_info["keywords"]
        
        best_match = None
        best_score = 0
        
        for pb in playbooks:
            pb_text = (pb.get("name", "") + " " + (pb.get("description") or "")).lower()
            
            # OS Check
            if detected_os:
                if detected_os == "linux" and "windows" in pb_text:
                    continue
                if detected_os == "windows" and "linux" in pb_text:
                    continue

            # Count keyword matches
            score = sum(1 for kw in keywords if kw in pb_text)
            
            # Bonus for exact category name match
            if category.replace("_", "-") in pb_text or category.replace("_", " ") in pb_text:
                score += 3
            
            if score > best_score:
                best_score = score
                best_match = pb
        
        return best_match if best_score > 0 else None

    def _get_playbook_for_classification(self, category: str, playbooks: List[dict], detected_os: str = None) -> Optional[dict]:
        """
        Dynamically map incident category to appropriate AWX playbook.
        Uses keyword matching against actual AWX playbooks.
        Respects OS constraints if detected_os is provided.
        """
        # Try direct category match first
        match = self._match_playbook_to_category(playbooks, category, detected_os=detected_os)
        if match:
            return match
        
        # Try related categories for storage/disk issues
        if any(keyword in category.lower() for keyword in ["disk", "storage", "filesystem", "space"]):
            match = self._match_playbook_to_category(playbooks, "disk_full", detected_os=detected_os)
            if match:
                return match
        
        # Try CPU-related categories
        if any(keyword in category.lower() for keyword in ["cpu", "utilization", "load"]):
            match = self._match_playbook_to_category(playbooks, "high_cpu", detected_os=detected_os)
            if match:
                return match
        
        # Try memory-related categories
        if any(keyword in category.lower() for keyword in ["memory", "ram", "oom"]):
            match = self._match_playbook_to_category(playbooks, "high_memory", detected_os=detected_os)
            if match:
                return match
        
        return None

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

        # OS Filtering based on hostname detection from classifier
        detected_os = None
        if ctx.incident and ctx.incident.context:
            detected_os = ctx.incident.context.get("os")
            hostname = ctx.incident.context.get("hostname")
            if detected_os:
                print(f"Planner: Filtering playbooks for OS '{detected_os}' (hostname: {hostname})")
        
        if detected_os:
            original_count = len(playbooks)
            filtered_by_os = []
            excluded = []
            for pb in playbooks:
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
            playbooks = filtered_by_os
            if excluded:
                print(f"Planner: Excluded {len(excluded)} playbooks due to OS mismatch: {excluded}")

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

            # Validate/Override with dynamic playbook matching
            if ctx.classification and ctx.classification.labels:
                detected_os = ctx.incident.context.get("os") if ctx.incident.context else None
                
                # Prioritize labels based on incident description matching
                # This ensures CPU incidents get CPU playbooks even if memory label is also present
                incident_text = f"{ctx.incident.short_description or ''} {ctx.incident.description or ''}".lower()
                
                label_scores = []
                for label in ctx.classification.labels:
                    score = 0
                    label_keywords = label.replace("_", " ").split()
                    for kw in label_keywords:
                        if kw in incident_text:
                            score += 1
                    # Boost score for exact keyword presence
                    if label == "high_cpu" and "cpu" in incident_text:
                        score += 5
                    if label == "high_memory" and "memory" in incident_text:
                        score += 5
                    label_scores.append((label, score))
                
                # Sort by score descending - highest relevance first
                label_scores.sort(key=lambda x: x[1], reverse=True)
                print(f"Label priority scores: {label_scores}")
                
                # Use dynamic matching with prioritized labels
                for label, score in label_scores:
                    matched_pb = self._get_playbook_for_classification(label, playbooks, detected_os=detected_os)
                    if matched_pb:
                        plan_data["playbook_id"] = str(matched_pb["id"])
                        plan_data["playbook_name"] = matched_pb["name"]
                        print(f"Dynamic match found: {label} (score: {score}) -> {matched_pb['name']} (ID: {matched_pb['id']})")
                        break

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


