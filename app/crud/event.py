# file: app/crud/event.py

from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.security import new_event_public_id
from app.tracing import current_traceparent


def get_event(db: Session, user_id: int, public_id: str) -> Optional[models.Event]:
    return (db.query(models.Event)
            .filter(models.Event.public_id == public_id, models.Event.user_id == user_id)
            .first())


def get_event_by_idempotency_key(db: Session, user_id: int, key: str) -> Optional[models.Event]:
    return (db.query(models.Event)
            .filter(models.Event.user_id == user_id, models.Event.idempotency_key == key)
            .first())


def list_events(db: Session, user_id: int, limit: int, before_id: Optional[int] = None):
    q = db.query(models.Event).filter(models.Event.user_id == user_id)
    if before_id is not None:
        q = q.filter(models.Event.id < before_id)
    return q.order_by(models.Event.id.desc()).limit(limit).all()


def count_deliveries(db: Session, event_id: int) -> int:
    return db.query(models.Delivery).filter(models.Delivery.event_id == event_id).count()


def create_event(db: Session, user_id: int, payload: dict, event_type: str,
                 request_id: Optional[str] = None,
                 idempotency_key: Optional[str] = None) -> Tuple[models.Event, int]:
    """Stores the event, one delivery per matching webhook, and one outbox row per delivery
    in a single transaction. Nothing touches Redis here: the relay publishes the outbox rows.

    Raises IntegrityError if (user_id, idempotency_key) already exists; the caller re-reads it.
    """
    event = models.Event(
        public_id=new_event_public_id(),
        user_id=user_id,
        payload=payload,
        status="pending",
        event_type=event_type,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise

    webhooks = (db.query(models.Webhook)
                .filter(models.Webhook.user_id == user_id,
                        models.Webhook.event_type == event_type,
                        models.Webhook.deleted_at.is_(None))
                .all())
    if not webhooks:
        event.status = "no_subscribers"

    tp = current_traceparent()
    deliveries = [models.Delivery(event_id=event.id, webhook_id=w.id, status="pending", retries=0, traceparent=tp)
                  for w in webhooks]
    db.add_all(deliveries)
    db.flush()                        # one batched INSERT ... RETURNING for all deliveries
    db.add_all([models.Outbox(delivery_id=d.id, request_id=request_id, traceparent=tp) for d in deliveries])

    db.commit()                       # session has expire_on_commit=False: no refresh query needed
    return event, len(webhooks)


def replay_event(db: Session, event: models.Event, request_id: Optional[str] = None) -> int:
    """Re-queues every failed/dead-lettered delivery of the event, atomically with its
    outbox rows. Successful deliveries are left alone."""
    deliveries = (db.query(models.Delivery)
                  .filter(models.Delivery.event_id == event.id,
                          models.Delivery.status.in_(["dead_letter", "failed"]))
                  .with_for_update()
                  .all())
    tp = current_traceparent()
    for d in deliveries:
        d.traceparent = tp or d.traceparent
        d.status = "pending"
        d.retries = 0
        d.next_retry_at = None
        d.locked_until = None
        d.moved_to_dlq = 0
        d.error_message = None
        db.add(models.Outbox(delivery_id=d.id, request_id=request_id, traceparent=d.traceparent))
    if deliveries:
        event.status = "pending"
    db.commit()
    return len(deliveries)
