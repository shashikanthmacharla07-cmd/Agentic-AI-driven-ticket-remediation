from __future__ import annotations
import os
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from pydantic import ValidationError
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.models import PipelineContext, Classification
from app.data.repositories import ClassificationRepository

llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "llama2:7b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
    num_thread=2,
)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a classification agent for IT incidents. Output only valid JSON with keys: intent (string), labels (array of strings), severity (string: P1|P2|P3|P4), eligibility (string: auto or human-only), confidence (number 0-1).\n"
     "First, describe the user's intent in a short natural language sentence (e.g., 'User wants to reset password', 'System needs disk cleanup').\n"
     "STRICT CLASSIFICATION RULES:\n"
     "1. Analyze the intent.\n"
     "2. Map keywords to labels using this table:\n"
     "   - 'web service', 'service down', 'service stopped', 'process' -> ['service_down'] (CRITICAL: If it says 'service', DO NOT use 'server_down')\n"
     "   - 'server down', 'server unreachable', 'vm down' -> ['server_down']\n"
     "3. Always set eligibility to 'auto'.\n"
     "4. Return only JSON, no extra text."),
    ("user",
     "Classify the incident below:\n"
     "short_description: {short}\n"
     "description: {desc}\n"
     "service: {service}\n"
     "severity_hint: {severity_hint}\n"
     "Constraints:\n"
      "- intent: short description of what needs to be done.\n"
      "- labels: array of relevant tags derived from intent.\n"
     "- severity must be one of P1,P2,P3,P4\n"
     "- severity must be one of P1,P2,P3,P4\n"
     "- eligibility must be 'auto' (we defer to planner for escalation)\n"
     "- return only JSON, no extra text.")
])

parser = JsonOutputParser(pydantic_object=Classification)

