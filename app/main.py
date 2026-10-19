# file: app/main.py

from typing import List, Optional
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import functools
import inspect

from fastapi.routing import APIRoute
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import generate_latest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, TimeoutError as SATimeoutError
from sqlalchemy.orm import Session

from app import schemas
from app.cache import get_cache, set_cache, delete_cache, redis_client
from app.crud import delivery as crud_delivery
from app.crud import event as crud_event
from app.crud import user as crud_user
from app.crud import webhook as crud_webhook
from app.db import dispose_engine
from app.deps import auth_endpoint_limit, authed_user_id, get_db
from app.logging_config import setup_logging
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY
from app.tracing import setup_tracing
from app.ssrf import BlockedTarget, check_url
from app.security import (
    JWT_TTL_SECONDS, create_access_token, get_jwt_secret, verify_password,
)

setup_tracing("ferrum-gateway")
setup_logging()
logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = int(os.getenv("MAX_PAYLOAD_BYTES", 256 * 1024))
MAX_IDEMPOTENCY_KEY_LEN = 255


@asynccontextmanager
async def lifespan(app):
    get_jwt_secret()  # fail fast on a missing/short secret rather than on the first login
    logger.info("gateway_startup")
    yield
    # uvicorn has already stopped accepting and drained in-flight requests by this point.
    logger.warning("gateway_shutdown")
    try:
        redis_client.close()
    except Exception:
        pass
    dispose_engine()


class SessionReleasingRoute(APIRoute):
    """Return the request's DB connection to the pool *inside the handler's own thread*.

    Why: FastAPI runs sync handlers in a bounded thread pool and then needs another pool thread to serialise
    the response, after which the session dependency is torn down. If the connection is only released at
    teardown, finished requests hold connections while waiting for a thread, and the threads are all blocked
    waiting for those connections: a circular wait. Under 200 concurrent clients this stalled the service
    (80 pool timeouts, 59 events accepted in 30 s). Closing the session before the handler returns removes the
    cycle: a connection is then only ever held by a thread that is running and will finish.
    Sizing the pool to the thread count does NOT fix it (requests 1..N take every connection, then queue for
    serialisation behind requests N+1..2N, which block on the pool)."""

    def __init__(self, path, endpoint, **kwargs):
        if not inspect.iscoroutinefunction(endpoint):
            endpoint = _close_session_when_done(endpoint)
        super().__init__(path, endpoint, **kwargs)


def _close_session_when_done(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            db = kwargs.get("db")
            if db is not None:
                db.close()
    return wrapper


app = FastAPI(title="Ferrum Webhook Gateway", lifespan=lifespan)
app.router.route_class = SessionReleasingRoute
FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")


@app.exception_handler(SATimeoutError)
async def db_pool_exhausted(request: Request, exc: SATimeoutError):
    """No DB connection became free within DB_POOL_TIMEOUT: shed load explicitly rather than hang."""
    logger.warning("db_pool_exhausted", extra={"service": "gateway", "path": request.url.path})
    return JSONResponse(status_code=503, content={"detail": "Service busy, retry shortly"},
                        headers={"Retry-After": "1"})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        "request completed",
        extra={"service": "gateway",
               "request_id": request_id,
               "method": request.method,
               "path": request.url.path,
               "status_code": response.status_code,
               "latency": round(process_time, 4)}
    )
    REQUEST_COUNT.inc()
    REQUEST_LATENCY.observe(process_time)
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------- ops

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


@app.get("/")
def root():
    return {"message": "Welcome to Ferrum Webhook Relay!"}


@app.get("/healthz")
def healthz():
    """Liveness: the process is up and serving. Deliberately checks no dependencies, so a
    DB blip restarts nothing."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    """Readiness: can this pod do useful work? Needs only Postgres. Ingest goes through the
    outbox, and Redis (cache, rate limit) degrades gracefully, so Redis is not required."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("readiness_failed", extra={"service": "gateway", "error": str(e)})
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": "down"})
    return {"status": "ready"}


# ---------------------------------------------------------------- auth

