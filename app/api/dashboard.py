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

from app.core.auth import get_current_user, require_not_must_change_password
from app.core.installments import installment_balance_due_expr
from app.core.metrics import calculate_months_left
from app.db.session import get_session
from app.models import Contract, Installment, InstallmentStatus, ContractState, Upload, UploadStatus, User

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
    current_user: User = Depends(require_not_must_change_password),
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

    # Only count installments whose payment month (due_month) has already passed
    month_start = date(date.today().year, date.today().month, 1)
    past_due_cond = Installment.due_month < month_start

    # 1. Due — SUM(due_amount) for installments in the period
    due_stmt = (
        select(func.coalesce(func.sum(Installment.due_amount), 0))
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    total_due = (await session.execute(due_stmt)).scalar() or Decimal("0")

    # 2. Collected — SUM(received_amount) in the period
    collected_stmt = (
        select(func.coalesce(func.sum(Installment.received_amount), 0))
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
    )
    total_collected = (await session.execute(collected_stmt)).scalar() or Decimal("0")

    # 3. Balance Due — SUM of MAX(0, due - received) per installment in period.
    #    Overpayments in one month do not cancel unpaid months, so this always
    #    matches the balances shown in the installment schedule.
    balance_due_stmt = (
        select(installment_balance_due_expr())
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds, past_due_cond)
    )
    total_balance_due = (await session.execute(balance_due_stmt)).scalar() or Decimal("0")

    # 4. Overall Outstanding — SUM per contract of (Sales Amount + GST − total EMI received).
    #    This matches the Excel "Overall Outstanding" column formula:
    #    Outstanding = Sales Amount + GST − EMI Received  (where EMI Received = sum of all monthly payments)
    #    Applied to contracts filtered by region/channel; date filter not applied here (it's a contract-level total).
    contract_filter_conds = build_filter_conditions(
        None, None, region, channel, apply_date_filter=False
    )
    outstanding_stmt = (
        select(
            func.coalesce(
                func.sum(
                    func.greatest(
                        Decimal("0"),
                        Contract.sales_amount
                        + func.coalesce(Contract.gst, Decimal("0"))
                        - func.coalesce(
                            select(func.sum(Installment.received_amount))
                            .where(Installment.contract_id == Contract.id)
                            .scalar_subquery(),
                            Decimal("0"),
                        ),
                    )
                ),
                0,
            )
        )
        .where(*contract_filter_conds)
    )
    total_outstanding = (await session.execute(outstanding_stmt)).scalar() or Decimal("0")

    # 5. Overall Outstanding (all time, no region/channel filter) — for the secondary figure
    outstanding_all_time_stmt = (
        select(
            func.coalesce(
                func.sum(
                    func.greatest(
                        Decimal("0"),
                        Contract.sales_amount
                        + func.coalesce(Contract.gst, Decimal("0"))
                        - func.coalesce(
                            select(func.sum(Installment.received_amount))
                            .where(Installment.contract_id == Contract.id)
                            .scalar_subquery(),
                            Decimal("0"),
                        ),
                    )
                ),
                0,
            )
        )
    )
    total_outstanding_all_time = (await session.execute(outstanding_all_time_stmt)).scalar() or Decimal("0")

    kpis = [
        {
            "title": "Collected",
            "value": format_nu(total_collected),
            "rawValue": float(total_collected),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Balance Due",
            "value": format_nu(total_balance_due),
            "rawValue": float(total_balance_due),
            "change": 0.0,
            "changeLabel": "vs prev upload",
            "trend": "neutral",
        },
        {
            "title": "Overall Outstanding",
            "value": format_nu(total_outstanding),
            "rawValue": float(total_outstanding),
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
        "balance_due": float(total_balance_due),
        "outstanding": float(total_outstanding),
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
    """Get receivable (Overall Outstanding: Sales+GST-Received), collected, and balance due by region."""
    # 1. Overall Outstanding per region: SUM per contract of (Sales Amount + GST - total EMI received)
    contract_filter_conds = build_filter_conditions(
        None, None, region, channel, apply_date_filter=False
    )
    received_subquery = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    outstanding_stmt = (
        select(
            Contract.region,
            func.coalesce(
                func.sum(
                    func.greatest(
                        Decimal("0"),
                        Contract.sales_amount
                        + func.coalesce(Contract.gst, Decimal("0"))
                        - received_subquery,
                    )
                ),
                0,
            ).label("total_outstanding"),
        )
        .where(Contract.region.isnot(None), *contract_filter_conds)
        .group_by(Contract.region)
    )
    out_rows = (await session.execute(outstanding_stmt)).all()
    out_map = {r.region: r.total_outstanding for r in out_rows}

    # 2. Collected and Balance Due in the selected period per region
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    perf_sub = (
        select(
            Contract.region,
            Installment.contract_id,
            func.coalesce(func.sum(Installment.received_amount), 0).label("contract_rec"),
            installment_balance_due_expr().label("contract_balance"),
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(Contract.region.isnot(None), *period_conds)
        .group_by(Contract.region, Installment.contract_id)
        .subquery()
    )
    perf_stmt = (
        select(
            perf_sub.c.region,
            func.coalesce(func.sum(perf_sub.c.contract_rec), 0).label("total_received"),
            func.coalesce(
                func.sum(perf_sub.c.contract_balance),
                Decimal("0"),
            ).label("total_balance_due"),
        )
        .group_by(perf_sub.c.region)
    )
    perf_rows = (await session.execute(perf_stmt)).all()
    perf_map = {r.region: (r.total_received, r.total_balance_due) for r in perf_rows}

    all_regions = sorted(
        set(out_map.keys()) | set(perf_map.keys()),
        key=lambda reg: out_map.get(reg, Decimal("0")),
        reverse=True,
    )

    return [
        {
            "region": reg or "Unknown",
            "receivable": float(out_map.get(reg, Decimal("0"))),
            "outstanding": float(out_map.get(reg, Decimal("0"))),
            "collected": float(perf_map.get(reg, (0, 0))[0]),
            "balance_due": float(perf_map.get(reg, (0, 0))[1]),
            "overdue": float(perf_map.get(reg, (0, 0))[1]),
        }
        for reg in all_regions
    ]


async def get_cost_centers_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get a cost-centre breakdown for a region.

    Receivable is the all-time outstanding (Sales + GST - received), matching
    the region chart; collected/balance_due follow the selected period.
    """
    cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")

    # 1. All-time outstanding per cost centre
    contract_filter_conds = build_filter_conditions(
        None, None, region, channel, apply_date_filter=False
    )
    received_subquery = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    outstanding_stmt = (
        select(
            cc_label.label("cost_center"),
            func.count(func.distinct(Contract.id)).label("contracts"),
            func.coalesce(
                func.sum(
                    func.greatest(
                        Decimal("0"),
                        Contract.sales_amount
                        + func.coalesce(Contract.gst, Decimal("0"))
                        - received_subquery,
                    )
                ),
                0,
            ).label("total_outstanding"),
        )
        .where(*contract_filter_conds)
        .group_by(cc_label)
    )
    out_rows = (await session.execute(outstanding_stmt)).all()
    out_map = {r.cost_center: (r.total_outstanding, r.contracts) for r in out_rows}

    # 2. Collected and Balance Due in the selected period per cost centre
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)
    perf_sub = (
        select(
            cc_label.label("cost_center"),
            Installment.contract_id,
            func.coalesce(func.sum(Installment.received_amount), 0).label("contract_rec"),
            installment_balance_due_expr().label("contract_balance"),
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds)
        .group_by(cc_label, Installment.contract_id)
        .subquery()
    )
    perf_stmt = (
        select(
            perf_sub.c.cost_center,
            func.coalesce(func.sum(perf_sub.c.contract_rec), 0).label("total_received"),
            func.coalesce(
                func.sum(perf_sub.c.contract_balance),
                Decimal("0"),
            ).label("total_balance_due"),
        )
        .group_by(perf_sub.c.cost_center)
    )
    perf_rows = (await session.execute(perf_stmt)).all()
    perf_map = {r.cost_center: (r.total_received, r.total_balance_due) for r in perf_rows}

    all_ccs = sorted(
        set(out_map.keys()) | set(perf_map.keys()),
        key=lambda cc: out_map.get(cc, (Decimal("0"), 0))[0],
        reverse=True,
    )

    return [
        {
            "cost_center": cc,
            "contracts": int(out_map.get(cc, (Decimal("0"), 0))[1]),
            "receivable": float(out_map.get(cc, (Decimal("0"), 0))[0]),
            "collected": float(perf_map.get(cc, (0, 0))[0]),
            "balance_due": float(perf_map.get(cc, (0, 0))[1]),
        }
        for cc in all_ccs
    ]


async def get_cost_center_contracts_data(
    session: AsyncSession,
    cost_center: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """List the individual contracts/customers under one cost centre.

    Outstanding is all-time (Sales + GST - received); collected and balance_due
    follow the selected period, matching the cost-centre table.
    """
    cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")
    contract_filter_conds = build_filter_conditions(
        None, None, region, channel, apply_date_filter=False
    )
    contract_filter_conds.append(cc_label == cost_center)

    received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    period_conds = build_filter_conditions(
        from_date, to_date, None, None, apply_date_filter=True
    )
    period_received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id, *period_conds)
        .scalar_subquery()
    )
    period_balance_subq = (
        select(installment_balance_due_expr())
        .where(Installment.contract_id == Contract.id, *period_conds)
        .correlate(Contract)
        .scalar_subquery()
    )

    outstanding = func.greatest(
        Decimal("0"),
        func.coalesce(Contract.sales_amount, Decimal("0"))
        + func.coalesce(Contract.gst, Decimal("0"))
        - received_subq,
    ).label("outstanding")
    collected = period_received_subq.label("collected")
    balance_due = period_balance_subq.label("balance_due")

    stmt = (
        select(
            Contract.id,
            Contract.reference,
            Contract.customer,
            Contract.cid,
            Contract.mobile,
            Contract.item,
            Contract.brand,
            Contract.ministry_agency,
            Contract.region,
            cc_label.label("cost_center"),
            Contract.payment_type,
            Contract.emi_months,
            Contract.monthly_deduction,
            Contract.sales_amount,
            Contract.gst,
            Contract.start_date,
            Contract.end_date,
            Contract.state,
            received_subq.label("received"),
            outstanding,
            collected,
            balance_due,
        )
        .where(*contract_filter_conds)
        .order_by(outstanding.desc(), Contract.customer.asc())
    )
    rows = (await session.execute(stmt)).all()

    data = []
    for r in rows:
        outstanding_value = float(r.outstanding or 0)
        data.append(
            {
                "id": r.id,
                "reference": r.reference,
                "customer": r.customer or "",
                "cid": r.cid or "",
                "mobile": r.mobile or "",
                "item": r.item or "",
                "brand": r.brand or "",
                "ministry_agency": r.ministry_agency or "",
                "region": r.region or "",
                "cost_center": r.cost_center,
                "payment_type": r.payment_type or "",
                "emi_months": r.emi_months,
                "months_left": calculate_months_left(
                    outstanding_value, r.monthly_deduction, r.emi_months
                ),
                "monthly_deduction": float(r.monthly_deduction or 0),
                "sales_amount": float(r.sales_amount or 0),
                "gst": float(r.gst or 0),
                "received": float(r.received or 0),
                "outstanding": outstanding_value,
                "collected": float(r.collected or 0),
                "balance_due": float(r.balance_due or 0),
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "status": r.state.value if hasattr(r.state, "value") else str(r.state),
            }
        )
    return data


async def get_aging_data(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    region: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Get aging buckets (0-30, 31-60, 61-90, 91-120, 120+ days) matching Excel Balance Due."""
    period_conds = build_filter_conditions(from_date, to_date, region, channel, apply_date_filter=True)

    # Only count installments whose payment month (due_month) has already passed
    month_start = date(date.today().year, date.today().month, 1)
    past_due_cond = Installment.due_month < month_start

    contract_summary = (
        select(
            Contract.id,
            Contract.monthly_deduction,
            installment_balance_due_expr().label("balance_due"),
            case(
                (
                    Contract.monthly_deduction > 0,
                    func.round(
                        installment_balance_due_expr() / Contract.monthly_deduction
                    ),
                ),
                else_=0,
            ).label("unpaid_count"),
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*period_conds, past_due_cond)
        .group_by(Contract.id, Contract.monthly_deduction)
        .subquery()
    )

    aging_stmt = (
        select(
            case(
                (contract_summary.c.unpaid_count <= 1, "0-30"),
                (contract_summary.c.unpaid_count == 2, "31-60"),
                (contract_summary.c.unpaid_count == 3, "61-90"),
                (contract_summary.c.unpaid_count == 4, "91-120"),
                else_="120+",
            ).label("bucket"),
            func.coalesce(func.sum(contract_summary.c.balance_due), 0).label("amount"),
            func.count().label("count"),
        )
        .where(contract_summary.c.balance_due > 0)
        .group_by("bucket")
    )
    result = await session.execute(aging_stmt)
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
    current_user: User = Depends(require_not_must_change_password),
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
    current_user: User = Depends(require_not_must_change_password),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_regions_data(session, from_date, to_date, region, channel)


@router.get("/cost-centers")
async def get_cost_centers(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_cost_centers_data(session, from_date, to_date, region, channel)


@router.get("/cost-centers/contracts")
async def get_cost_center_contracts(
    cost_center: str = Query(...),
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_cost_center_contracts_data(
        session, cost_center, from_date, to_date, region, channel
    )


@router.get("/aging")
async def get_aging(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
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
    current_user: User = Depends(require_not_must_change_password),
):
    from_date, to_date = resolve_date_bounds(preset, from_, to)
    return await get_trend_data(session, from_date, to_date, region, channel)


@router.get("/attention")
async def get_attention(
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    return await get_attention_data(session, region, channel)


@router.get("/uploads")
async def get_recent_uploads(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    return await get_recent_uploads_data(session)


@router.get("/tables")
async def get_dashboard_tables(
    preset: Optional[str] = Query("all"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
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
    current_user: User = Depends(require_not_must_change_password),
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
    """Format amount in standard international format (millions/thousands) with Nu. prefix (e.g. Nu. 4,961,670.80 or Nu. 185,000,000)."""
    if not amount:
        return "Nu. 0"
    dec = Decimal(str(amount))
    if dec == 0:
        return "Nu. 0"
    if dec == dec.to_integral():
        return f"Nu. {int(dec):,}"
    return f"Nu. {dec:,.2f}"

# ----------------------------- Reports Endpoints -----------------------------


class _ReportFilters:
    @staticmethod
    def build(
        session: AsyncSession,
        region: Optional[str] = None,
        cost_center: Optional[str] = None,
        channel: Optional[str] = None,
        brand: Optional[str] = None,
        state: Optional[str] = None,
    ):
        conditions = []
        if region and region.strip():
            conditions.append(func.lower(Contract.region) == region.strip().lower())
        if cost_center and cost_center.strip():
            cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")
            conditions.append(func.lower(cc_label) == cost_center.strip().lower())
        if channel and channel.strip():
            ch = channel.strip().lower()
            if ch == "internal":
                conditions.append(
                    func.lower(Contract.payment_type).in_(["internal", "salary", "staff", "employee"])
                    | Contract.payment_type.ilike("%salary%")
                    | Contract.payment_type.ilike("%employee%")
                    | Contract.payment_type.ilike("%staff%")
                    | Contract.payment_type.ilike("%internal%")
                )
            elif ch == "external":
                conditions.append(
                    func.lower(Contract.payment_type).in_(["external", "customer"])
                    | Contract.payment_type.ilike("%external%")
                    | Contract.payment_type.ilike("%customer%")
                )
        if brand and brand.strip():
            conditions.append(func.lower(Contract.brand) == brand.strip().lower())
        if state and state.strip():
            try:
                from app.models import ContractState

                conditions.append(Contract.state == ContractState(state.strip().lower()))
            except Exception:
                pass
        return conditions


@router.get("/reports/overdue")
async def get_overdue_report(
    region: Optional[str] = Query(None),
    cost_center: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    filters = _ReportFilters.build(session, region, cost_center, channel, brand, state)

    cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")
    received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    period_received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id, Installment.received_amount > 0)
        .scalar_subquery()
    )

    # Overdue = balance due on installments due in the past (before current month start)
    from datetime import date as _date

    month_start = _date(date.today().year, date.today().month, 1)
    overdue_balance_subq = (
        select(installment_balance_due_expr())
        .where(
            Installment.contract_id == Contract.id,
            Installment.due_month < month_start,
        )
        .correlate(Contract)
        .scalar_subquery()
    )
    balance_due_subq = (
        select(installment_balance_due_expr())
        .where(Installment.contract_id == Contract.id)
        .correlate(Contract)
        .scalar_subquery()
    )

    outstanding = func.greatest(
        Decimal("0"),
        func.coalesce(Contract.sales_amount, Decimal("0"))
        + func.coalesce(Contract.gst, Decimal("0"))
        - received_subq,
    ).label("outstanding")
    overdue_amount = overdue_balance_subq.label("overdue_amount")
    balance_due = balance_due_subq.label("balance_due")

    stmt = (
        select(
            Contract.id,
            Contract.reference,
            Contract.customer,
            Contract.cid,
            Contract.mobile,
            Contract.region,
            cc_label.label("cost_center"),
            Contract.brand,
            Contract.payment_type,
            Contract.monthly_deduction,
            Contract.emi_months,
            Contract.start_date,
            Contract.end_date,
            Contract.state,
            outstanding,
            balance_due,
            overdue_amount,
        )
        .where(*filters, overdue_amount > 0)
        .order_by(overdue_amount.desc(), Contract.reference.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for r in rows:
        outstanding_value = float(r.outstanding or 0)
        items.append(
            {
                "id": r.id,
                "reference": r.reference,
                "customer": r.customer or "",
                "cid": r.cid or "",
                "mobile": r.mobile or "",
                "region": r.region or "",
                "cost_center": r.cost_center,
                "brand": r.brand or "",
                "payment_type": r.payment_type or "",
                "monthly_deduction": float(r.monthly_deduction or 0),
                "emi_months": r.emi_months,
                "months_left": calculate_months_left(
                    outstanding_value, r.monthly_deduction, r.emi_months
                ),
                "outstanding": outstanding_value,
                "balance_due": float(r.balance_due or 0),
                "overdue_amount": float(r.overdue_amount or 0),
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "status": r.state.value if hasattr(r.state, "value") else str(r.state),
            }
        )
    total_overdue = sum((Decimal(str(i["overdue_amount"])) for i in items), Decimal("0"))
    return {"items": items, "total": len(items), "total_overdue": float(total_overdue)}


@router.get("/reports/by-region")
async def get_report_by_region(
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    filters = _ReportFilters.build(session, region, None, channel, brand, state)
    cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")
    received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    balance_due_subq = (
        select(installment_balance_due_expr())
        .where(Installment.contract_id == Contract.id)
        .correlate(Contract)
        .scalar_subquery()
    )

    outstanding = func.greatest(
        Decimal("0"),
        func.coalesce(Contract.sales_amount, Decimal("0"))
        + func.coalesce(Contract.gst, Decimal("0"))
        - received_subq,
    )
    balance_due = balance_due_subq

    stmt = (
        select(
            Contract.region,
            cc_label.label("cost_center"),
            func.count(Contract.id).label("contracts"),
            func.coalesce(func.sum(Contract.monthly_deduction), 0).label("monthly_deduction"),
            func.coalesce(func.sum(outstanding), 0).label("outstanding"),
            func.coalesce(func.sum(received_subq), 0).label("collected"),
            func.coalesce(func.sum(balance_due), 0).label("balance_due"),
        )
        .where(*filters)
        .group_by(Contract.region, cc_label)
        .order_by(Contract.region, cc_label)
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for r in rows:
        items.append(
            {
                "region": r.region or "",
                "cost_center": r.cost_center,
                "contracts": int(r.contracts or 0),
                "monthly_deduction": float(r.monthly_deduction or 0),
                "outstanding": float(r.outstanding or 0),
                "collected": float(r.collected or 0),
                "balance_due": float(r.balance_due or 0),
            }
        )
    return {"items": items}


@router.get("/reports/by-brand")
async def get_report_by_brand(
    region: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    """Summary of contracts and collections grouped by brand (income/performance by brand)."""
    filters = _ReportFilters.build(session, region, None, channel, brand, state)
    brand_label = func.coalesce(func.nullif(func.trim(Contract.brand), ""), "Unassigned")
    received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .scalar_subquery()
    )
    balance_due_subq = (
        select(installment_balance_due_expr())
        .where(Installment.contract_id == Contract.id)
        .correlate(Contract)
        .scalar_subquery()
    )

    outstanding = func.greatest(
        Decimal("0"),
        func.coalesce(Contract.sales_amount, Decimal("0"))
        + func.coalesce(Contract.gst, Decimal("0"))
        - received_subq,
    )
    balance_due = balance_due_subq

    stmt = (
        select(
            brand_label.label("brand"),
            func.count(Contract.id).label("contracts"),
            func.coalesce(func.sum(Contract.monthly_deduction), 0).label("monthly_deduction"),
            func.coalesce(func.sum(outstanding), 0).label("outstanding"),
            func.coalesce(func.sum(received_subq), 0).label("collected"),
            func.coalesce(func.sum(balance_due), 0).label("balance_due"),
        )
        .where(*filters)
        .group_by(brand_label)
        .order_by(func.sum(outstanding).desc())
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for r in rows:
        items.append(
            {
                "brand": r.brand or "",
                "contracts": int(r.contracts or 0),
                "monthly_deduction": float(r.monthly_deduction or 0),
                "outstanding": float(r.outstanding or 0),
                "collected": float(r.collected or 0),
                "balance_due": float(r.balance_due or 0),
            }
        )
    return {"items": items}


@router.get("/reports/dues")
async def get_dues_report(
    region: Optional[str] = Query(None),
    cost_center: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    from_month: Optional[str] = Query(None),
    to_month: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_not_must_change_password),
):
    from datetime import date as _date

    filters = _ReportFilters.build(session, region, cost_center, channel, brand, state)
    cc_label = func.coalesce(func.nullif(func.trim(Contract.cost_center), ""), "Unassigned")

    conditions = list(filters)

    def parse_month(m: str):
        try:
            if "-" in m:
                y, mo = m.split("-")
                return _date(int(y), int(mo), 1)
            return None
        except Exception:
            return None

    fm = parse_month(from_month) if from_month else None
    tm = parse_month(to_month) if to_month else None
    if fm:
        conditions.append(Installment.due_month >= fm)
    if tm:
        conditions.append(Installment.due_month <= tm)
    else:
        conditions.append(Installment.due_month <= _date(date.today().year, date.today().month, 1))

    stmt = (
        select(
            Installment.id,
            Installment.due_month,
            Installment.due_amount,
            Installment.received_amount,
            Installment.status,
            Contract.id.label("contract_id"),
            Contract.reference,
            Contract.customer,
            Contract.region,
            cc_label.label("cost_center"),
            Contract.brand,
            Contract.payment_type,
            Contract.monthly_deduction,
            Contract.state,
        )
        .join(Contract, Installment.contract_id == Contract.id)
        .where(*conditions, Installment.due_amount > 0)
        .order_by(Installment.due_month.asc(), Contract.reference.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for r in rows:
        due = Decimal(r.due_amount or 0)
        received = Decimal(r.received_amount or 0)
        balance = max(Decimal("0"), due - received)
        items.append(
            {
                "installment_id": r.id,
                "contract_id": r.contract_id,
                "reference": r.reference,
                "customer": r.customer or "",
                "region": r.region or "",
                "cost_center": r.cost_center,
                "brand": r.brand or "",
                "payment_type": r.payment_type or "",
                "due_month": r.due_month.isoformat() if r.due_month else None,
                "due_amount": float(due),
                "received_amount": float(received),
                "balance": float(balance),
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "contract_status": r.state.value if hasattr(r.state, "value") else str(r.state),
            }
        )
    total_due = sum((Decimal(str(i["due_amount"])) for i in items), Decimal("0"))
    total_balance = sum((Decimal(str(i["balance"])) for i in items), Decimal("0"))
    return {"items": items, "total": len(items), "total_due": float(total_due), "total_balance": float(total_balance)}
