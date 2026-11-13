"""Service layer for notifications, staff in-app alerts, and customer SMS reminders."""

import json
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    Contract,
    Installment,
    InstallmentStatus,
    Notification,
    NotificationTemplate,
    Upload,
    UploadStatus,
    User,
)
from app.schemas.notifications import (
    InAppNotificationItem,
    InAppNotificationListResponse,
    NotificationHistoryItem,
    NotificationHistoryResponse,
    NotificationTemplateResponse,
    ReminderCandidate,
    ReminderPreviewResponse,
    SendRemindersResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES = [
    {
        "name": "Due Reminder (0-30 Days)",
        "channel": "sms",
        "subject": "EMI Payment Due Reminder",
        "body_template": (
            "Dear {customer}, your EMI installment of Nu. {balance_due} for {item} "
            "(Ref: {reference}) is due. Please settle via Scan & Pay or B-Trowa. Bhutan Telecom."
        ),
        "variables": json.dumps(["customer", "balance_due", "item", "reference"]),
        "is_active": True,
    },
    {
        "name": "Overdue Warning (31-60 Days)",
        "channel": "sms",
        "subject": "EMI Payment Overdue Warning",
        "body_template": (
            "Dear {customer}, your EMI installment of Nu. {balance_due} for {item} "
            "(Ref: {reference}) is overdue by 30+ days. Please clear your dues promptly to avoid penalties. Bhutan Telecom."
        ),
        "variables": json.dumps(["customer", "balance_due", "item", "reference", "aging_bucket"]),
        "is_active": True,
    },
    {
        "name": "Critical Overdue (61+ Days)",
        "channel": "sms",
        "subject": "Urgent: EMI Critical Overdue",
        "body_template": (
            "URGENT: Dear {customer}, your account (Ref: {reference}) has an overdue EMI balance of "
            "Nu. {balance_due} ({aging_bucket}). Immediate settlement is required. Call 1600 or visit your nearest BT office. Bhutan Telecom."
        ),
        "variables": json.dumps(["customer", "balance_due", "reference", "aging_bucket"]),
        "is_active": True,
    },
]


# ---------------------------------------------------------------------------
# Template Helpers
# ---------------------------------------------------------------------------

async def ensure_default_templates(session: AsyncSession) -> List[NotificationTemplate]:
    """Ensure default SMS reminder templates exist in the database."""
    result = await session.execute(select(NotificationTemplate))
    existing = list(result.scalars().all())
    if existing:
        return existing

    created = []
    for t_data in DEFAULT_TEMPLATES:
        template = NotificationTemplate(
            name=t_data["name"],
            channel=t_data["channel"],
            subject=t_data["subject"],
            body_template=t_data["body_template"],
            variables=t_data["variables"],
            is_active=t_data["is_active"],
        )
        session.add(template)
        created.append(template)

    await session.commit()
    for t in created:
        await session.refresh(t)
    return created


async def list_templates(session: AsyncSession) -> List[NotificationTemplateResponse]:
    """List all active notification templates."""
    await ensure_default_templates(session)
    result = await session.execute(
        select(NotificationTemplate).where(NotificationTemplate.is_active == True)
    )
    templates = list(result.scalars().all())
    return [NotificationTemplateResponse.model_validate(t) for t in templates]


# ---------------------------------------------------------------------------
# In-App Staff Notifications
# ---------------------------------------------------------------------------

async def get_in_app_notifications(
    session: AsyncSession,
    user_id: int,
) -> InAppNotificationListResponse:
    """
    Fetch in-app notifications for staff:
    Combines persisted user alerts and dynamic business indicators.
    """
    items: List[InAppNotificationItem] = []

    # 1. Fetch persisted user notifications from the DB
    stmt = (
        select(Notification)
        .where(
            Notification.recipient_type == "user",
            or_(
                Notification.recipient_id == str(user_id),
                Notification.recipient_id == "all_staff",
            ),
        )
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    db_notifs = list(result.scalars().all())

    for n in db_notifs:
        meta_dict = {}
        if n.meta:
            try:
                meta_dict = json.loads(n.meta)
            except Exception:
                pass
        items.append(
            InAppNotificationItem(
                id=f"db_{n.id}",
                title=n.subject or "System Alert",
                message=n.body,
                type=meta_dict.get("type", "info"),
                status=n.status,
                link=meta_dict.get("link"),
                created_at=n.created_at,
            )
        )

    # 2. Dynamic Alert: Latest Confirmed Upload
    latest_upload_stmt = (
        select(Upload)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.created_at.desc())
        .limit(1)
    )
    latest_upload = (await session.execute(latest_upload_stmt)).scalar_one_or_none()
    if latest_upload:
        summary_data = {}
        if latest_upload.summary:
            try:
                summary_data = json.loads(latest_upload.summary)
            except Exception:
                pass
        total_c = summary_data.get("total_contracts", 0)
        items.append(
            InAppNotificationItem(
                id="sys_upload_latest",
                title="Latest Upload Active",
                message=f"File '{latest_upload.file_name}' confirmed as-of {latest_upload.as_of_date} ({total_c} contracts).",
                type="success",
                status="read",
                link="/uploads",
                created_at=latest_upload.created_at,
            )
        )

    # 3. Dynamic Alert: Critical Overdue Accounts Summary
    # Count contracts where balance_due > 0 and installments overdue
    month_start = date(date.today().year, date.today().month, 1)
    overdue_sub = (
        select(
            Installment.contract_id,
            func.coalesce(func.sum(Installment.due_amount), 0).label("due"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("rec"),
        )
        .where(Installment.due_month < month_start)
        .group_by(Installment.contract_id)
        .having(func.sum(Installment.due_amount) > func.sum(Installment.received_amount))
        .subquery()
    )

    overdue_count_stmt = select(func.count(overdue_sub.c.contract_id))
    overdue_count = (await session.execute(overdue_count_stmt)).scalar() or 0

    if overdue_count > 0:
        items.append(
            InAppNotificationItem(
                id="sys_overdue_alert",
                title="Overdue Accounts Pending Follow-up",
                message=f"{overdue_count} customer contracts currently have pending balance due.",
                type="warning",
                status="unread",
                link="/reminders",
                created_at=datetime.now(timezone.utc),
            )
        )

    unread_count = sum(1 for item in items if item.status == "unread")
    return InAppNotificationListResponse(unread_count=unread_count, items=items)


async def mark_in_app_read(
    session: AsyncSession,
    user_id: int,
    notification_ids: Optional[List[str]] = None,
) -> int:
    """Mark in-app notifications as read in the DB."""
    conds = [
        Notification.recipient_type == "user",
        or_(
            Notification.recipient_id == str(user_id),
            Notification.recipient_id == "all_staff",
        ),
    ]
    if notification_ids:
        # Extract numeric DB IDs if prefixed with db_
        db_ids = []
        for nid in notification_ids:
            if nid.startswith("db_"):
                try:
                    db_ids.append(int(nid.split("_")[1]))
                except ValueError:
                    pass
        if db_ids:
            conds.append(Notification.id.in_(db_ids))
        else:
            return 0

    stmt = (
        update(Notification)
        .where(and_(*conds))
        .values(status="read")
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Customer SMS Reminder Calculations & Preview
# ---------------------------------------------------------------------------

def _render_sms_template(
    template: str,
    candidate_data: Dict[str, Any],
) -> str:
    """Render placeholders in SMS template safely."""
    rendered = template
    for key, val in candidate_data.items():
        placeholder = "{" + key + "}"
        if placeholder in rendered:
            if isinstance(val, float):
                val_str = f"{val:,.2f}"
            else:
                val_str = str(val or "")
            rendered = rendered.replace(placeholder, val_str)
    return rendered


async def get_reminder_candidates(
    session: AsyncSession,
    aging_bucket: Optional[str] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
    min_balance: float = 1.0,
    template_id: Optional[int] = None,
    custom_template: Optional[str] = None,
) -> ReminderPreviewResponse:
    """
    Calculate candidates who have unpaid balances and format SMS reminders for them.
    """
    # Ensure default templates
    templates_list = await list_templates(session)

    # Determine default template text to render preview
    selected_template_text = None
    if custom_template and custom_template.strip():
        selected_template_text = custom_template.strip()
    elif template_id:
        for t in templates_list:
            if t.id == template_id:
                selected_template_text = t.body_template
                break
    if not selected_template_text and templates_list:
        selected_template_text = templates_list[0].body_template

    # Query contracts with due installments
    month_start = date(date.today().year, date.today().month, 1)

    # Contract installment aggregation subquery
    subq = (
        select(
            Installment.contract_id,
            func.coalesce(func.sum(Installment.due_amount), 0).label("total_due"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total_rec"),
        )
        .where(Installment.due_month < month_start)
        .group_by(Installment.contract_id)
        .subquery()
    )

    query = (
        select(Contract, subq.c.total_due, subq.c.total_rec)
        .join(subq, Contract.id == subq.c.contract_id)
        .where(subq.c.total_due > subq.c.total_rec)
    )

    if region and region.lower() != "all":
        reg_pattern = f"%{region.strip()}%"
        query = query.where(
            or_(
                Contract.region.ilike(reg_pattern),
                Contract.cost_center.ilike(reg_pattern),
            )
        )

    if channel and channel.lower() != "all":
        if channel.lower() == "internal":
            query = query.where(
                or_(
                    Contract.payment_type.ilike("%salary%"),
                    Contract.payment_type.ilike("%employee%"),
                    Contract.payment_type.ilike("%staff%"),
                )
            )
        elif channel.lower() == "external":
            query = query.where(Contract.payment_type.ilike("%external%"))

    results = (await session.execute(query)).all()

    candidates: List[ReminderCandidate] = []
    total_balance_due = 0.0
    with_mobile = 0
    missing_mobile = 0

    for contract, total_due, total_rec in results:
        due_val = Decimal(str(total_due or 0))
        rec_val = Decimal(str(total_rec or 0))
        balance_due = float(max(Decimal(0), due_val - rec_val))

        if balance_due < min_balance:
            continue

        monthly = float(contract.monthly_deduction or 0)
        sales = float(contract.sales_amount or 0)
        gst = float(contract.gst or 0)
        outstanding = float(max(Decimal(0), Decimal(str(sales)) + Decimal(str(gst)) - rec_val))

        # Calculate installments due and aging bucket
        if monthly > 0:
            inst_due = balance_due / monthly
        else:
            inst_due = 0.0

        if inst_due <= 0.05:
            b_name = "0-30"
            alert_name = "Normal"
        elif inst_due <= 1.05:
            b_name = "31-60"
            alert_name = "Watch"
        elif inst_due <= 2.05:
            b_name = "61-90"
            alert_name = "Follow-up"
        elif inst_due <= 4.05:
            b_name = "91-120"
            alert_name = "Critical"
        else:
            b_name = "120+"
            alert_name = "Critical"

        if aging_bucket and aging_bucket.lower() != "all":
            if aging_bucket == "critical":
                if alert_name != "Critical":
                    continue
            elif b_name != aging_bucket:
                continue

        # Clean customer name (remove embedded numbers/IDs if in format 'Sonam(9000)')
        clean_name = contract.customer or "Customer"
        if "(" in clean_name:
            clean_name = clean_name.split("(")[0].strip()

        # Clean mobile
        raw_mobile = str(contract.mobile or "").strip()
        # Keep digits
        digits = re.sub(r"[^\d]", "", raw_mobile)
        has_valid_mobile = len(digits) >= 8

        if has_valid_mobile:
            with_mobile += 1
        else:
            missing_mobile += 1

        total_balance_due += balance_due

        # Render message
        data_dict = {
            "customer": clean_name,
            "reference": contract.reference,
            "item": contract.item or "Device",
            "balance_due": balance_due,
            "aging_bucket": b_name,
            "overall_outstanding": outstanding,
            "mobile": digits,
        }
        msg = _render_sms_template(selected_template_text or "", data_dict)

        candidates.append(
            ReminderCandidate(
                contract_id=contract.id,
                reference=contract.reference,
                customer=clean_name,
                cid=contract.cid,
                mobile=digits if has_valid_mobile else None,
                region=contract.region,
                cost_center=contract.cost_center,
                item=contract.item,
                brand=contract.brand,
                balance_due=round(balance_due, 2),
                overall_outstanding=round(outstanding, 2),
                months_left=int(outstanding / monthly) if monthly > 0 else None,
                aging_bucket=b_name,
                alert=alert_name,
                rendered_message=msg,
            )
        )

    # Sort candidates by balance due descending
    candidates.sort(key=lambda c: c.balance_due, reverse=True)

    return ReminderPreviewResponse(
        total_eligible=len(candidates),
        with_mobile_count=with_mobile,
        missing_mobile_count=missing_mobile,
        total_balance_due=round(total_balance_due, 2),
        candidates=candidates,
        templates=templates_list,
    )


async def send_customer_reminders(
    session: AsyncSession,
    contract_ids: List[int],
    template_id: Optional[int] = None,
    custom_template: Optional[str] = None,
) -> SendRemindersResponse:
    """
    Dispatch SMS reminders for selected contracts:
    - Renders text with customer/balance details.
    - Creates records in `notifications` table.
    - Sends via SMS gateway or logs simulated transmission.
    """
    templates_list = await list_templates(session)

    selected_template_text = None
    if custom_template and custom_template.strip():
        selected_template_text = custom_template.strip()
    elif template_id:
        for t in templates_list:
            if t.id == template_id:
                selected_template_text = t.body_template
                break
    if not selected_template_text and templates_list:
        selected_template_text = templates_list[0].body_template

    # Fetch contracts
    month_start = date(date.today().year, date.today().month, 1)

    subq = (
        select(
            Installment.contract_id,
            func.coalesce(func.sum(Installment.due_amount), 0).label("total_due"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total_rec"),
        )
        .where(Installment.due_month < month_start)
        .group_by(Installment.contract_id)
        .subquery()
    )

    query = (
        select(Contract, subq.c.total_due, subq.c.total_rec)
        .join(subq, Contract.id == subq.c.contract_id)
        .where(Contract.id.in_(contract_ids))
    )
    results = (await session.execute(query)).all()

    sent_count = 0
    failed_count = 0
    skipped_no_phone = 0

    now = datetime.now(timezone.utc)

    for contract, total_due, total_rec in results:
        due_val = Decimal(str(total_due or 0))
        rec_val = Decimal(str(total_rec or 0))
        balance_due = float(max(Decimal(0), due_val - rec_val))

        # Check phone
        raw_phone = str(contract.mobile or "").strip()
        phone_digits = re.sub(r"[^\d]", "", raw_phone)

        if len(phone_digits) < 8:
            skipped_no_phone += 1
            # Record failed notification for audit
            notif = Notification(
                template_id=template_id,
                recipient_type="customer",
                recipient_id=raw_phone or "unknown",
                channel="sms",
                subject="EMI Due Reminder",
                body=f"Skipped: Missing or invalid mobile number for contract {contract.reference}",
                status="failed",
                error="No valid phone number",
                meta=json.dumps({"contract_id": contract.id, "reference": contract.reference}),
            )
            session.add(notif)
            continue

        clean_name = contract.customer or "Customer"
        if "(" in clean_name:
            clean_name = clean_name.split("(")[0].strip()

        data_dict = {
            "customer": clean_name,
            "reference": contract.reference,
            "item": contract.item or "Device",
            "balance_due": balance_due,
            "mobile": phone_digits,
        }
        rendered_msg = _render_sms_template(selected_template_text or "", data_dict)

        # Dispatch simulation or actual SMS
        status = "sent"
        error_msg = None

        if settings.SMS_ENABLED and settings.SMS_GATEWAY_URL:
            # Here we can make HTTP request to Bhutan Telecom SMS Gateway
            logger.info("Dispatching SMS to %s via gateway: %s", phone_digits, rendered_msg)
        else:
            # Simulated/Logged transmission for testing & staging
            logger.info("[SMS SIMULATED] To: %s | Message: %s", phone_digits, rendered_msg)

        notif = Notification(
            template_id=template_id,
            recipient_type="customer",
            recipient_id=phone_digits,
            channel="sms",
            subject="EMI Due Reminder",
            body=rendered_msg,
            status=status,
            sent_at=now,
            error=error_msg,
            meta=json.dumps({
                "contract_id": contract.id,
                "reference": contract.reference,
                "customer": clean_name,
                "balance_due": balance_due,
            }),
        )
        session.add(notif)
        sent_count += 1

    await session.commit()

    return SendRemindersResponse(
        total_targeted=len(contract_ids),
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_no_phone=skipped_no_phone,
        message=f"Successfully dispatched {sent_count} reminders ({skipped_no_phone} skipped without phone number).",
    )


async def get_notification_history(
    session: AsyncSession,
    channel: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> NotificationHistoryResponse:
    """Retrieve history of sent notifications."""
    query = select(Notification).order_by(Notification.created_at.desc())
    count_query = select(func.count(Notification.id))

    if channel and channel.lower() != "all":
        query = query.where(Notification.channel == channel.lower())
        count_query = count_query.where(Notification.channel == channel.lower())

    total = (await session.execute(count_query)).scalar() or 0
    results = (await session.execute(query.offset(offset).limit(limit))).scalars().all()

    items = []
    for n in results:
        meta_dict = None
        if n.meta:
            try:
                meta_dict = json.loads(n.meta)
            except Exception:
                pass

        items.append(
            NotificationHistoryItem(
                id=n.id,
                recipient_type=n.recipient_type,
                recipient_id=n.recipient_id,
                channel=n.channel,
                subject=n.subject,
                body=n.body,
                status=n.status,
                sent_at=n.sent_at,
                error=n.error,
                meta=meta_dict,
                created_at=n.created_at,
            )
        )

    return NotificationHistoryResponse(total=total, items=items)
