# file: app/security.py

import base64
import os
import secrets
import threading
import time
from typing import Optional

import jwt
from passlib.context import CryptContext

# Argon2id at OWASP's minimum recommended cost (19 MiB, t=2, p=1). passlib's default is 64 MiB per
# hash: 50 concurrent logins OOM-killed a 256 MiB pod in the load test. Hashes created with other
# parameters still verify (parameters are embedded in the hash).
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto",
                           argon2__memory_cost=int(os.getenv("ARGON2_MEMORY_COST_KIB", 19456)),
                           argon2__time_cost=int(os.getenv("ARGON2_TIME_COST", 2)), argon2__parallelism=1)

# Hashing is CPU+memory heavy and /register + /login are unauthenticated: bound how many run at once
# so memory use is capped at HASH_CONCURRENCY * 19 MiB no matter how many requests arrive.
_hash_slots = threading.BoundedSemaphore(int(os.getenv("HASH_CONCURRENCY", 4)))

JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", 3600))
_MIN_SECRET_LEN = 32

# Verified against when the email is unknown, so /login takes the same time either way.
_DUMMY_HASH = pwd_context.hash("ferrum-dummy-password")


def hash_password(password: str) -> str:
    with _hash_slots:
        return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    with _hash_slots:
        return pwd_context.verify(plain_password, hashed_password or _DUMMY_HASH) and bool(hashed_password)


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        if os.getenv("TESTING") == "true":
            return "test-secret-test-secret-test-secret-0000"
        raise RuntimeError("JWT_SECRET is not set")
    if len(secret) < _MIN_SECRET_LEN and os.getenv("TESTING") != "true":
        raise RuntimeError(f"JWT_SECRET must be at least {_MIN_SECRET_LEN} characters")
    return secret


def create_access_token(user_id: int) -> str:
    now = int(time.time())
    claims = {"sub": str(user_id), "iat": now, "exp": now + JWT_TTL_SECONDS}
    return jwt.encode(claims, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Returns the user id, or None if the token is invalid/expired."""
    try:
        claims = jwt.decode(
            token, get_jwt_secret(), algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def generate_webhook_secret() -> str:
    """Standard Webhooks signing secret: "whsec_" + base64(32 random bytes)."""
    return "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()


def new_event_public_id() -> str:
    return "evt_" + secrets.token_hex(16)
