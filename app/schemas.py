# file: app/schemas.py

from pydantic import BaseModel, EmailStr, AnyHttpUrl
from typing import Dict, Any

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True

class WebhookCreate(BaseModel):
    url: AnyHttpUrl
    event_type: str

class WebhookOut(BaseModel):
    id: int
    url: AnyHttpUrl
    event_type: str

    class Config:
        from_attributes = True

class EventCreate(BaseModel):
    payload: Dict[str, Any]
    event_type: str
