"""Pydantic schemas for notifications and customer payment reminders."""

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Template Schemas
# ---------------------------------------------------------------------------

class NotificationTemplateBase(BaseModel):
    name: str = Field(..., max_length=100)
    channel: str = Field(..., description="sms, email, in_app")
    subject: Optional[str] = Field(None, max_length=200)
    body_template: str = Field(...)
    variables: Optional[str] = None
    is_active: bool = True


class NotificationTemplateCreate(NotificationTemplateBase):
    pass


class NotificationTemplateResponse(NotificationTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# In-App Staff Notification Schemas
# ---------------------------------------------------------------------------

class InAppNotificationItem(BaseModel):
    id: str
    title: str
    message: str
    type: str = Field("info", description="info, warning, critical, success")
    status: str = Field("unread", description="unread, read")
    link: Optional[str] = None
    created_at: datetime


class InAppNotificationListResponse(BaseModel):
    unread_count: int
    items: List[InAppNotificationItem]


class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[str]] = None  # None = mark all


# ---------------------------------------------------------------------------
# Customer SMS Reminder Schemas
# ---------------------------------------------------------------------------

class ReminderCandidate(BaseModel):
    contract_id: int
    reference: str
    customer: str
    cid: Optional[str] = None
    mobile: Optional[str] = None
    region: Optional[str] = None
    cost_center: Optional[str] = None
    item: Optional[str] = None
    brand: Optional[str] = None
    balance_due: float
    overall_outstanding: float
    months_left: Optional[int] = None
    aging_bucket: str
    alert: str
    rendered_message: str


class ReminderPreviewResponse(BaseModel):
    total_eligible: int
    with_mobile_count: int
    missing_mobile_count: int
    total_balance_due: float
    candidates: List[ReminderCandidate]
    templates: List[NotificationTemplateResponse]


class SendRemindersRequest(BaseModel):
    contract_ids: List[int] = Field(..., min_length=1)
    template_id: Optional[int] = None
    custom_message_template: Optional[str] = None


class SendRemindersResponse(BaseModel):
    total_targeted: int
    sent_count: int
    failed_count: int
    skipped_no_phone: int
    message: str


class NotificationHistoryItem(BaseModel):
    id: int
    recipient_type: str
    recipient_id: str
    channel: str
    subject: Optional[str] = None
    body: str
    status: str
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationHistoryResponse(BaseModel):
    total: int
    items: List[NotificationHistoryItem]
