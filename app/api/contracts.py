"""
Contracts API router.

Provides the contract list (with filters + summary), per-contract detail, and
installment schedule, plus the manual close action.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_role
from app.core.confirm import verify_confirm_code
from app.core.metrics import calculate_months_left
from app.db.session import get_session
from app.models import Contract, ContractClosure, ContractState, Installment, User, UserRole
from app.schemas.contracts import ContractUpdateRequest
from app.schemas.uploads import CloseContractRequest, CloseContractResponse

logger = logging.getLogger(__name__)

router = APIRouter()

SORT_KEYS = {
    "reference",
    "customer",
    "region",
    "cost_center",
    "monthly_deduction",
    "emi_months",
    "emi_left",
    "receivable",
    "outstanding",
    "collected",
    "balance_due",
    "sales_amount",
    "start_date",
    "end_date",
}

EMI_LEFT_BUCKETS = {"zero", "1-2", "3-6", "7+"}

ENDING_FILTERS = {"this_month", "next_3_months", "this_fy"}


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _month_end(value: date) -> date:
    return _add_months(value, 1) - timedelta(days=1)


def _resolve_ending(ending: str, ref_date: Optional[date] = None) -> Tuple[date, date]:
    """Resolve an ending preset into an inclusive [start, end] date range."""
    ref = ref_date or date.today()
    start = _month_start(ref)
    if ending == "this_month":
        return start, _month_end(start)
    if ending == "next_3_months":
        return start, _month_end(_add_months(start, 2))
    if ending == "this_fy":
        if ref.month >= 7:
            return date(ref.year, 7, 1), date(ref.year + 1, 6, 30)
        return date(ref.year - 1, 7, 1), date(ref.year, 6, 30)
    raise HTTPException(status_code=400, detail=f"Invalid ending filter: {ending}")


def _channel_condition(channel: str):
    """Match the channel logic used by the dashboard filters."""
    if channel == "internal":
        return or_(
            func.lower(Contract.payment_type).in_(
                ["internal", "salary", "staff", "employee"]
            ),
            Contract.payment_type.ilike("%salary%"),
            Contract.payment_type.ilike("%employee%"),
            Contract.payment_type.ilike("%staff%"),
            Contract.payment_type.ilike("%internal%"),
        )
    if channel == "external":
        return or_(
            func.lower(Contract.payment_type).in_(["external", "customer"]),
            Contract.payment_type.ilike("%external%"),
            Contract.payment_type.ilike("%customer%"),
        )
    raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")


def _serialize_contract(
    contract: Contract,
    received: Optional[Decimal],
    total_due: Optional[Decimal],
) -> dict:
    received_value = Decimal(received or 0)
    total_due_value = Decimal(total_due or 0)
    sales = Decimal(contract.sales_amount or 0)
    gst = Decimal(contract.gst or 0)
    outstanding = max(Decimal("0"), sales + gst - received_value)
    balance_due = max(Decimal("0"), total_due_value - received_value)
    outstanding_value = float(outstanding)
    return {
        "id": contract.id,
        "reference": contract.reference,
        "customer": contract.customer or "",
        "cid": contract.cid or "",
        "mobile": contract.mobile or "",
        "item": contract.item or "",
        "brand": contract.brand or "",
        "ministry_agency": contract.ministry_agency or "",
        "region": contract.region or "",
        "cost_center": contract.cost_center or "",
        "payment_type": contract.payment_type or "",
        "emi_months": contract.emi_months,
        "months_left": calculate_months_left(
            outstanding_value, contract.monthly_deduction, contract.emi_months
        ),
        "monthly_deduction": float(contract.monthly_deduction or 0),
        "sales_amount": float(sales),
        "gst": float(gst),
        "receivable": float(sales + gst),
        "received": float(received_value),
        "collected": float(received_value),
        "total_due": float(total_due_value),
        "outstanding": outstanding_value,
        "balance_due": float(balance_due),
        "start_date": contract.start_date.isoformat() if contract.start_date else None,
        "end_date": contract.end_date.isoformat() if contract.end_date else None,
        "status": (
            contract.state.value
            if hasattr(contract.state, "value")
            else str(contract.state)
        ),
    }


def _matches_emi_left(item: dict, bucket: str) -> bool:
    left = item.get("months_left")
    if left is None:
        return False
    if bucket == "zero":
        return left == 0
    if bucket == "1-2":
        return 1 <= left <= 2
    if bucket == "3-6":
        return 3 <= left <= 6
    if bucket == "7+":
        return left >= 7
    return False


def _sort_value(item: dict, key: str):
    if key in ("reference", "customer", "region", "cost_center"):
        return (item.get(key) or "").lower()
    if key in ("start_date", "end_date"):
        value = item.get(key)
        return (value is None, value or "")
    value = item.get(key)
    return (value is None, value or 0)


@router.get("")
async def list_contracts(
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    cost_center: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    emi_left: Optional[str] = Query(None),
    ending: Optional[str] = Query(None),
    overdue: bool = Query(False),
    cycle_ended_due: bool = Query(False),
    cycle_ended_paid: bool = Query(False),
    sort: str = Query("outstanding"),
    order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
):
    """List contracts with filters, sorting, pagination, and a filtered summary."""
    conditions = []

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Contract.reference.ilike(term),
                Contract.customer.ilike(term),
                Contract.cid.ilike(term),
                Contract.mobile.ilike(term),
            )
        )

    if state and state.strip():
        try:
            conditions.append(Contract.state == ContractState(state.strip().lower()))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")

    if channel and channel.strip():
        conditions.append(_channel_condition(channel.strip().lower()))

    if region and region.strip():
        conditions.append(func.lower(Contract.region) == region.strip().lower())

    if cost_center and cost_center.strip():
        conditions.append(
            func.lower(Contract.cost_center) == cost_center.strip().lower()
        )

    if brand and brand.strip():
        conditions.append(func.lower(Contract.brand) == brand.strip().lower())

    if emi_left and emi_left.strip():
        bucket = emi_left.strip().lower()
        if bucket not in EMI_LEFT_BUCKETS:
            raise HTTPException(
                status_code=400, detail=f"Invalid emi_left filter: {emi_left}"
            )

    end_bounds = None
    if ending and ending.strip():
        ending_value = ending.strip().lower()
        if ending_value not in ENDING_FILTERS:
            raise HTTPException(
                status_code=400, detail=f"Invalid ending filter: {ending}"
            )
        end_bounds = _resolve_ending(ending_value)

    received_subq = (
        select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .correlate(Contract)
        .scalar_subquery()
    )
    total_due_subq = (
        select(func.coalesce(func.sum(Installment.due_amount), Decimal("0")))
        .where(Installment.contract_id == Contract.id)
        .correlate(Contract)
        .scalar_subquery()
    )

    stmt = (
        select(
            Contract,
            received_subq.label("received"),
            total_due_subq.label("total_due"),
        )
        .where(*conditions)
    )

    rows = (await session.execute(stmt)).all()
    items = [
        _serialize_contract(row[0], row.received, row.total_due)
        for row in rows
    ]

    if emi_left and emi_left.strip():
        items = [item for item in items if _matches_emi_left(item, emi_left.strip().lower())]

    if end_bounds is not None:
        start, end = end_bounds
        items = [
            item
            for item in items
            if item["end_date"]
            and start <= date.fromisoformat(item["end_date"]) <= end
        ]

    if overdue:
        items = [item for item in items if item["balance_due"] > 0]

    if cycle_ended_due:
        today = date.today()
        items = [
            item
            for item in items
            if item["end_date"]
            and date.fromisoformat(item["end_date"]) < today
            and item["balance_due"] > 0
        ]

    if cycle_ended_paid:
        today = date.today()
        items = [
            item
            for item in items
            if item["end_date"]
            and date.fromisoformat(item["end_date"]) < today
            and item["balance_due"] == 0
        ]

    summary = {
        "contracts": len(items),
        "monthly_deduction": sum(item["monthly_deduction"] for item in items),
        "receivable": sum(item["receivable"] for item in items),
        "outstanding": sum(item["outstanding"] for item in items),
        "collected": sum(item["collected"] for item in items),
        "balance_due": sum(item["balance_due"] for item in items),
    }

    sort_key = sort if sort in SORT_KEYS else "outstanding"
    reverse = (order or "desc").strip().lower() != "asc"
    field_key = "months_left" if sort_key == "emi_left" else sort_key

    if field_key in ("months_left", "emi_months", "start_date", "end_date"):
        present = [item for item in items if item.get(field_key) is not None]
        missing = [item for item in items if item.get(field_key) is None]
        present.sort(key=lambda item: _sort_value(item, field_key), reverse=reverse)
        items = present + missing
    else:
        items.sort(key=lambda item: _sort_value(item, sort_key), reverse=reverse)

    total = len(items)
    page = items[skip : skip + limit]

    return {
        "items": page,
        "total": total,
        "skip": skip,
        "limit": limit,
        "summary": summary,
    }


@router.get("/facets")
async def contract_facets(
    session: AsyncSession = Depends(get_session),
):
    """Distinct regions, cost centers, and brands for the filter sidebar."""
    region_rows = (
        await session.execute(
            select(Contract.region)
            .where(Contract.region.isnot(None), Contract.region != "")
            .distinct()
            .order_by(Contract.region)
        )
    ).scalars().all()

    cost_center_rows = (
        await session.execute(
            select(Contract.region, Contract.cost_center)
            .where(
                Contract.cost_center.isnot(None),
                Contract.cost_center != "",
            )
            .distinct()
            .order_by(Contract.region, Contract.cost_center)
        )
    ).all()

    brand_rows = (
        await session.execute(
            select(Contract.brand)
            .where(Contract.brand.isnot(None), Contract.brand != "")
            .distinct()
            .order_by(Contract.brand)
        )
    ).scalars().all()

    return {
        "regions": list(region_rows),
        "cost_centers": [
            {"region": region or "", "name": cost_center}
            for region, cost_center in cost_center_rows
        ],
        "brands": list(brand_rows),
    }


async def _contract_totals(
    session: AsyncSession, contract_id: int
) -> Tuple[Decimal, Decimal]:
    """Return (received, total_due) summed across a contract's installments."""
    received = (
        await session.execute(
            select(func.coalesce(func.sum(Installment.received_amount), Decimal("0")))
            .where(Installment.contract_id == contract_id)
        )
    ).scalar()
    total_due = (
        await session.execute(
            select(func.coalesce(func.sum(Installment.due_amount), Decimal("0")))
            .where(Installment.contract_id == contract_id)
        )
    ).scalar()
    return received or Decimal("0"), total_due or Decimal("0")


