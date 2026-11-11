"""API endpoints for notifications, staff in-app alerts, and customer SMS payment reminders."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_not_must_change_password, require_role
from app.db.session import get_session
from app.models import User, UserRole
from app.schemas.notifications import (
    InAppNotificationListResponse,
    MarkReadRequest,
    NotificationHistoryResponse,
    NotificationTemplateResponse,
    ReminderPreviewResponse,
    SendRemindersRequest,
    SendRemindersResponse,
)
from app.services import notification_service

router = APIRouter()


# ---------------------------------------------------------------------------
# In-App Staff Notifications
# ---------------------------------------------------------------------------

@router.get("/in-app", response_model=InAppNotificationListResponse)
async def get_in_app_notifications(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """
    Get in-app notifications for the currently logged-in user / finance staff.
    Includes persistent staff alerts and system status notifications.
    """
    return await notification_service.get_in_app_notifications(
        session=session,
        user_id=current_user.id,
    )


@router.post("/in-app/mark-read")
async def mark_in_app_notifications_read(
    payload: MarkReadRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """
    Mark one, several, or all in-app notifications as read.
    """
    count = await notification_service.mark_in_app_read(
        session=session,
        user_id=current_user.id,
        notification_ids=payload.notification_ids,
    )
    return {"message": "Notifications marked as read", "updated_count": count}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=List[NotificationTemplateResponse])
async def list_notification_templates(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """
    List active SMS / email reminder templates.
    """
    return await notification_service.list_templates(session=session)


# ---------------------------------------------------------------------------
# Customer Reminders (SMS)
# ---------------------------------------------------------------------------

@router.get("/reminders/candidates", response_model=ReminderPreviewResponse)
async def get_reminder_candidates(
    aging_bucket: Optional[str] = Query("all", description="all, 0-30, 31-60, 61-90, 91-120, 120+, critical"),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None, description="all, internal, external"),
    min_balance: float = Query(1.0, ge=0),
    template_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """
    Preview eligible overdue customers for payment reminders with rendered message text.
    """
    return await notification_service.get_reminder_candidates(
        session=session,
        aging_bucket=aging_bucket,
        region=region,
        channel=channel,
        min_balance=min_balance,
        template_id=template_id,
    )


@router.post("/reminders/send", response_model=SendRemindersResponse)
async def send_customer_reminders(
    payload: SendRemindersRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.FINANCE_UPLOADER)),
):
    """
    Dispatch SMS reminders to customers for the specified contract IDs.
    """
    if not payload.contract_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one contract ID must be selected to send reminders.",
        )

    return await notification_service.send_customer_reminders(
        session=session,
        contract_ids=payload.contract_ids,
        template_id=payload.template_id,
        custom_template=payload.custom_message_template,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history", response_model=NotificationHistoryResponse)
async def get_notification_history(
    channel: Optional[str] = Query(None, description="all, sms, email"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """
    View history log of dispatched notifications.
    """
    return await notification_service.get_notification_history(
        session=session,
        channel=channel,
        limit=limit,
        offset=offset,
    )

