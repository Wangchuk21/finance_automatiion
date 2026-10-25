"""Dashboard API endpoints for KPIs, charts, and analytics with date filtering."""

import csv
import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Contract, Installment, InstallmentStatus, ContractState, Upload, UploadStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def parse_month_param(val: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM or YYYY-MM-DD into the first day of that month."""
    if not val:
        return None
    val = val.strip()
    try:
        if len(val) == 7:  # YYYY-MM
            dt = datetime.strptime(val, "%Y-%m").date()
            return date(dt.year, dt.month, 1)
        elif len(val) >= 10:  # YYYY-MM-DD
            dt = datetime.strptime(val[:10], "%Y-%m-%d").date()
            return date(dt.year, dt.month, 1)
        else:
            dt = datetime.strptime(val[:7], "%Y-%m").date()
            return date(dt.year, dt.month, 1)
    except Exception:
        return None


def resolve_date_bounds(
    preset: Optional[str] = "all",
    from_str: Optional[str] = None,
    to_str: Optional[str] = None,
    ref_date: Optional[date] = None,
) -> Tuple[Optional[date], Optional[date]]:
    """
    Resolve preset and from/to into (from_date, to_date) where dates are the
    first day of the respective month. "all" = no bounds (None, None).
    Fiscal year = 1 July to 30 June (Bhutan).
    """
    ref = ref_date or date.today()
    p = (preset or "all").lower().strip()

    if p == "all":
        if from_str or to_str:
            return parse_month_param(from_str), parse_month_param(to_str)
        return None, None

    if p == "this_month":
        start = date(ref.year, ref.month, 1)
        return start, start

    if p == "last_month":
        if ref.month == 1:
            start = date(ref.year - 1, 12, 1)
        else:
            start = date(ref.year, ref.month - 1, 1)
        return start, start

    if p == "last_3_months":
        to_d = date(ref.year, ref.month, 1)
        y = ref.year
        m = ref.month - 2
        while m <= 0:
            m += 12
            y -= 1
        from_d = date(y, m, 1)
        return from_d, to_d

    if p == "this_fy":
        # Fiscal year = 1 July to 30 June (Bhutan)
        if ref.month >= 7:
            from_d = date(ref.year, 7, 1)
            to_d = date(ref.year + 1, 6, 1)
        else:
            from_d = date(ref.year - 1, 7, 1)
            to_d = date(ref.year, 6, 1)
        return from_d, to_d

    if p == "last_fy":
        if ref.month >= 7:
            from_d = date(ref.year - 1, 7, 1)
            to_d = date(ref.year, 6, 1)
        else:
            from_d = date(ref.year - 2, 7, 1)
            to_d = date(ref.year - 1, 6, 1)
        return from_d, to_d

    if p == "custom":
        return parse_month_param(from_str), parse_month_param(to_str)

    # Fallback to parsing from/to if provided
    return parse_month_param(from_str), parse_month_param(to_str)


def build_filter_conditions(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
    apply_date_filter: bool = True,
) -> list:
    """Build SQLAlchemy filter conditions for Installment joined with Contract."""
    conditions = []
    if apply_date_filter:
        if from_date is not None and to_date is not None:
            conditions.append(Installment.due_month.between(from_date, to_date))
        elif from_date is not None:
            conditions.append(Installment.due_month >= from_date)
        elif to_date is not None:
            conditions.append(Installment.due_month <= to_date)

    if region and region.strip():
        conditions.append(func.lower(Contract.region) == region.strip().lower())

    if channel and channel.strip():
        ch = channel.strip().lower()
        if ch == "internal":
            conditions.append(
                func.lower(Contract.payment_type).in_(["internal", "salary", "staff", "employee"]) |
                Contract.payment_type.ilike("%salary%") |
                Contract.payment_type.ilike("%employee%") |
                Contract.payment_type.ilike("%staff%") |
                Contract.payment_type.ilike("%internal%")
            )
        elif ch == "external":
            conditions.append(
                func.lower(Contract.payment_type).in_(["external", "customer"]) |
                Contract.payment_type.ilike("%external%") |
                Contract.payment_type.ilike("%customer%")
            )
        else:
            conditions.append(func.lower(Contract.payment_type) == ch)

    return conditions


@router.get("/")
async def get_dashboard(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all dashboard data in one call, filtered by date, region, and channel."""
    from_date, to_date = resolve_date_bounds(preset, from_, to)

    kpis_data = await get_kpis_data(session, from_date, to_date, region, channel)
    regions = await get_regions_data(session, from_date, to_date, region, channel)
    aging = await get_aging_data(session, from_date, to_date, region, channel)
    trend = await get_trend_data(session, from_date, to_date, region, channel)
    attention = await get_attention_data(session, region, channel)
    recent_uploads = await get_recent_uploads_data(session)
    tables = await get_contracts_table_data(session, from_date, to_date, region, channel)

    latest_upload = await session.execute(
        select(Upload.as_of_date)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.upload_time.desc())
        .limit(1)
    )
    last_upload_date = latest_upload.scalar_one_or_none()

    return {
        "kpis": kpis_data["kpis"],
        "summary": kpis_data["summary"],
        "regions": regions,
        "aging": aging,
        "trend": trend,
        "attention": attention,
        "recentUploads": recent_uploads,
        "tables": tables,
        "asOfDate": last_upload_date.isoformat() if last_upload_date else None,
        "lastUploadAt": last_upload_date.isoformat() if last_upload_date else None,
        "filters": {
            "preset": preset,
            "from": from_date.strftime("%Y-%m") if from_date else None,
            "to": to_date.strftime("%Y-%m") if to_date else None,
            "region": region,
            "channel": channel,
        },
    }


