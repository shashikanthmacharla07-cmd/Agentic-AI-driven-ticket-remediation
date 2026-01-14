# app/main.py
import os
import time
import json
import asyncio
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

import asyncpg

import httpx
from pydantic import BaseModel

# Models
from app.models import PipelineContext, Incident, IncidentRequest

# Cache and repositories
# Cache and repositories
# from app.data.cache import Cache
from app.data.repositories import (
    IncidentRepository,
    ClassificationRepository,
    PlanRepository,
    ExecutionRepository,
    ValidationRepository,
    ClosureRepository,
)

# Clients
from app.clients.awx_client import AWXClient
from app.clients.servicenow_client import ServiceNowClient

# Agents
from app.agents.intake import IntakeAgent
from app.agents.classifier import ClassifierAgent
from app.agents.planner import PlannerAgent
from app.agents.executor import ExecutorAgent
from app.agents.validator import ValidatorAgent
from app.agents.closure import ClosureAgent

# Orchestrator
from app.orchestrator import OrchestrationAgent

# Services
from app.services.servicenow_fetcher import ServiceNowIncidentFetcher
from app.services.incident_scheduler import IncidentScheduler

# Health route
from app.routes import health

def get_ollama_host() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://172.16.0.4:11434")

def build_pg_dsn() -> str:
    return (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pg_dsn = build_pg_dsn()

    awx_url = os.getenv("AWX_URL")
    awx_token = os.getenv("AWX_TOKEN")
    snow_url = os.getenv("SNOW_URL")
    snow_user = os.getenv("SNOW_USER")
    snow_pass = os.getenv("SNOW_PASS")

    try:
        app.state.pg_pool = await asyncpg.create_pool(dsn=pg_dsn, min_size=1, max_size=10)
    except Exception as e:
        print(f"Failed to create PG pool: {e}")
        app.state.pg_pool = None

    # app.state.redis = None
    app.state.redis = None
    app.state.cache = None

    if app.state.pg_pool:
        app.state.incident_repo = IncidentRepository(app.state.pg_pool)
        app.state.classification_repo = ClassificationRepository(app.state.pg_pool)
        app.state.plan_repo = PlanRepository(app.state.pg_pool)
        app.state.execution_repo = ExecutionRepository(app.state.pg_pool)
        app.state.validation_repo = ValidationRepository(app.state.pg_pool)
        app.state.closure_repo = ClosureRepository(app.state.pg_pool)
    else:
        app.state.incident_repo = None
        # etc, set to None

    app.state.awx = AWXClient(base_url=awx_url, token=awx_token) if awx_url and awx_token else None
    app.state.snow = ServiceNowClient(base_url=snow_url, username=snow_user, password=snow_pass) if snow_url and snow_user and snow_pass else None

    # Agents initialization
    app.state.intake = IntakeAgent(repo=app.state.incident_repo)
    app.state.classifier = ClassifierAgent(repo=app.state.classification_repo)
    app.state.planner = PlannerAgent(repo=app.state.plan_repo, awx_client=app.state.awx)
    app.state.executor = ExecutorAgent(repo=app.state.execution_repo, awx_client=app.state.awx)
    app.state.validator = ValidatorAgent(repo=app.state.validation_repo)
    app.state.closure = ClosureAgent(repo=app.state.closure_repo, sn_client=app.state.snow)

    app.state.orchestrator = OrchestrationAgent(
        intake=app.state.intake,
        classifier=app.state.classifier,
        planner=app.state.planner,
        executor=app.state.executor,
        validator=app.state.validator,
        closure=app.state.closure
    )

    # Initialize ServiceNow incident fetcher and scheduler
    app.state.sn_fetcher = ServiceNowIncidentFetcher(app.state.snow) if app.state.snow else None
    app.state.scheduler = None
    if app.state.sn_fetcher:
        poll_interval = int(os.getenv("INCIDENT_POLL_INTERVAL_SECONDS", "30"))
        batch_size = int(os.getenv("INCIDENT_BATCH_SIZE", "5"))
        app.state.scheduler = IncidentScheduler(
            fetcher=app.state.sn_fetcher,
            orchestrator=app.state.orchestrator,
            poll_interval=poll_interval,
            incidents_per_poll=batch_size
        )
        await app.state.scheduler.start()
        print(f"Incident scheduler started (polling every {poll_interval}s, batch size: {batch_size})")

    # Ollama warm-up with timeout and retries
    # Ollama warm-up removed to speed up startup

    yield

    # Shutdown: stop scheduler
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        await app.state.scheduler.stop()
    
    # Close connections
    # Close connections
    if hasattr(app.state, 'pg_pool') and app.state.pg_pool:
        await app.state.pg_pool.close()
    if hasattr(app.state, 'redis') and app.state.redis:
        await app.state.redis.close()

app = FastAPI(lifespan=lifespan)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"message": "Orchestrator is running", "ollama_host": get_ollama_host()}

class PromptRequest(BaseModel):
    prompt: str

@app.post("/inference")
async def inference(request: PromptRequest):
    prompt = request.prompt
    ollama_host = get_ollama_host()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{ollama_host}/api/generate",
                json={"model": "gemma:2b", "prompt": prompt, "stream": True},
                headers={"Accept": "application/json"}
            )
            if r.status_code == 200:
                output = ""
                async for line in r.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            output += chunk.get("response", "")
                        except Exception:
                            continue
                return {"response": output[:2000]}
            else:
                raise HTTPException(status_code=r.status_code, detail=r.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {str(e) or 'Unknown failure'}")

@app.post("/inference_fast")
async def inference_fast(request: PromptRequest):
    prompt = request.prompt
    ollama_host = get_ollama_host()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{ollama_host}/api/generate",
                json={"model": "gemma:2b", "prompt": prompt, "stream": False},
                headers={"Accept": "application/json"}
            )
            if r.status_code == 200:
                try:
                    return {"response": r.json().get("response", "")[:2000]}
                except Exception as e:
                    return {"detail": f"Ollama JSON parse error: {str(e)}"}
            else:
                return {"detail": f"Ollama returned {r.status_code}: {r.text}"}
    except Exception as e:
        return {"detail": f"Ollama error: {type(e).__name__}: {str(e) or 'Unknown failure'}"}
async def inference_test():
    ollama_host = get_ollama_host()
    sample_prompt = "Summarize the benefits of containerized AI inference"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{ollama_host}/api/generate",
                json={"model": "gemma:2b", "prompt": sample_prompt, "stream": True},
                headers={"Accept": "application/json"}
            )
            latency = round((time.time() - start) * 1000, 2)
            if r.status_code == 200:
                output = ""
                async for line in r.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            output += chunk.get("response", "")
                        except Exception:
                            continue
                return {
                    "status": "ok",
                    "latency_ms": latency,
                    "model": "gemma:2b",
                    "sample_prompt": sample_prompt,
                    "response_preview": output[:200]
                }
            else:
                return {
                    "status": "error",
                    "latency_ms": latency,
                    "detail": r.text
                }
    except Exception as e:
        return {
            "status": "unreachable",
            "error": str(e)
        }

@app.post("/orchestrate")
async def orchestrate_incident(request: IncidentRequest):
    """
    Manual incident orchestration endpoint (for testing).
    In production, incidents are automatically fetched from ServiceNow and processed.
    """
    try:
        raw_incident = request.dict()
        response = await app.state.orchestrator.run(raw_incident)
        return response
    except Exception as e:
        return {"status": "error", "detail": str(e)}

