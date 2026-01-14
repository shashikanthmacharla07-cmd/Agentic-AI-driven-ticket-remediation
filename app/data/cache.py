# app/data/cache.py
import json
from typing import Optional, Dict, Any
#from aioredis import Redis
from redis.asyncio import Redis


class Cache:
    def __init__(self, redis: Redis, ttl_seconds: int = 300):
        self.redis = redis
        self.ttl = ttl_seconds

    # ---------- Incident ----------
    async def get_incident(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"incident:{number}")
        return json.loads(val) if val else None

    async def set_incident(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"incident:{number}", json.dumps(data), ex=self.ttl)

    # ---------- Classification ----------
    async def get_classification(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"classification:{number}")
        return json.loads(val) if val else None

    async def set_classification(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"classification:{number}", json.dumps(data), ex=self.ttl)

    # ---------- Plan ----------
    async def get_plan(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"plan:{number}")
        return json.loads(val) if val else None

    async def set_plan(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"plan:{number}", json.dumps(data), ex=self.ttl)

    # ---------- Execution ----------
    async def get_execution(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"execution:{number}")
        return json.loads(val) if val else None

    async def set_execution(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"execution:{number}", json.dumps(data), ex=self.ttl)

    # ---------- Validation ----------
    async def get_validation(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"validation:{number}")
        return json.loads(val) if val else None

    async def set_validation(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"validation:{number}", json.dumps(data), ex=self.ttl)

    # ---------- Closure ----------
    async def get_closure(self, number: str) -> Optional[Dict[str, Any]]:
        val = await self.redis.get(f"closure:{number}")
        return json.loads(val) if val else None

    async def set_closure(self, number: str, data: Dict[str, Any]) -> None:
        await self.redis.set(f"closure:{number}", json.dumps(data), ex=self.ttl)

