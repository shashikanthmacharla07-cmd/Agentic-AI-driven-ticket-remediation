# app/startup.py

import os
import logging
import httpx

async def check_ollama_health():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MODEL", "gemma:2b")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            tags = response.json().get("models", [])

            if any(model in tag.get("name", "") for tag in tags):
                logging.info(f"✅ Ollama model '{model}' is available.")
            else:
                logging.warning(f"⚠️ Ollama reachable but model '{model}' not found.")
    except Exception as e:
        logging.error(f"❌ Ollama unreachable: {e}")

