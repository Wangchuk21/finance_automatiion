"""Dashboard API endpoints for KPIs, charts, and analytics."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Contract, Installment, InstallmentStatus, ContractState, Upload, UploadStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
):
    """Get all dashboard data in one call."""
    # Get all data in parallel-ish fashion
    kpis = await get_kpis_data(session)
    regions = await get_regions_data(session)
    aging = await get_aging_data(session)
    trend = await get_trend_data(session)
    attention = await get_attention_data(session)
    recent_uploads = await get_recent_uploads_data(session)

    # Get latest upload date
    latest_upload = await session.execute(
        select(Upload.as_of_date)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.upload_time.desc())
        .limit(1)
    )
    last_upload_date = latest_upload.scalar_one_or_none()

    return {
        "kpis": kpis,
        "regions": regions,
        "aging": aging,
        "trend": trend,
        "attention": attention,
        "recentUploads": recent_uploads,
        "asOfDate": last_upload_date.isoformat() if last_upload_date else None,
        "lastUploadAt": last_upload_date.isoformat() if last_upload_date else None,
    }


async def get_kpis_data(session: AsyncSession) -> List[dict]:
    """Calculate KPI values from database."""
    # Total receivable (sum of due_amount for pending/partial installments)
    receivable_result = await session.execute(
        select(func.coalesce(func.sum(Installment.due_amount), 0))
        .where(Installment.status.in_([InstallmentStatus.PENDING, InstallmentStatus.PARTIAL]))
    )
    total_receivable = receivable_result.scalar() or Decimal("0")

    # Total collected (sum of received_amount)
    collected_result = await session.execute(
        select(func.coalesce(func.sum(Installment.received_amount), 0))
    )
    total_collected = collected_result.scalar() or Decimal("0")

    # Total overdue (due - received for overdue/partial installments)
    overdue_result = await session.execute(
        select(func.coalesce(func.sum(Installment.due_amount - Installment.received_amount), 0))
        .where(Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]))
    )
    total_overdue = overdue_result.scalar() or Decimal("0")

    # Critical accounts (contracts with overdue installments)
    critical_result = await session.execute(
        select(func.count(func.distinct(Installment.contract_id)))
        .where(Installment.status == InstallmentStatus.OVERDUE)
    )
    critical_accounts = critical_result.scalar() or 0

    # Previous period comparison (last upload vs current)
    # For now, return basic values
    return [
        {
            "title": "Total Receivable",
            "value": format_nu(total_receivable),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Collected",
            "value": format_nu(total_collected),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Overdue",
            "value": format_nu(total_overdue),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Critical Accounts",
            "value": str(critical_accounts),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
    ]


async def get_regions_data(session: AsyncSession) -> List[dict]:
    """Get receivable/collected/overdue by region."""
    result = await session.execute(
        select(
            Contract.region,
            func.coalesce(func.sum(Installment.due_amount), 0).label("total_due"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total_received"),
            func.coalesce(
                func.sum(
                    case(
                        (Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]),
                         Installment.due_amount - Installment.received_amount),
                        else_=0
                    )
                ),
                0
            ).label("total_overdue"),
        )
        .join(Installment, Installment.contract_id == Contract.id)
        .where(Contract.region.isnot(None))
        .group_by(Contract.region)
        .order_by(func.sum(Installment.due_amount).desc())
    )
    rows = result.all()
    return [
        {
            "region": row.region or "Unknown",
            "receivable": float(row.total_due),
            "collected": float(row.total_received),
            "overdue": float(row.total_overdue),
        }
        for row in rows
    ]


async def get_aging_data(session: AsyncSession) -> List[dict]:
    """Get aging buckets (0-30, 31-60, 61-90, 91-120, 120+ days)."""
    # Get the latest as_of_date from confirmed uploads
    latest_as_of = await session.execute(
        select(Upload.as_of_date)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.upload_time.desc())
        .limit(1)
    )
    as_of_date = latest_as_of.scalar_one_or_none()

    if not as_of_date:
        return []

    # Calculate aging for overdue installments
    # Use PostgreSQL date arithmetic: (today - due_month) gives interval, extract days
    today = as_of_date
    result = await session.execute(
        select(
            case(
                ((today - Installment.due_month) <= 30, "0-30"),
                ((today - Installment.due_month) <= 60, "31-60"),
                ((today - Installment.due_month) <= 90, "61-90"),
                ((today - Installment.due_month) <= 120, "91-120"),
                else_="120+"
            ).label("bucket"),
            func.coalesce(func.sum(Installment.due_amount - Installment.received_amount), 0).label("amount"),
            func.count().label("count"),
        )
        .where(Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]))
        .where(Installment.due_amount > Installment.received_amount)
        .group_by("bucket")
    )
    rows = result.all()

    # Ensure all buckets exist
    bucket_order = ["0-30", "31-60", "61-90", "91-120", "120+"]
    data = {row.bucket: {"amount": float(row.amount), "count": row.count} for row in rows}

    return [
        {"bucket": b, "amount": data.get(b, {}).get("amount", 0), "count": data.get(b, {}).get("count", 0)}
        for b in bucket_order
    ]


async def get_trend_data(session: AsyncSession) -> List[dict]:
    """Get collection trend by month (last 6 months)."""
    # Get data for last 6 months from installments
    # Use PostgreSQL's to_char for date formatting
    result = await session.execute(
        select(
            func.to_char(Installment.due_month, "YYYY-MM").label("month"),
            func.coalesce(
                func.sum(case((Contract.payment_type == "Internal", Installment.received_amount), else_=0)),
                0
            ).label("internal"),
            func.coalesce(
                func.sum(case((Contract.payment_type == "External", Installment.received_amount), else_=0)),
                0
            ).label("external"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total"),
        )
        .join(Contract, Contract.id == Installment.contract_id)
        .where(Installment.due_month >= date.today() - timedelta(days=180))
        .group_by("month")
        .order_by("month")
    )
    rows = result.all()

    return [
        {
            "month": row.month,
            "internal": float(row.internal),
            "external": float(row.external),
            "total": float(row.total),
        }
        for row in rows
    ]


async def get_attention_data(session: AsyncSession) -> List[dict]:
    """Get items needing attention (missing contracts, validation warnings)."""
    items = []

    # Contracts in missing_review state
    review_result = await session.execute(
        select(func.count())
        .where(Contract.state == ContractState.MISSING_REVIEW)
    )
    review_count = review_result.scalar() or 0

    if review_count > 0:
        items.append({
            "id": "pending_review",
            "type": "pending_review",
            "title": "Contracts pending review",
            "description": f"{review_count} contracts flagged for manual review",
            "count": review_count,
            "actionLabel": "Review contracts",
        })

    return items


async def get_recent_uploads_data(session: AsyncSession) -> List[dict]:
    """Get recent uploads for the dashboard."""
    result = await session.execute(
        select(Upload)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.upload_time.desc())
        .limit(5)
    )
    uploads = result.scalars().all()

    return [
        {
            "id": u.id,
            "file_name": u.file_name,
            "date": u.upload_time.strftime("%d %b %Y"),
            "status": u.status.value,
            "contracts": (
                json.loads(u.summary).get("upsert_result", {}).get("contracts_created", 0) +
                json.loads(u.summary).get("upsert_result", {}).get("contracts_updated", 0)
            ) if u.summary else 0,
        }
        for u in uploads
    ]


@router.get("/kpis")
async def get_kpis(session: AsyncSession = Depends(get_session)):
    return await get_kpis_data(session)


@router.get("/regions")
async def get_regions(session: AsyncSession = Depends(get_session)):
    return await get_regions_data(session)


@router.get("/aging")
async def get_aging(session: AsyncSession = Depends(get_session)):
    return await get_aging_data(session)


@router.get("/trend")
async def get_trend(session: AsyncSession = Depends(get_session)):
    return await get_trend_data(session)


@router.get("/attention")
async def get_attention(session: AsyncSession = Depends(get_session)):
    return await get_attention_data(session)


@router.get("/uploads")
async def get_recent_uploads(session: AsyncSession = Depends(get_session)):
    return await get_recent_uploads_data(session)


def format_nu(amount: Decimal) -> str:
    """Format amount in Ngultrum format (Nu. 1,22,64,000)."""
    if amount == 0:
        return "Nu. 0"
    # Format without commas first, then apply Indian grouping
    s = f"{amount:.2f}".split(".")
    integer_part = s[0].replace(",", "")  # Remove any existing commas
    # Indian grouping: 1,22,64,000 (3-2-2-2...)
    parts = []
    while len(integer_part) > 3:
        parts.append(integer_part[-3:])
        integer_part = integer_part[:-3]
    parts.append(integer_part)
    formatted = ",".join(reversed(parts))
    return f"Nu. {formatted}"