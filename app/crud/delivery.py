# file: app/crud/delivery.py

from typing import List, Optional

from sqlalchemy.orm import Session

from app import models


def list_for_event(db: Session, event: models.Event) -> List[models.Delivery]:
    return (db.query(models.Delivery)
            .filter(models.Delivery.event_id == event.id)
            .order_by(models.Delivery.id)
            .all())


def list_for_user(db: Session, user_id: int, limit: int, status: Optional[str] = None,
                  before_id: Optional[int] = None):
    q = (db.query(models.Delivery, models.Event.public_id)
         .join(models.Event, models.Event.id == models.Delivery.event_id)
         .filter(models.Event.user_id == user_id))
    if status:
        q = q.filter(models.Delivery.status == status)
    if before_id is not None:
        q = q.filter(models.Delivery.id < before_id)
    return q.order_by(models.Delivery.id.desc()).limit(limit).all()


def attempts(db: Session, delivery_id: int):
    return (db.query(models.DeliveryAttempt)
            .filter(models.DeliveryAttempt.delivery_id == delivery_id)
            .order_by(models.DeliveryAttempt.attempt)
            .all())