@router.get("/{contract_id}")
async def get_contract(
    contract_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get one contract with its all-time financial summary."""
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    received, total_due = await _contract_totals(session, contract_id)
    return _serialize_contract(contract, received, total_due)


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: int,
    request: ContractUpdateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Edit a contract's static information. Admin only.

    Installments are not touched, so collected amounts and the schedule keep
    their existing values. Outstanding is recalculated from the edited
    sales amount / GST minus collected.
    """
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    updates = request.model_dump(exclude_unset=True)

    # Trim text fields and store blank values as NULL.
    text_fields = {
        "customer",
        "cid",
        "mobile",
        "item",
        "brand",
        "region",
        "cost_center",
        "ministry_agency",
        "payment_type",
    }
    for field in text_fields & updates.keys():
        value = updates[field]
        if isinstance(value, str):
            updates[field] = value.strip() or None

    if "customer" in updates and not updates["customer"]:
        raise HTTPException(status_code=422, detail="Customer cannot be empty")

    start_date = updates.get("start_date", contract.start_date)
    end_date = updates.get("end_date", contract.end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422, detail="Start date cannot be after end date"
        )

    for field, value in updates.items():
        setattr(contract, field, value)

    await session.commit()
    await session.refresh(contract)

    received, total_due = await _contract_totals(session, contract_id)
    return _serialize_contract(contract, received, total_due)


@router.get("/{contract_id}/installments")
async def get_contract_installments(
    contract_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get the installment schedule for one contract."""
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    installments = (
        await session.execute(
            select(Installment)
            .where(Installment.contract_id == contract_id)
            .order_by(Installment.due_month.asc())
        )
    ).scalars().all()

    data = []
    for installment in installments:
        due = Decimal(installment.due_amount or 0)
        received = Decimal(installment.received_amount or 0)
        data.append(
            {
                "id": installment.id,
                "due_month": installment.due_month.isoformat(),
                "due_amount": float(due),
                "received_amount": float(received),
                "balance": float(max(Decimal("0"), due - received)),
                "salary_amount": float(installment.salary_amount or 0),
                "external_amount": float(installment.external_amount or 0),
                "cell_status": installment.cell_status,
                "status": (
                    installment.status.value
                    if hasattr(installment.status, "value")
                    else str(installment.status)
                ),
            }
        )
    return data


@router.post("/{contract_id}/close", response_model=CloseContractResponse)
async def close_contract_endpoint(
    contract_id: int,
    request: CloseContractRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.FINANCE_UPLOADER)),
):
    """
    Close a contract.
    # TEMPORARY - replace with real TOTP in M3
    """
    # Verify confirmation code
    await verify_confirm_code(
        code=request.get_code(),
        action="close_contract",
        entity_id=str(contract_id),
        entity_type="contract",
        session=session,
    )

    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    contract.state = ContractState.CLOSED

    closure = ContractClosure(
        contract_id=contract_id,
        upload_id=None,
        reason=request.reason or "manual_close",
        note=request.note,
        balance_at_closing=0,
        closed_by=current_user.id if current_user else 1,
    )
    session.add(closure)
    await session.commit()

    return CloseContractResponse(
        contract_id=contract_id,
        status="closed",
        message="Contract closed successfully",
    )
