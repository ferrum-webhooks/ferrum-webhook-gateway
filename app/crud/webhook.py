# file: app/crud/webhook.py

from sqlalchemy.orm import Session
from app import models


def create_webhook(db: Session, user_id: int, url: str, event_type: str):
    webhook = models.Webhook(
        user_id=user_id,
        url=url,
        event_type=event_type
    )

    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return webhook


def get_webhooks(db: Session):
    return db.query(models.Webhook).all()
