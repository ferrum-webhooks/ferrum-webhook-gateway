# file: app/main.py

from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import time
import logging

from app import schemas
from app.deps import get_db
from app.cache import get_cache, set_cache, delete_cache, push_event

from app.crud import user as crud_user
from app.crud import webhook as crud_webhook
from app.crud import event as crud_event

logging.basicConfig(level=logging.INFO)

app = FastAPI()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logging.info(f"{request.method} {request.url.path} completed in {process_time:.4f}s")
    return response

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
        logging.info("CACHE HIT")
        return cached_webhooks
    logging.info("CACHE MISS")

    webhooks = crud_webhook.get_webhooks(db)
    serialized = [
        { "id": webhook.id, "url": webhook.url, "event_type": webhook.event_type}
        for webhook in webhooks
    ] 
    
    set_cache(cache_key, serialized)
    return serialized

@app.post("/events")
def create_event(
    event: schemas.EventCreate,
    db: Session = Depends(get_db)
):
    db_event = crud_event.create_event(db, user_id=1, payload=event.payload, event_type=event.event_type)

    push_event("event_queue", {
        "event_id": db_event.id,
    })

    return {"event_id": db_event.id}