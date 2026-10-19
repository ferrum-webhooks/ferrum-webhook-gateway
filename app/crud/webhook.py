# file: app/crud/webhook.py

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from app import models
from app.security import generate_webhook_secret


def create_webhook(db: Session, user_id: int, url: str, event_type: str):
    webhook = models.Webhook(
        user_id=user_id,
        url=str(url),
        event_type=event_type,
        secret=generate_webhook_secret(),
    )

    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return webhook


def get_webhooks(db: Session, user_id: int):
    return (db.query(models.Webhook)
            .filter(models.Webhook.user_id == user_id, models.Webhook.deleted_at.is_(None))
            .order_by(models.Webhook.id)
            .all())


def get_webhook(db: Session, user_id: int, webhook_id: int) -> Optional[models.Webhook]:
    return (db.query(models.Webhook)
            .filter(models.Webhook.id == webhook_id, models.Webhook.user_id == user_id,
                    models.Webhook.deleted_at.is_(None))
            .first())


def update_webhook(db: Session, webhook: models.Webhook, url=None, event_type=None):
    if url is not None:
        webhook.url = str(url)
    if event_type is not None:
        webhook.event_type = event_type
    db.commit()
    db.refresh(webhook)
    return webhook


def delete_webhook(db: Session, webhook: models.Webhook):
    """Soft delete: delivery history keeps referencing the row. Undelivered work is cancelled."""
    (db.query(models.Delivery)
     .filter(models.Delivery.webhook_id == webhook.id,
             models.Delivery.status.in_(["pending", "retrying"]))
     .update({"status": "cancelled", "next_retry_at": None}, synchronize_session=False))
    webhook.deleted_at = datetime.now(timezone.utc)
    db.commit()
