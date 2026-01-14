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
        
        # CPU checks
        if any(k in text_lower for k in ["cpu", "utilization", "processor"]):
            labels.append("high_cpu")
            
        # Memory checks
        if any(k in text_lower for k in ["memory", "ram", "memory_usage"]):
            labels.append("high_memory")
            
        return list(set(labels))

    async def run(self, ctx: PipelineContext, playbooks: List[dict] = None) -> PipelineContext:
        if not ctx.incident:
            raise HTTPException(status_code=400, detail="ClassifierAgent: incident is missing in context")

        number = ctx.incident.number or "unknown"
        playbooks = playbooks or []

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
             "- For high CPU issues, always include 'high_cpu'.\n"
             "- For high memory issues, always include 'high_memory'.\n"
             "- For disk or filesystem issues (disk full, /var full, etc.), use labels: var_full, tmp_full, disk_full, storage_full, filesystem_cleanup.\n"
             "- For server down: 'server_down'. Database: 'database_down'. Network: 'network_error'.\n"
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

