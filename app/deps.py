# file: app/deps.py

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_session_local
from app.ratelimit import take_auth_token, take_token
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_db():
    """One Session per request.

    This is deliberately an *async* generator dependency. A sync generator dependency runs its teardown in the
    same 40-thread pool as the sync endpoints. Under load every thread ends up blocked waiting for a pooled
    DB connection that is held by a finished request whose teardown is waiting for a thread: a deadlock
    (reproduced: 80 pool timeouts, 59 events accepted in 30 s at 200 concurrent clients). Closing the session
    on the event loop needs no thread; it only returns the connection to the pool (and rolls back an open
    transaction), which is a sub-millisecond local operation."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    user_id = decode_access_token(creds.credentials) if creds else None
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def authed_user_id(user_id: int = Depends(get_current_user_id)) -> int:
    """Authenticated + rate limited (per-user token bucket). Use on every protected route."""
    allowed, retry_after = take_token(user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    return user_id


def auth_endpoint_limit(request: Request) -> None:
    """Per-client-IP limit for /register and /login (they cost an Argon2 hash each and need no token).
    Behind an ingress, client.host is the proxy: run uvicorn with --proxy-headers and trusted
    --forwarded-allow-ips so this sees the real client."""
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = take_auth_token(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts",
                            headers={"Retry-After": str(retry_after)})
