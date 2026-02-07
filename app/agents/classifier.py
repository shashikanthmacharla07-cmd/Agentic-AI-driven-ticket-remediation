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
    model=os.getenv("LLM_MODEL", "llama3"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a classification agent for IT incidents. Output only valid JSON with keys: labels (array of strings), severity (string: P1|P2|P3|P4), eligibility (string: auto or human-only), confidence (number 0-1).\n"
     "If the incident is about high CPU, CPU utilization, or CPU usage, always include 'high_cpu' in labels.\n"
     "If the incident is about 'VM availability', 'availability' issues, or 'VM unreachable', always include 'vm_availability' and 'high_cpu' in labels.\n"
     "If the incident is about high memory, memory usage, or memory utilization, always include 'high_memory' in labels.\n"
     "If the incident is about disk or filesystem issues (disk full, no space, cleanup needed, /var full, /tmp full), use labels: var_full (if /var is mentioned), tmp_full (if /tmp is mentioned), disk_full, storage_full, filesystem_cleanup.\n"
     "For server down, use 'server_down'. For database down, use 'database_down'. For network issues, use 'network_error'. For application crash, use 'application_crash'.\n"
     "Return only JSON, no extra text."),
    ("user",
     "Classify the incident below:\n"
     "short_description: {short}\n"
     "description: {desc}\n"
     "service: {service}\n"
     "severity_hint: {severity_hint}\n"
     "Constraints:\n"
     "- labels: array of relevant tags.\n"
     "- severity must be one of P1,P2,P3,P4\n"
     "- eligibility must be 'auto' or 'human-only' (NOT 'auto-remediate')\n"
     "- return only JSON, no extra text.")
])

parser = JsonOutputParser(pydantic_object=Classification)

class ClassifierAgent:
    def __init__(self, repo: ClassificationRepository):
        self.repo = repo

    def _heuristic_labeler(self, text: str) -> List[str]:
        """Scan text for obvious keywords to provide a safety net for small LLMs."""
        labels = []
        text_lower = text.lower()
        
        # Storage / Disk checks
        storage_keywords = ["disk", "storage", "filesystem", "space", "partition", "mount", "full", "cleanup"]
        if any(k in text_lower for k in storage_keywords):
            labels.append("disk_full")
            if "var" in text_lower:
                labels.append("var_full")
            if "tmp" in text_lower:
                labels.append("tmp_full")
            if "cleanup" in text_lower:
                labels.append("filesystem_cleanup")
        
        # CPU checks - be specific about CPU-related terms
        cpu_keywords = ["cpu", "processor", "cpu utilization", "cpu usage", "high cpu"]
        if any(k in text_lower for k in cpu_keywords):
            labels.append("high_cpu")
            
        # VM Availability checks
        if any(k in text_lower for k in ["vm availability", "availability", "vm unreachable"]):
            labels.append("vm_availability")
            labels.append("high_cpu") # Requirement: invoke CPU playbook for VM availability
            
        # Memory checks - only add if memory is explicitly mentioned
        # Don't add high_memory just because of generic "utilization" keyword
        memory_keywords = ["memory", "ram", "memory usage", "memory utilization", "high memory", "oom", "out of memory"]
        if any(k in text_lower for k in memory_keywords):
            labels.append("high_memory")
            
        return list(set(labels))

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

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.incident:
            raise HTTPException(status_code=400, detail="ClassifierAgent: incident is missing in context")

        number = ctx.incident.number or "unknown"
        playbooks = playbooks or []

        # Extract hostname and detect OS from incident description
        hostname, detected_os = self._extract_hostname_and_os(ctx)
        if hostname or detected_os:
            # Store in incident context for planner to use
            if ctx.incident.context is None:
                ctx.incident.context = {}
            if hostname:
                ctx.incident.context["hostname"] = hostname
            if detected_os:
                ctx.incident.context["os"] = detected_os
                print(f"Classifier: Set OS context to '{detected_os}' for planner filtering")

        # Prepare prompt inputs with playbook context
        inputs = {
            "short": ctx.incident.short_description or "",
            "desc": ctx.incident.description or "",
            "service": ctx.incident.service or "",
            "severity_hint": ctx.incident.severity or "",
            "playbooks": playbooks,
        }

        # Compose prompt with playbook context
        prompt_with_playbooks = ChatPromptTemplate.from_messages([
            ("system",
             "You are a classification agent for IT incidents. You have access to the following AWX playbooks: {playbooks}.\n"
             "Classify the incident based on its description and suggest the most relevant labels.\n"
             "Specific labeling instructions:\n"
             "- For high CPU issues, always include 'high_cpu'. ALERT: High CPU/Memory is NOT 'server_down' unless the node is unreachable.\n"
             "- For high memory issues, always include 'high_memory'.\n"
             "- For disk or filesystem issues (disk full, /var full, etc.), use labels: var_full, tmp_full, disk_full, storage_full, filesystem_cleanup.\n"
             "- For server down: 'server_down' (Use ONLY if host is offline/unreachable). Database: 'database_down'. Network: 'network_error'.\n"
             "Output only valid JSON with keys: labels (array of strings), severity (string: P1|P2|P3|P4), eligibility (string: auto or human-only), confidence (number 0-1)."),
            ("user",
             "short_description: {short}\n"
             "description: {desc}\n"
             "service: {service}\n"
             "severity_hint: {severity_hint}\n"
             "Constraints:\n"
             "- labels: array of relevant tags from the specific instructions above.\n"
             "- severity must be one of P1,P2,P3,P4\n"
             "- eligibility must be 'auto' or 'human-only'\n"
             "- return only JSON, no extra text.")
        ])

        msg = await llm.ainvoke(prompt_with_playbooks.format(**inputs))
        print(f"Classifier LLM output: {repr(msg.content)}")

        # Parse structured output
        try:
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
                if "confidence" not in parsed_dict:
                    parsed_dict["confidence"] = 0.5
                classification = Classification(**parsed_dict)
            elif not isinstance(parsed_dict, Classification):
                # fallback: try to coerce to Classification
                classification = Classification(**dict(parsed_dict))
            else:
                classification = parsed_dict
            print(f"Classification object: {classification}")
            
            # Heuristic Safety Net
            heuristic_labels = self._heuristic_labeler(f"{inputs['short']} {inputs['desc']}")
            if heuristic_labels:
                original_labels = set(classification.labels)
                classification.labels = list(original_labels.union(set(heuristic_labels)))
                print(f"Heuristic labels added: {heuristic_labels}. Final labels: {classification.labels}")
                # Boost confidence if heuristics match
                classification.confidence = min(1.0, classification.confidence + 0.2)

        except Exception as e:
            print(f"ClassifierAgent: failed to parse LLM output: {e}")
            raise HTTPException(status_code=500, detail=f"ClassifierAgent: invalid LLM output {e}")

            # Persist classification
        if self.repo:
            try:
                await self.repo.upsert(number, classification)
            except Exception as e:
                print(f"Failed to upsert classification: {e}")

        ctx.classification = classification
        return ctx