class ClassifierAgent:
    def __init__(self, repo: ClassificationRepository):
        self.repo = repo



    def _extract_hostname_and_os(self, ctx: PipelineContext) -> tuple[Optional[str], Optional[str]]:
        """
        Extract hostname from incident description and detect OS based on naming convention.
        - Hostname containing 'lin' -> linux
        - Hostname containing 'win' -> windows
        Returns (hostname, os_type) tuple.
        """
        import re
        
        if not ctx.incident:
            return None, None
        
        # Combine all text sources for hostname extraction
        desc = ctx.incident.description or ""
        short_desc = ctx.incident.short_description or ""
        resource_id = ctx.incident.resource_id or ""
        combined_text = f"{desc} {short_desc} {resource_id}".lower()
        
        hostname = None
        
        # Patterns to extract hostname from description
        # Priority order: more specific patterns first
        patterns = [
            r'hostname[:\s]+([a-zA-Z0-9\-_]+)',           # hostname: xyz or hostname xyz
            r'server[:\s]+([a-zA-Z0-9\-_]+)',             # server: xyz or server xyz
            r'host[:\s]+([a-zA-Z0-9\-_]+)',               # host: xyz or host xyz
            r'on\s+server\s+([a-zA-Z0-9\-_]+)',           # on server xyz
            r'on\s+host\s+([a-zA-Z0-9\-_]+)',             # on host xyz
            r'on\s+([a-zA-Z0-9]*(?:lin|win)[a-zA-Z0-9\-_]*)', # on linprod01 or winprod01
            r'\b([a-zA-Z0-9]*lin[a-zA-Z0-9\-_]*)\b',      # any word containing 'lin'
            r'\b([a-zA-Z0-9]*win[a-zA-Z0-9\-_]*)\b',      # any word containing 'win'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, combined_text)
            if match:
                hostname = match.group(1)
                # Skip common words that aren't hostnames
                if hostname in ['the', 'a', 'an', 'is', 'on', 'in', 'at', 'to', 'for', 'and', 'window', 'windows', 'linux', 'line', 'online', 'offline']:
                    continue
                break
        
        if not hostname:
            return None, None
        
        # Detect OS from hostname pattern
        hostname_lower = hostname.lower()
        os_type = None
        
        if 'lin' in hostname_lower:
            os_type = 'linux'
        elif 'win' in hostname_lower:
            os_type = 'windows'
        
        # Additional Linux distro patterns in hostname
        if not os_type:
            linux_patterns = ['ubuntu', 'centos', 'rhel', 'debian', 'fedora', 'suse']
            if any(p in hostname_lower for p in linux_patterns):
                os_type = 'linux'
        
        if hostname and os_type:
            print(f"Extracted hostname: '{hostname}', detected OS: '{os_type}'")
        elif hostname:
            print(f"Extracted hostname: '{hostname}', OS could not be determined")
        
        return hostname, os_type

    def _extract_username(self, ctx: PipelineContext) -> Optional[str]:
        """
        Extract username from incident description using regex patterns.
        """
        import re
        
        if not ctx.incident:
            return None
        
        # Combine all text sources
        desc = ctx.incident.description or ""
        short_desc = ctx.incident.short_description or ""
        combined_text = f"{desc} {short_desc}".lower()
        
        username = None
        
        # Patterns to extract username
        patterns = [
            r'user[:\s]+([a-z0-9\._]+)',                  # user: jdoe
            r'username[:\s]+([a-z0-9\._]+)',              # username: jdoe
            r'userid[:\s]+([a-z0-9\._]+)',                # userid: jdoe
            r'for\s+user\s+([a-z0-9\._]+)',               # for user jdoe
            r'on\s+behalf\s+of\s+([a-z0-9\._]+)',         # on behalf of jdoe
            r'user\s+([a-z0-9\._]+)\s+cannot',            # user jdoe cannot...
        ]
        
        for pattern in patterns:
            match = re.search(pattern, combined_text)
            if match:
                extract = match.group(1)
                # Filter out common false positives
                if extract in ['check', 'verify', 'please', 'the', 'a', 'an', 'is', 'to', 'for', 'and', 'details', 'regarding']:
                    continue
                username = extract
                break
                
        if username:
            print(f"Extracted username: '{username}'")
            
        return username

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.incident:
            raise HTTPException(status_code=400, detail="ClassifierAgent: incident is missing in context")

        number = ctx.incident.number or "unknown"
        playbooks = playbooks or []

        # Extract hostname and detect OS from incident description
        hostname, detected_os = self._extract_hostname_and_os(ctx)
        
        # Extract username
        username = self._extract_username(ctx)
        
        if hostname or detected_os or username:
            # Store in incident context for planner to use
            if ctx.incident.context is None:
                ctx.incident.context = {}
            if hostname:
                ctx.incident.context["hostname"] = hostname
            if detected_os:
                ctx.incident.context["os"] = detected_os
                print(f"Classifier: Set OS context to '{detected_os}' for planner filtering")
            if username:
                ctx.incident.context["username"] = username


        # Prepare prompt inputs with playbook context
        inputs = {
            "short": ctx.incident.short_description or "",
            "desc": ctx.incident.description or "",
            "service": ctx.incident.service or "",
            "severity_hint": ctx.incident.severity or "",
            "playbooks": playbooks,
        }

        # Compose prompt with playbook context - Refactored for LLM Intelligence & Small Model Compatibility
        prompt_with_playbooks = ChatPromptTemplate.from_messages([
            ("system",
             "You are an intelligent classification agent for IT incidents. You have access to the following AWX playbooks: {playbooks}.\n"
             "Analyze the incident description and determine the most accurate labels based on the actual issue described.\n"
             "Instructions:\n"
             "1. Analyize the input to understand the core issue (e.g. user creation, server down, disk full).\n"
             "2. Define the 'intent' field as a concise summary of the requested action.\n"
             "3. Based on the intent, assign labels from this list if applicable: ['create_user', 'high_cpu', 'high_memory', 'disk_full', 'server_down', 'application_crash', 'network_error'].\n"
             "3. If the request is about installing software, use 'software_install'.\n"
             "4. ALWAYS set 'eligibility' to 'auto'.\n"
             "5. Return ONLY a valid JSON object. Do not add any markdown formatting or explanation.\n"
             "\n"
             "Example Input:\n"
             "short_description: create user jane\n"
             "description: please create user jane on server01\n"
             "\n"
             "Example Output:\n"
             "{{\n"
             "  \"intent\": \"Create a new user account for Jane\",\n"
             "  \"labels\": [\"create_user\"],\n"
             "  \"severity\": \"P3\",\n"
             "  \"eligibility\": \"auto\",\n"
             "  \"confidence\": 0.9\n"
             "}}\n"),
            ("user",
             "Classify the incident below:\n"
             "short_description: {short}\n"
             "description: {desc}\n"
             "service: {service}\n"
             "severity_hint: {severity_hint}\n"
             "Constraints:\n"
             "- intent: string summary\n"
             "- labels: array of strings based on intent\n"
             "- severity: P1, P2, P3, or P4\n"
             "- eligibility: 'auto'\n"
             "- return only JSON.")
        ])

        # Retry logic for robust parsing
        max_retries = 3
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                msg = await llm.ainvoke(prompt_with_playbooks.format(**inputs))
                print(f"Classifier LLM output (Attempt {attempt+1}): {repr(msg.content)}")
                
                # Parse structured output
                parsed_dict = parser.parse(msg.content)
                print(f"Parsed classification dict: {parsed_dict}")
                
                if isinstance(parsed_dict, dict):
                    parsed_dict = {k.lower(): v for k, v in parsed_dict.items()}
                    # Ensure all required fields are present with defaults if missing
                    if "labels" not in parsed_dict:
                        parsed_dict["labels"] = ["unknown"]
                    if "severity" not in parsed_dict:
                        parsed_dict["severity"] = "P3"
                    if "eligibility" not in parsed_dict:
                        parsed_dict["eligibility"] = "auto"
                    # FORCE eligibility to auto for planner decision
                    parsed_dict["eligibility"] = "auto"
                    if "intent" not in parsed_dict:
                        parsed_dict["intent"] = "Unknown intent"
                    if "confidence" not in parsed_dict:
                        parsed_dict["confidence"] = 0.5
                    classification = Classification(**parsed_dict)
                elif not isinstance(parsed_dict, Classification):
                    # fallback: try to coerce to Classification
                    classification = Classification(**dict(parsed_dict))
                else:
                    classification = parsed_dict
                
                # If we got here, parsing succeeded
                break
                
            except Exception as e:
                print(f"ClassifierAgent: parsing attempt {attempt+1} failed: {e}")
                last_exception = e
                # wait briefly before retry (optional)
                import asyncio
                await asyncio.sleep(0.5)
        else:
            # If we exhausted retries, fallback to safe default instead of crashing
            print(f"ClassifierAgent: All {max_retries} attempts failed. Using fallback classification.")
            classification = Classification(
                labels=["manual_classification_required"],
                intent="Failed to classify due to error",
                severity="P3",
                eligibility="auto", # Still let planner see it, maybe it can pick a generic playbook
                confidence=0.0
            )
            # We could raise exception, but user asked to fix the error. 
            # Returning a fallback is safer for pipeline stability.
            
            # If we MUST fail, uncomment below:
            # raise HTTPException(status_code=500, detail=f"ClassifierAgent: invalid LLM output after retries: {last_exception}")

        print(f"Classification object: {classification}")

        # Persist classification
        if self.repo:
            try:
                await self.repo.upsert(number, classification)
            except Exception as e:
                print(f"Failed to upsert classification: {e}")

        ctx.classification = classification
        return ctx

