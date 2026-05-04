# file: app/main.py

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import generate_latest
from sqlalchemy.orm import Session
import time
import logging
import uuid

from app import schemas
from app.deps import get_db
from app.cache import get_cache, set_cache, delete_cache, push_event, get_queue_length

from app.crud import user as crud_user
from app.crud import webhook as crud_webhook
from app.crud import event as crud_event
from app.logging_config import setup_logging
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

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
               "latency": round(process_time,4),
            }
    )
    REQUEST_COUNT.inc()
    REQUEST_LATENCY.observe(process_time)
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    return response

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type="text/plain")

@app.get("/")
def root():
    return {"message": "Welcome to Ferrum Webhook Relay!"}

@app.post("/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = crud_user.get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    return crud_user.create_user(db, user.email, user.password)

@app.post("/webhooks", response_model=schemas.WebhookOut)
def create_webhook(webhook: schemas.WebhookCreate,
                    db: Session = Depends(get_db)):
    db_webhook = crud_webhook.create_webhook(db, user_id=1, url=webhook.url, event_type=webhook.event_type)

    delete_cache("webhooks:user:1")  # Invalidate cache for this user

    return db_webhook


@app.get("/webhooks", response_model=list[schemas.WebhookOut])
def list_webhooks(db: Session = Depends(get_db)):
    cache_key = "webhooks:user:1"  # TEMP: we don’t have auth yet
    cached_webhooks = get_cache(cache_key)
    if cached_webhooks:
        logger.info(
            "webhooks_cache_hit",
            extra={"service": "gateway"}
        )
        return cached_webhooks

    webhooks = crud_webhook.get_webhooks(db)
    serialized = [
        { "id": webhook.id, "url": webhook.url, "event_type": webhook.event_type}
        for webhook in webhooks
    ] 
    
    set_cache(cache_key, serialized)
    return serialized

@app.post("/events")
def create_event(
    request: Request,
    event: schemas.EventCreate,
    db: Session = Depends(get_db)
):
    request_id = request.state.request_id
    db_event = crud_event.create_event(db, user_id=1, payload=event.payload, event_type=event.event_type)

    push_event("event_queue", {
        "event_id": db_event.id,
        "event_type": db_event.event_type,
        "request_id": request_id
    })

    logger.info(
        "event_created",
        extra={"service": "gateway", "request_id": request_id, "event_id": db_event.id}
    )

    return {"event_id": db_event.id}