async def get_kpis_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> dict:
    """Calculate KPI values (Due, Collected, Overdue, Outstanding in period, Total all time)."""
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    all_time_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=False)

    # 1. Due (sum of due_amount in period)
    due_stmt = (
        select(func.coalesce(func.sum(Installment.due_amount), 0))
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    total_due = (await session.execute(due_stmt)).scalar() or Decimal("0")

    # 2. Collected (sum of received_amount in period)
    collected_stmt = (
        select(func.coalesce(func.sum(Installment.received_amount), 0))
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    total_collected = (await session.execute(collected_stmt)).scalar() or Decimal("0")

    # 3. Overdue (due - received for overdue/partial installments in period)
    overdue_stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]),
                            func.greatest(Decimal("0"), Installment.due_amount - Installment.received_amount),
                        ),
                        else_=Decimal("0"),
                    )
                ),
                0,
            )
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    total_overdue = (await session.execute(overdue_stmt)).scalar() or Decimal("0")

    # 4. Outstanding in period (due - received where due > received for installments in period)
    outstanding_period_stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Installment.status != InstallmentStatus.PAID,
                            func.greatest(Decimal("0"), Installment.due_amount - Installment.received_amount),
                        ),
                        else_=Decimal("0"),
                    )
                ),
                0,
            )
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    period_outstanding = (await session.execute(outstanding_period_stmt)).scalar() or Decimal("0")

    # 5. Total outstanding (all time)
    outstanding_all_time_stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Installment.status != InstallmentStatus.PAID,
                            func.greatest(Decimal("0"), Installment.due_amount - Installment.received_amount),
                        ),
                        else_=Decimal("0"),
                    )
                ),
                0,
            )
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*all_time_conds)
    )
    total_outstanding_all_time = (await session.execute(outstanding_all_time_stmt)).scalar() or Decimal("0")

    kpis = [
        {
            "title": "Due",
            "value": format_nu(total_due),
            "rawValue": float(total_due),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Collected",
            "value": format_nu(total_collected),
            "rawValue": float(total_collected),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Overdue",
            "value": format_nu(total_overdue),
            "rawValue": float(total_overdue),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Outstanding in period",
            "value": format_nu(period_outstanding),
            "rawValue": float(period_outstanding),
            "secondaryValue": format_nu(total_outstanding_all_time),
            "secondaryLabel": f"Total outstanding (all time): {format_nu(total_outstanding_all_time)}",
            "totalOutstandingAllTime": float(total_outstanding_all_time),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
    ]

    summary = {
        "due": float(total_due),
        "collected": float(total_collected),
        "overdue": float(total_overdue),
        "outstanding": float(period_outstanding),
        "total_outstanding_all_time": float(total_outstanding_all_time),
    }

    return {"kpis": kpis, "summary": summary}


async def get_regions_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get receivable/collected/overdue by region."""
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    result = await session.execute(
        select(
            Contract.region,
            func.coalesce(func.sum(Installment.due_amount), 0).label("total_due"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total_received"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]),
                            func.greatest(Decimal("0"), Installment.due_amount - Installment.received_amount),
                        ),
                        else_=Decimal("0"),
                    )
                ),
                0,
            ).label("total_overdue"),
        )
        .join(Installment, Installment.contract_id == Contract.id)
        .where(Contract.region.isnot(None), *period_conds)
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


async def get_aging_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get aging buckets (0-30, 31-60, 61-90, 91-120, 120+ days)."""
    latest_as_of = await session.execute(
        select(Upload.as_of_date)
        .where(Upload.status == UploadStatus.CONFIRMED)
        .order_by(Upload.upload_time.desc())
        .limit(1)
    )
    as_of_date = latest_as_of.scalar_one_or_none()
    today = as_of_date or date.today()

    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    result = await session.execute(
        select(
            case(
                ((today - Installment.due_month) <= 30, "0-30"),
                ((today - Installment.due_month) <= 60, "31-60"),
                ((today - Installment.due_month) <= 90, "61-90"),
                ((today - Installment.due_month) <= 120, "91-120"),
                else_="120+",
            ).label("bucket"),
            func.coalesce(
                func.sum(func.greatest(Decimal("0"), Installment.due_amount - Installment.received_amount)),
                0,
            ).label("amount"),
            func.count().label("count"),
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(Installment.status.in_([InstallmentStatus.OVERDUE, InstallmentStatus.PARTIAL]))
        .where(Installment.due_amount > Installment.received_amount)
        .where(*period_conds)
        .group_by("bucket")
    )
    rows = result.all()

    bucket_order = ["0-30", "31-60", "61-90", "91-120", "120+"]
    data = {row.bucket: {"amount": float(row.amount), "count": row.count} for row in rows}

    return [
        {"bucket": b, "amount": data.get(b, {}).get("amount", 0.0), "count": data.get(b, {}).get("count", 0)}
        for b in bucket_order
    ]


async def get_trend_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get collection trend by month."""
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    where_clauses = list(period_conds)
    if from_date is None and to_date is None:
        where_clauses.append(Installment.due_month >= date.today() - timedelta(days=180))

    result = await session.execute(
        select(
            func.to_char(Installment.due_month, "YYYY-MM").label("month"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            func.lower(Contract.payment_type).in_(["internal", "salary", "staff", "employee"]) |
                            Contract.payment_type.ilike("%salary%") |
                            Contract.payment_type.ilike("%employee%") |
                            Contract.payment_type.ilike("%staff%") |
                            Contract.payment_type.ilike("%internal%"),
                            Installment.received_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("internal"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            func.lower(Contract.payment_type).in_(["external", "customer"]) |
                            Contract.payment_type.ilike("%external%") |
                            Contract.payment_type.ilike("%customer%"),
                            Installment.received_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("external"),
            func.coalesce(func.sum(Installment.received_amount), 0).label("total"),
        )
        .join(Contract, Contract.id == Installment.contract_id)
        .where(*where_clauses)
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


async def get_attention_data(
    session: AsyncSession,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get items needing attention (missing contracts, validation warnings)."""
    items = []
    conds = []
    if region and region.strip():
        conds.append(func.lower(Contract.region) == region.strip().lower())
    if channel and channel.strip():
        conds.append(func.lower(Contract.payment_type).ilike(f"%{channel.strip().lower()}%"))

    review_result = await session.execute(
        select(func.count())
        .where(Contract.state == ContractState.MISSING_REVIEW, *conds)
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


async def get_contracts_table_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 50,
) -> List[dict]:
    """Get filtered installment table data."""
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    stmt = (
        select(
            Contract.reference,
            Contract.region,
            Contract.payment_type,
            Installment.due_month,
            Installment.due_amount,
            Installment.received_amount,
            Installment.status,
        )
        .join(Contract, Contract.id == Installment.contract_id)
        .where(*period_conds)
        .order_by(Installment.due_month.desc(), Contract.reference)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "reference": r.reference,
            "region": r.region or "",
            "payment_type": r.payment_type or "",
            "due_month": r.due_month.strftime("%Y-%m") if r.due_month else "",
            "due_amount": float(r.due_amount or 0),
            "received_amount": float(r.received_amount or 0),
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
        }
        for r in rows
    ]


@router.get("/kpis")
async def get_kpis(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    res = await get_kpis_data(session, from_date, to_date, region, channel)
    return res["kpis"]


@router.get("/regions")
async def get_regions(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_regions_data(session, from_date, to_date, region, channel)


@router.get("/aging")
async def get_aging(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_aging_data(session, from_date, to_date, region, channel)


@router.get("/trend")
async def get_trend(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_trend_data(session, from_date, to_date, region, channel)


@router.get("/attention")
async def get_attention(
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await get_attention_data(session, region, channel)


@router.get("/uploads")
async def get_recent_uploads(session: AsyncSession = Depends(get_session)):
    return await get_recent_uploads_data(session)


@router.get("/tables")
async def get_dashboard_tables(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_contracts_table_data(session, from_date, to_date, region, channel)


@router.get("/export")
async def export_dashboard_data(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Export filtered dashboard installments to CSV. Never exports personal data."""
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    stmt = (
        select(
            Contract.reference,
            Contract.region,
            Contract.payment_type,
            Installment.due_month,
            Installment.due_amount,
            Installment.received_amount,
            Installment.status,
        )
        .join(Contract, Contract.id == Installment.contract_id)
        .where(*period_conds)
        .order_by(Installment.due_month.asc(), Contract.reference)
    )
    rows = (await session.execute(stmt)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reference",
        "Region",
        "Payment Type",
        "Due Month",
        "Due Amount",
        "Received Amount",
        "Status",
        "Outstanding Amount",
    ])
    for r in rows:
        due = r.due_amount or Decimal("0")
        rec = r.received_amount or Decimal("0")
        out = max(Decimal("0"), due - rec)
        status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
        writer.writerow([
            r.reference,
            r.region or "",
            r.payment_type or "",
            r.due_month.strftime("%Y-%m") if r.due_month else "",
            f"{due:.2f}",
            f"{rec:.2f}",
            status_val,
            f"{out:.2f}",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dashboard_export.csv"'},
    )


def format_nu(amount: Decimal | float | int) -> str:
    """Format amount in Ngultrum format (Nu. 1,22,64,000)."""
    if not amount:
        return "Nu. 0"
    dec = Decimal(str(amount))
    if dec == 0:
        return "Nu. 0"
    s = f"{dec:.2f}".split(".")
    integer_part = s[0].replace(",", "")
    parts = []
    if len(integer_part) > 3:
        parts.append(integer_part[-3:])
        integer_part = integer_part[:-3]
        while len(integer_part) > 2:
            parts.append(integer_part[-2:])
            integer_part = integer_part[:-2]
    parts.append(integer_part)
    formatted = ",".join(reversed(parts))
    return f"Nu. {formatted}"