@app.post("/register", response_model=schemas.UserOut, status_code=201,
          dependencies=[Depends(auth_endpoint_limit)])
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud_user.get_user_by_email(db, user.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    try:
        return crud_user.create_user(db, user.email, user.password)
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")


@app.post("/login", response_model=schemas.TokenOut, dependencies=[Depends(auth_endpoint_limit)])
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud_user.get_user_by_email(db, body.email)
    # verify_password runs a dummy hash for unknown emails: same cost, same error.
    if not verify_password(body.password, user.password_hash if user else None) or not user:
        raise HTTPException(status_code=401, detail="Invalid credentials",
                            headers={"WWW-Authenticate": "Bearer"})
    return schemas.TokenOut(access_token=create_access_token(user.id),
                            expires_in=JWT_TTL_SECONDS)


# ---------------------------------------------------------------- webhooks

def _check_target(url) -> None:
    try:
        check_url(str(url))
    except BlockedTarget as e:
        raise HTTPException(status_code=422, detail=f"Webhook URL rejected: {e}")


def _webhooks_cache_key(user_id: int) -> str:
    return f"webhooks:user:{user_id}"


@app.post("/webhooks", response_model=schemas.WebhookDetail, status_code=201)
def create_webhook(webhook: schemas.WebhookCreate,
                   user_id: int = Depends(authed_user_id),
                   db: Session = Depends(get_db)):
    _check_target(webhook.url)
    db_webhook = crud_webhook.create_webhook(db, user_id=user_id, url=webhook.url,
                                             event_type=webhook.event_type)
    delete_cache(_webhooks_cache_key(user_id))
    return db_webhook


@app.get("/webhooks", response_model=List[schemas.WebhookOut])
def list_webhooks(user_id: int = Depends(authed_user_id), db: Session = Depends(get_db)):
    cache_key = _webhooks_cache_key(user_id)
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    serialized = [
        {"id": w.id, "url": w.url, "event_type": w.event_type}
        for w in crud_webhook.get_webhooks(db, user_id)
    ]
    set_cache(cache_key, serialized)
    return serialized


def _owned_webhook(db: Session, user_id: int, webhook_id: int):
    webhook = crud_webhook.get_webhook(db, user_id, webhook_id)
    if not webhook:  # 404, not 403: don't reveal that another user's id exists
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@app.get("/webhooks/{webhook_id}", response_model=schemas.WebhookDetail)
def get_webhook(webhook_id: int, user_id: int = Depends(authed_user_id),
                db: Session = Depends(get_db)):
    return _owned_webhook(db, user_id, webhook_id)


@app.patch("/webhooks/{webhook_id}", response_model=schemas.WebhookOut)
def update_webhook(webhook_id: int, body: schemas.WebhookUpdate,
                   user_id: int = Depends(authed_user_id), db: Session = Depends(get_db)):
    webhook = _owned_webhook(db, user_id, webhook_id)
    if body.url is not None:
        _check_target(body.url)
    updated = crud_webhook.update_webhook(db, webhook, url=body.url, event_type=body.event_type)
    delete_cache(_webhooks_cache_key(user_id))
    return updated


@app.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, user_id: int = Depends(authed_user_id),
                   db: Session = Depends(get_db)):
    crud_webhook.delete_webhook(db, _owned_webhook(db, user_id, webhook_id))
    delete_cache(_webhooks_cache_key(user_id))
    return Response(status_code=204)


# ---------------------------------------------------------------- events

def _same_request(existing, body: schemas.EventCreate) -> bool:
    return existing.event_type == body.event_type and existing.payload == body.payload


@app.post("/events", response_model=schemas.EventAccepted, status_code=202)
def create_event(
    request: Request,
    response: Response,
    event: schemas.EventCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user_id: int = Depends(authed_user_id),
    db: Session = Depends(get_db),
):
    request_id = request.state.request_id

    if idempotency_key is not None and not (0 < len(idempotency_key) <= MAX_IDEMPOTENCY_KEY_LEN):
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 1-255 characters")
    if len(json.dumps(event.payload)) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    def replayed(existing):
        if not _same_request(existing, event):
            raise HTTPException(
                status_code=422,
                detail="Idempotency-Key was already used with a different request body")
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
        return schemas.EventAccepted(
            event_id=existing.public_id, status=existing.status,
            deliveries=crud_event.count_deliveries(db, existing.id))

    if idempotency_key:
        existing = crud_event.get_event_by_idempotency_key(db, user_id, idempotency_key)
        if existing:
            return replayed(existing)

    try:
        db_event, n = crud_event.create_event(
            db, user_id=user_id, payload=event.payload, event_type=event.event_type,
            request_id=request_id, idempotency_key=idempotency_key)
    except IntegrityError:
        # Concurrent request with the same key won the insert; return its result.
        existing = (crud_event.get_event_by_idempotency_key(db, user_id, idempotency_key)
                    if idempotency_key else None)
        if not existing:
            raise
        return replayed(existing)

    span = trace.get_current_span()
    span.set_attribute("ferrum.event_id", db_event.public_id)
    span.set_attribute("ferrum.deliveries", n)
    logger.info("event_created",
                extra={"service": "gateway", "request_id": request_id,
                       "event_id": db_event.public_id, "deliveries": n})
    return schemas.EventAccepted(event_id=db_event.public_id, status=db_event.status, deliveries=n)


