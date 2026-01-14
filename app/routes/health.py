# app/routes/health.py
import os
import time
import httpx
from fastapi import APIRouter, Request

router = APIRouter(prefix="/health")


def get_ollama_host() -> str:
    # Use OLLAMA_BASE_URL to match main.py, fallback to OLLAMA_HOST or default
    return os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST", "http://172.16.0.4:11434")

@router.get("")
async def health(request: Request):
    status = {"orchestrator": "ok"}

    # Ollama check
    ollama_host = get_ollama_host()
    sample_prompt = "hi"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{ollama_host}/api/generate",
                json={"model": "gemma:2b", "prompt": sample_prompt, "stream": False}
            )
            latency = round((time.time() - start) * 1000, 2)
            if r.status_code == 200:
                try:
                    response = r.json().get("response", "")
                except Exception:
                    response = r.text
                status["ollama"] = "ok"
                status["ollama_latency_ms"] = latency
                status["ollama_model"] = "gemma:2b"
                status["ollama_response_preview"] = response[:100]
            else:
                status["ollama"] = f"error {r.status_code}"
    except Exception as e:
        status["ollama"] = f"unreachable ({repr(e)})"

    # Postgres check
    try:
        if request.app.state.pg_pool:
            async with request.app.state.pg_pool.acquire() as conn:
                await conn.execute("SELECT 1")
            status["postgres"] = "ok"
        else:
            status["postgres"] = "not_configured"
    except Exception as e:
        status["postgres"] = f"error ({e})"

    # AWX check
    try:
        if hasattr(request.app.state, 'awx') and request.app.state.awx:
            if await request.app.state.awx.ping():
                status["awx"] = "ok"
            else:
                status["awx"] = "error (ping failed)"
        else:
            status["awx"] = "not_configured"
    except Exception as e:
        status["awx"] = f"error ({repr(e)})"


    return status

