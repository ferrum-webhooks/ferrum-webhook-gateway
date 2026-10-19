# file: app/schemas.py

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, AnyHttpUrl, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    id: int
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class WebhookCreate(BaseModel):
    url: AnyHttpUrl
    event_type: str = Field(min_length=1, max_length=128)


class WebhookUpdate(BaseModel):
    url: Optional[AnyHttpUrl] = None
    event_type: Optional[str] = Field(default=None, min_length=1, max_length=128)


class WebhookOut(BaseModel):
    id: int
    url: AnyHttpUrl
    event_type: str

    model_config = ConfigDict(from_attributes=True)


class WebhookDetail(WebhookOut):
    """Includes the signing secret; only returned on create/get-by-id to the owner."""
    secret: str


class EventCreate(BaseModel):
    payload: Dict[str, Any]
    event_type: str = Field(min_length=1, max_length=128)


class EventAccepted(BaseModel):
    event_id: str
    status: str
    deliveries: int


class EventOut(BaseModel):
    event_id: str
    event_type: str
    status: str
    created_at: datetime
    payload: Optional[Dict[str, Any]] = None


class DeliveryAttemptOut(BaseModel):
    attempt: int
    status: str
    response_code: Optional[int] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    attempted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliveryOut(BaseModel):
    id: int
    event_id: str
    webhook_id: int
    status: str
    retries: int
    response_code: Optional[int] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    attempted_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    attempts: Optional[List[DeliveryAttemptOut]] = None


class ReplayOut(BaseModel):
    event_id: str
    replayed_deliveries: int
