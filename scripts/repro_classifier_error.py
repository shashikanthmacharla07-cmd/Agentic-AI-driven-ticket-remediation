
import asyncio
import os
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List

# Define the model to match app/models.py
class Classification(BaseModel):
    labels: List[str] = Field(description="List of labels")
    severity: str = Field(description="Severity P1-P4")
    eligibility: str = Field(description="auto or human-only")
    confidence: float = Field(description="Confidence 0-1")

async def test_classifier_prompt():
    print("Testing Classifier Prompt with phi:2.7b...")
    
    llm = ChatOllama(
        model="phi:2.7b",
        base_url="http://localhost:11434",
        temperature=0,
    )
    
    # Original Prompt from classifier.py
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a classification agent for IT incidents. Output only valid JSON with keys: labels (array of strings), severity (string: P1|P2|P3|P4), eligibility (string: auto or human-only), confidence (number 0-1).\n"
         "If the incident is about high CPU, CPU utilization, or CPU usage, always include 'high_cpu' in labels.\n"
         "If the incident is about 'VM availability', 'availability' issues, or 'VM unreachable', always include 'vm_availability' and 'high_cpu' in labels.\n"
         "If the incident is about high memory, memory usage, or memory utilization, always include 'high_memory' in labels.\n"
         "If the incident is about disk or filesystem issues (disk full, no space, cleanup needed, /var full, /tmp full), use labels: var_full (if /var is mentioned), tmp_full (if /tmp is mentioned), disk_full, storage_full, filesystem_cleanup.\n"
         "For user creation, onboarding, or adding new users, use labels: 'create_user'.\n"
         "For server down, use 'server_down'. For database down, use 'database_down'. For network issues, use 'network_error'. For application crash, use 'application_crash'.\n"
         "Always set eligibility to 'auto' to allow the planner to decide on remediation.\n"
         "Return only JSON, no extra text."),
        ("user",
         "Classify the incident below:\n"
         "short_description: {short}\n"
         "description: {desc}\n"
         "service: {service}\n"
         "severity_hint: {severity_hint}\n"
         "Constraints:\n"
         "- labels: array of relevant tags reflecting the TRUE nature of the incident.\n"
         "- severity must be one of P1,P2,P3,P4\n"
         "- eligibility must be 'auto'\n"
         "- return only JSON, no extra text.")
    ])
    
    inputs = {
        "short": "create user john on lin-us-poc-01",
        "desc": "create user john on lin-us-poc-01",
        "service": "orchestrator",
        "severity_hint": "medium",
        "playbooks": [] # effectively empty in template
    }
    
    print(f"\nSending prompt to LLM...")
    try:
        msg = await llm.ainvoke(prompt.format(**inputs))
        print(f"Raw Output: '{msg.content}'")
        
        parser = JsonOutputParser(pydantic_object=Classification)
        parsed = parser.parse(msg.content)
        print(f"Parsed: {parsed}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_classifier_prompt())
