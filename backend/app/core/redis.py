"""Redis client helper for centralized shared cache."""

from __future__ import annotations

import logging
import redis.asyncio as aioredis
from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
  """Get or initialize asynchronous Redis client."""
  global _redis_client
  if _redis_client is not None:
    return _redis_client

  settings = get_settings()
  redis_url = settings.redis_url

  if not redis_url or not redis_url.strip():
    raise RuntimeError(
      "REDIS_URL environment variable is required to start the application and connect to Redis cache."
    )

  _redis_client = aioredis.from_url(
    redis_url.strip(),
    encoding="utf-8",
    decode_responses=True,
  )
  return _redis_client


async def init_redis() -> None:
  """Validate connection to Redis on startup. Fails if unreachable."""
  client = get_redis_client()
  try:
    await client.ping()
    logger.info("Successfully connected to Redis shared cache.")
  except Exception as exc:
    logger.error("Failed to connect to Redis: %s", exc)
    raise RuntimeError(f"Could not connect to Redis cache at {get_settings().redis_url}: {exc}") from exc


async def close_redis_client() -> None:
  """Gracefully close Redis connection pool."""
  global _redis_client
  if _redis_client is not None:
    await _redis_client.aclose()
    _redis_client = None