def _event_out(e, with_payload: bool) -> schemas.EventOut:
    return schemas.EventOut(event_id=e.public_id, event_type=e.event_type, status=e.status,
                            created_at=e.created_at, payload=e.payload if with_payload else None)


@app.get("/events", response_model=List[schemas.EventOut], response_model_exclude_none=True)
def list_events(limit: int = Query(50, ge=1, le=100),
                before: Optional[str] = Query(None, description="event_id cursor: return older events"),
                user_id: int = Depends(authed_user_id), db: Session = Depends(get_db)):
    before_id = None
    if before:
        cursor = crud_event.get_event(db, user_id, before)
        if not cursor:
            raise HTTPException(status_code=404, detail="Cursor event not found")
        before_id = cursor.id
    return [_event_out(e, False) for e in crud_event.list_events(db, user_id, limit, before_id)]


def _owned_event(db: Session, user_id: int, event_id: str):
    event = crud_event.get_event(db, user_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get("/events/{event_id}", response_model=schemas.EventOut)
def get_event(event_id: str, user_id: int = Depends(authed_user_id),
              db: Session = Depends(get_db)):
    return _event_out(_owned_event(db, user_id, event_id), True)


# ---------------------------------------------------------------- deliveries + replay

def _delivery_out(d, event_public_id: str, with_attempts_db: Optional[Session] = None):
    attempts = None
    if with_attempts_db is not None:
        attempts = [schemas.DeliveryAttemptOut.model_validate(a)
                    for a in crud_delivery.attempts(with_attempts_db, d.id)]
    return schemas.DeliveryOut(
        id=d.id, event_id=event_public_id, webhook_id=d.webhook_id, status=d.status,
        retries=d.retries or 0, response_code=d.response_code, latency_ms=d.latency_ms,
        error_message=d.error_message, attempted_at=d.attempted_at,
        next_retry_at=d.next_retry_at, attempts=attempts)


@app.get("/deliveries", response_model=List[schemas.DeliveryOut], response_model_exclude_none=True)
def list_deliveries(status: Optional[str] = Query(None, description="e.g. failed, dead_letter, success"),
                    limit: int = Query(50, ge=1, le=100),
                    before_id: Optional[int] = Query(None, description="delivery id cursor"),
                    user_id: int = Depends(authed_user_id), db: Session = Depends(get_db)):
    rows = crud_delivery.list_for_user(db, user_id, limit, status, before_id)
    return [_delivery_out(d, public_id) for d, public_id in rows]


@app.get("/deliveries/{event_id}", response_model=List[schemas.DeliveryOut],
         response_model_exclude_none=True)
def get_event_deliveries(event_id: str, user_id: int = Depends(authed_user_id),
                         db: Session = Depends(get_db)):
    event = _owned_event(db, user_id, event_id)
    return [_delivery_out(d, event.public_id, db) for d in crud_delivery.list_for_event(db, event)]


@app.post("/retry/{event_id}", response_model=schemas.ReplayOut, status_code=202)
@app.post("/events/{event_id}/replay", response_model=schemas.ReplayOut, status_code=202)
def replay_event(event_id: str, request: Request, user_id: int = Depends(authed_user_id),
                 db: Session = Depends(get_db)):
    """Re-queue the event's failed / dead-lettered deliveries. Successful ones are untouched."""
    event = _owned_event(db, user_id, event_id)
    trace.get_current_span().set_attribute("ferrum.event_id", event.public_id)
    n = crud_event.replay_event(db, event, request_id=request.state.request_id)
    logger.info("event_replayed", extra={"service": "gateway", "event_id": event.public_id,
                                         "request_id": request.state.request_id, "deliveries": n})
    return schemas.ReplayOut(event_id=event.public_id, replayed_deliveries=n)
