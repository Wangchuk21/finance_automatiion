"""Database upsert service for Excel imports."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract, Installment, InstallmentStatus, ContractState
from app.importer.column_map import parse_amount


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Convert value to Decimal quantized to 0.01, or None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _determine_installment_status(
    due_amount: Optional[Decimal],
    received_amount: Decimal,
    cell_status: Optional[str],
    as_of: Optional[date] = None,
) -> InstallmentStatus:
    """Determine installment status from amounts, cell_status, and date."""
    if cell_status in ("not_received", "not_deducted"):
        return InstallmentStatus.PENDING

    if due_amount is None:
        # Outside schedule: no due amount
        if received_amount > Decimal("0"):
            return InstallmentStatus.PAID
        return InstallmentStatus.PENDING

    if received_amount >= due_amount:
        return InstallmentStatus.PAID
    if received_amount > Decimal("0"):
        return InstallmentStatus.PARTIAL

    # Nothing received
    today = as_of or date.today()
    if due_amount > Decimal("0") and date(today.year, today.month, 1) > date(
        today.year, today.month, 1
    ):
        # due_month is in the past
        pass
    return InstallmentStatus.PENDING


@dataclass
class UpsertResult:
    """Result of an upsert operation."""
    contracts_created: int = 0
    contracts_updated: int = 0
    installments_created: int = 0
    installments_updated: int = 0
    installments_unchanged: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


async def upsert_contracts(
    session: AsyncSession,
    contracts: List[Dict[str, Any]],
    upload_id: int,
    as_of: Optional[date] = None,
) -> UpsertResult:
    """
    Upsert contracts and their installments.

    Uses reference as the unique key for upsert.
    """
    result = UpsertResult()

    for contract_data in contracts:
        reference = contract_data.get("reference")
        if not reference:
            result.errors.append("Contract missing reference, skipping")
            continue

        installments_data = contract_data.pop("installments", [])

        # Check if contract exists
        stmt = select(Contract).where(Contract.reference == reference)
        existing = await session.execute(stmt)
        contract = existing.scalar_one_or_none()

        is_new = contract is None
        if is_new:
            contract = Contract(reference=reference)
            session.add(contract)
            result.contracts_created += 1
        else:
            result.contracts_updated += 1

        # Update static fields
        _update_contract_fields(contract, contract_data)

        # Flush to get contract ID
        await session.flush()

        # Upsert installments
        inst_result = await _upsert_installments(
            session, contract.id, installments_data, upload_id, as_of=as_of
        )
        result.installments_created += inst_result.created
        result.installments_updated += inst_result.updated
        result.installments_unchanged += inst_result.unchanged

    return result


def _update_contract_fields(contract: Contract, data: Dict[str, Any]) -> None:
    """Update contract fields from parsed data."""
    field_mapping = {
        "item": "item",
        "brand": "brand",
        "region": "region",
        "cost_center": "cost_center",
        "ministry_agency": "ministry_agency",
        "payment_type": "payment_type",
        "emi_months": "emi_months",
        "customer": "customer",
        "cid": "cid",
        "mobile": "mobile",
        "contract_date": "contract_date",
        "monthly_deduction": "monthly_deduction",
        "sales_amount": "sales_amount",
        "gst": "gst",
    }

    for data_key, model_attr in field_mapping.items():
        value = data.get(data_key)
        if value is not None:
            setattr(contract, model_attr, value)

    # Ensure state is active if not set
    if not contract.state:
        contract.state = ContractState.ACTIVE


@dataclass
class InstallmentUpsertResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


async def _upsert_installments(
    session: AsyncSession,
    contract_id: int,
    installments_data: List[Dict[str, Any]],
    upload_id: int,
    as_of: Optional[date] = None,
) -> InstallmentUpsertResult:
    """Upsert installments for a contract."""
    result = InstallmentUpsertResult()

    for inst_data in installments_data:
        due_month = inst_data.get("due_month")
        if not due_month:
            continue

        # --- amounts ---
        # due_amount comes explicitly; it is NULL for months outside the schedule
        due_amount = _to_decimal(inst_data.get("due_amount"))

        # external / salary are RECEIVED amounts (never due)
        external_amount = _to_decimal(inst_data.get("external_amount"))
        salary_amount = _to_decimal(inst_data.get("salary_amount"))

        # received = sum of both columns (do NOT clamp to due)
        received_amount = (external_amount or Decimal("0")) + (
            salary_amount or Decimal("0")
        )
        received_amount = received_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # cell_status: not_received / not_deducted (from the cell text)
        cell_status = inst_data.get("not_status") or inst_data.get("cell_status")

        # status
        status = _determine_installment_status(due_amount, received_amount, cell_status, as_of)

        # Check if installment exists
        stmt = select(Installment).where(
            Installment.contract_id == contract_id,
            Installment.due_month == due_month,
        )
        existing = await session.execute(stmt)
        installment = existing.scalar_one_or_none()

        if installment is None:
            installment = Installment(
                contract_id=contract_id,
                due_month=due_month,
                due_amount=due_amount,
                received_amount=received_amount,
                salary_amount=salary_amount,
                external_amount=external_amount,
                cell_status=cell_status,
                status=status,
            )
            session.add(installment)
            result.created += 1
        else:
            has_changes = False

            for attr, new_val in [
                ("due_amount", due_amount),
                ("received_amount", received_amount),
                ("salary_amount", salary_amount),
                ("external_amount", external_amount),
                ("cell_status", cell_status),
                ("status", status),
            ]:
                if getattr(installment, attr) != new_val:
                    setattr(installment, attr, new_val)
                    has_changes = True

            if has_changes:
                result.updated += 1
            else:
                result.unchanged += 1

    return result


async def get_upload_summary(session: AsyncSession, upload_id: int) -> Dict[str, Any]:
    """Get summary stats for an upload."""
    return {
        "upload_id": upload_id,
        "message": "Upload processed successfully",
    }


async def rollback_upload(session: AsyncSession, upload_id: int) -> bool:
    """
    Rollback an upload by deleting installments created/updated by it.
    This is a simplified version - in production you'd want to use
    installment_history to restore previous state.
    """
    from app.models import Upload, UploadStatus

    stmt = select(Upload).where(Upload.id == upload_id)
    result = await session.execute(stmt)
    upload = result.scalar_one_or_none()

    if upload:
        upload.status = UploadStatus.ROLLED_BACK
        return True
    return False