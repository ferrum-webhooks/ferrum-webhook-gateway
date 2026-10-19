# file: app/ratelimit.py
#
# Per-user token bucket in Redis. One Lua script = one atomic round trip, and it uses
# Redis TIME so every gateway pod shares the same clock. Fails open if Redis is down:
# a cache outage must not take ingest down with it.

import logging
import math
import os
from typing import Tuple

import redis

from app.cache import redis_client

logger = logging.getLogger(__name__)

RATE_LIMIT_CAPACITY = int(os.getenv("RATE_LIMIT_CAPACITY", 100))        # burst size
RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("RATE_LIMIT_REFILL_PER_SEC", 50))
AUTH_RATE_LIMIT_CAPACITY = int(os.getenv("AUTH_RATE_LIMIT_CAPACITY", 20))   # per client IP, /register + /login
AUTH_RATE_LIMIT_REFILL_PER_SEC = float(os.getenv("AUTH_RATE_LIMIT_REFILL_PER_SEC", 2))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"

_LUA = """
local cap  = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local t    = redis.call('TIME')
local now  = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local d    = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(d[1])
local ts     = tonumber(d[2])
if tokens == nil then tokens = cap; ts = now end
tokens = math.min(cap, tokens + (now - ts) / 1000 * rate)
local allowed = 0
local retry = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry = (1 - tokens) / rate
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('PEXPIRE', KEYS[1], math.ceil(cap / rate * 1000) * 2)
return {allowed, tostring(retry)}
"""

_script = None


def take_token(user_id: int) -> Tuple[bool, int]:
    """Per-user bucket for authenticated routes. Returns (allowed, retry_after_seconds)."""
    return _take(f"ratelimit:user:{user_id}", RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_SEC)


def take_auth_token(client_ip: str) -> Tuple[bool, int]:
    """Per-IP bucket for the unauthenticated, expensive /register and /login."""
    return _take(f"ratelimit:auth-ip:{client_ip}", AUTH_RATE_LIMIT_CAPACITY, AUTH_RATE_LIMIT_REFILL_PER_SEC)


def _take(key: str, capacity: float, refill: float) -> Tuple[bool, int]:
    global _script
    if not RATE_LIMIT_ENABLED:
        return True, 0
    try:
        if _script is None:
            _script = redis_client.register_script(_LUA)
        allowed, retry = _script(
            keys=[key],
            args=[capacity, refill],
        )
        return bool(int(allowed)), max(1, math.ceil(float(retry)))
    except redis.exceptions.RedisError as e:
        logger.warning("rate_limit_unavailable", extra={"service": "gateway", "error": str(e)})
        return True, 0
