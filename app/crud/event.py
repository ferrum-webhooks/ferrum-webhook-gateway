# file: app/crud/event.py

from sqlalchemy.orm import Session
from app import models


def create_event(db: Session, user_id: int, payload: dict, event_type: str):
    event = models.Event(
        user_id=user_id,
        payload=payload,
        status="pending",
        event_type=event_type
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return event
