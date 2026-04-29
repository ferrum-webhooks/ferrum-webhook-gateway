# file: app/crud/user.py

from sqlalchemy.orm import Session
from app import models
from app.security import hash_password


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, email: str, password: str):
    db_user = models.User(
        email=email,
        password_hash=hash_password(password)
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user
