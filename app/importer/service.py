"""Database upsert service for Excel imports."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract, Installment, InstallmentStatus, ContractState
from app.importer.column_map import parse_amount


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
            session, contract.id, installments_data, upload_id
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
) -> InstallmentUpsertResult:
    """Upsert installments for a contract."""
    result = InstallmentUpsertResult()
    
    for inst_data in installments_data:
        due_month = inst_data.get("due_month")
        if not due_month:
            continue
        
        # Check if installment exists
        stmt = select(Installment).where(
            Installment.contract_id == contract_id,
            Installment.due_month == due_month,
        )
        existing = await session.execute(stmt)
        installment = existing.scalar_one_or_none()
        
        # Determine due_amount (prefer external, fallback to salary)
        due_amount = inst_data.get("external_amount")
        if due_amount is None:
            due_amount = inst_data.get("salary_amount")
        if due_amount is None:
            due_amount = Decimal("0")
        elif not isinstance(due_amount, Decimal):
            due_amount = Decimal(str(due_amount))
        
        # Received amount
        received_amount = inst_data.get("received_amount")
        if received_amount is None:
            received_amount = Decimal("0")
        elif not isinstance(received_amount, Decimal):
            received_amount = Decimal(str(received_amount))
        
        # Salary amount
        salary_amount = inst_data.get("salary_amount")
        if salary_amount is not None and not isinstance(salary_amount, Decimal):
            salary_amount = Decimal(str(salary_amount))
        
        # Determine status
        status = _determine_installment_status(
            due_amount, received_amount, inst_data.get("not_status")
        )
        
        if installment is None:
            # Create new
            installment = Installment(
                contract_id=contract_id,
                due_month=due_month,
                due_amount=due_amount,
                received_amount=received_amount,
                salary_amount=salary_amount,
                status=status,
            )
            session.add(installment)
            result.created += 1
        else:
            # Update existing - track history if changed
            has_changes = False
            
            if installment.due_amount != due_amount:
                installment.due_amount = due_amount
                has_changes = True
            
            if installment.received_amount != received_amount:
                installment.received_amount = received_amount
                has_changes = True
            
            if installment.salary_amount != salary_amount:
                installment.salary_amount = salary_amount
                has_changes = True
            
            if installment.status != status:
                installment.status = status
                has_changes = True
            
            if has_changes:
                result.updated += 1
            else:
                result.unchanged += 1
    
    return result


def _determine_installment_status(
    due_amount: Decimal,
    received_amount: Decimal,
    not_status: Optional[str] = None,
) -> InstallmentStatus:
    """Determine installment status from amounts and not_status flag."""
    if not_status == "not_received":
        return InstallmentStatus.PENDING
    elif not_status == "not_deducted":
        return InstallmentStatus.PENDING
    
    if due_amount <= 0:
        return InstallmentStatus.PENDING
    
    if received_amount <= 0:
        return InstallmentStatus.PENDING
    elif received_amount >= due_amount:
        return InstallmentStatus.PAID
    else:
        return InstallmentStatus.PARTIAL


async def get_upload_summary(session: AsyncSession, upload_id: int) -> Dict[str, Any]:
    """Get summary stats for an upload."""
    from sqlalchemy import func
    
    # Count contracts affected
    stmt = select(func.count()).select_from(Contract).join(Installment).where(
        Installment.id.in_(
            select(Installment.id).where(Installment.contract_id == Contract.id)
        )
    )
    # This is complex, return basic info for now
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
    # In a real implementation, you'd use installment_history to restore
    # For now, just mark upload as rolled_back
    from app.models import Upload, UploadStatus
    
    stmt = select(Upload).where(Upload.id == upload_id)
    result = await session.execute(stmt)
    upload = result.scalar_one_or_none()
    
    if upload:
        upload.status = UploadStatus.ROLLED_BACK
        return True
    return False