"""Comparison service for comparing uploads against previous confirmed uploads."""

import json
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract, Installment, InstallmentHistory, InstallmentStatus, ContractState, Upload, UploadStatus
from app.importer.reader import import_excel_file, read_excel_sheet, parse_sheet_to_contracts


@dataclass
class ContractComparison:
    """Comparison result for a single contract."""
    contract_id: int
    reference: str
    customer: Optional[str]
    cid: Optional[str]
    region: Optional[str]
    previous_balance: Decimal
    current_balance: Decimal
    previous_status: ContractState
    current_status: ContractState
    change_type: str  # "newly_paid", "newly_overdue", "new", "missing", "correction", "unchanged"
    details: List[str] = field(default_factory=list)


@dataclass
class ComparisonSummary:
    """Summary of comparison results."""
    total_contracts_current: int
    total_contracts_previous: int
    newly_paid: int
    newly_overdue: int
    new_contracts: int
    missing_contracts: int
    corrections: int
    unchanged: int
    total_outstanding_before: Decimal
    total_outstanding_after: Decimal
    total_received_before: Decimal
    total_received_after: Decimal
    missing_share: Decimal
    missing_contracts_detail: List[ContractComparison] = field(default_factory=list)
    newly_paid_detail: List[ContractComparison] = field(default_factory=list)
    newly_overdue_detail: List[ContractComparison] = field(default_factory=list)
    new_contracts_detail: List[ContractComparison] = field(default_factory=list)
    corrections_detail: List[ContractComparison] = field(default_factory=list)


async def get_last_confirmed_upload(session: AsyncSession, as_of_date: Optional[date] = None) -> Optional[Upload]:
    """Get the last confirmed upload before the given date."""
    stmt = select(Upload).where(Upload.status == UploadStatus.CONFIRMED)
    if as_of_date:
        stmt = stmt.where(Upload.as_of_date <= as_of_date)
    stmt = stmt.order_by(Upload.as_of_date.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_upload_contracts(session: AsyncSession, upload_id: int) -> Dict[int, Dict[str, Any]]:
    """Get all contracts with their installments for a specific upload.
    
    Returns dict of contract_id -> {contract_data, installments, balance, status}
    """
    # Get all contracts that have installments from this upload
    stmt = select(
        Contract.id, Contract.reference, Contract.customer, Contract.cid,
        Contract.region, Contract.brand, Contract.state,
        Installment.due_month, Installment.due_amount, Installment.received_amount,
        Installment.salary_amount, Installment.status
    ).join(Installment, Installment.contract_id == Contract.id).join(
        InstallmentHistory, InstallmentHistory.installment_id == Installment.id
    ).where(InstallmentHistory.upload_id == upload_id)
    
    result = await session.execute(stmt)
    rows = result.all()
    
    contracts: Dict[int, Dict[str, Any]] = {}
    
    for row in rows:
        contract_id = row.id
        if contract_id not in contracts:
            contracts[contract_id] = {
                "id": contract_id,
                "reference": row.reference,
                "customer": row.customer,
                "cid": row.cid,
                "region": row.region,
                "brand": row.brand,
                "state": row.state,
                "installments": [],
                "total_due": Decimal("0"),
                "total_received": Decimal("0"),
                "total_salary": Decimal("0"),
            }
        
        inst = {
            "due_month": row.due_month,
            "due_amount": row.due_amount,
            "received_amount": row.received_amount,
            "salary_amount": row.salary_amount,
            "status": row.status,
        }
        contracts[contract_id]["installments"].append(inst)
        contracts[contract_id]["total_due"] += row.due_amount or Decimal("0")
        contracts[contract_id]["total_received"] += row.received_amount or Decimal("0")
        if row.salary_amount:
            contracts[contract_id]["total_salary"] += row.salary_amount
    
    # Calculate balance and determine status for each contract
    for contract in contracts.values():
        contract["balance"] = contract["total_due"] - contract["total_received"]
        # Determine overall contract status based on installments
        if all(inst["status"] == InstallmentStatus.PAID for inst in contract["installments"]):
            contract["calculated_status"] = ContractState.CLOSED
        elif any(inst["status"] == InstallmentStatus.OVERDUE for inst in contract["installments"]):
            contract["calculated_status"] = ContractState.ACTIVE
        elif any(inst["status"] == InstallmentStatus.PARTIAL for inst in contract["installments"]):
            contract["calculated_status"] = ContractState.ACTIVE
        else:
            contract["calculated_status"] = ContractState.ACTIVE
    
    return contracts


async def compare_uploads(
    session: AsyncSession,
    current_upload_id: int,
    previous_upload_id: Optional[int] = None
) -> Tuple[ComparisonSummary, List[List[ContractComparison]]]:
    """Compare current upload against previous confirmed upload."""
    
    # Get current upload
    current_upload = await session.get(Upload, current_upload_id)
    if not current_upload:
        raise ValueError("Current upload not found")
    
    # Get previous confirmed upload if not specified
    if previous_upload_id is None:
        prev_upload = await get_last_confirmed_upload(session, current_upload.as_of_date)
        if not prev_upload:
            # No previous upload to compare against
            return ComparisonSummary(
                total_contracts_current=0,
                total_contracts_previous=0,
                newly_paid=0,
                newly_overdue=0,
                new_contracts=0,
                missing_contracts=0,
                corrections=0,
                unchanged=0,
                total_outstanding_before=Decimal("0"),
                total_outstanding_after=Decimal("0"),
                total_received_before=Decimal("0"),
                total_received_after=Decimal("0"),
                missing_contracts_detail=[],
                newly_paid_detail=[],
                newly_overdue_detail=[],
                new_contracts_detail=[],
                corrections_detail=[],
                missing_share=Decimal("0"),
            ), []
        prev_upload = prev_upload
    else:
        prev_upload = await session.get(Upload, previous_upload_id)
        if not prev_upload:
            raise ValueError("Previous upload not found")
    
    # Parse current upload's file directly (since it's pending, no installment_history records yet)
    import json
    summary = json.loads(current_upload.summary) if current_upload.summary else {}
    current_parsed = read_excel_sheet(
        summary.get("temp_file", ""),
        sheet_name=summary.get("sheet_name"),
        header_row=summary.get("header_row")
    )
    current_contracts_list = parse_sheet_to_contracts(current_parsed)
    
    # Add computed fields to current contracts (balance, total_due, total_received, etc.)
    for contract in current_contracts_list:
        total_due = Decimal("0")
        total_received = Decimal("0")
        total_salary = Decimal("0")
        for inst in contract.get("installments", []):
            due_amount = Decimal(str(inst.get("external_amount") or inst.get("salary_amount") or 0))
            total_due += due_amount
            total_received += Decimal(str(inst.get("received_amount") or 0))
            if inst.get("salary_amount"):
                total_salary += Decimal(str(inst.get("salary_amount")))
            
            contract["total_due"] = total_due
            contract["total_received"] = total_received
            contract["total_salary"] = total_salary
            contract["balance"] = total_due - total_received
            
            # Determine contract state
            if all(Decimal(str(inst.get("received_amount", 0))) >= Decimal(str(inst.get("external_amount") or inst.get("salary_amount") or 0)) for inst in contract.get("installments", [])):
                contract["calculated_status"] = ContractState.CLOSED
            elif any(inst.get("status") == InstallmentStatus.OVERDUE for inst in contract.get("installments", [])):
                contract["calculated_status"] = ContractState.ACTIVE
            elif any(inst.get("status") == InstallmentStatus.PARTIAL for inst in contract.get("installments", [])):
                contract["calculated_status"] = ContractState.ACTIVE
            else:
                contract["calculated_status"] = ContractState.ACTIVE
            
            contract["state"] = contract["calculated_status"]
    
    # Get previous upload's contracts from database (via installment_history)
    previous_contracts = await get_upload_contracts(session, prev_upload.id)
    
    # Convert current_contracts_list to dict keyed by contract reference
    current_contracts_dict = {}
    for contract in current_contracts_list:
        # Use reference as key for comparison
        current_contracts_dict[contract["reference"]] = contract
    
    # Convert previous_contracts to dict keyed by reference
    previous_contracts_dict = {c["reference"]: c for c in previous_contracts.values()}
    
    current_refs = set(current_contracts_dict.keys())
    previous_refs = set(previous_contracts_dict.keys())
    
    # Compare
    missing_contracts = []
    newly_paid = []
    newly_overdue = []
    new_contracts = []
    corrections = []
    unchanged = 0
    
    # Missing contracts (in previous but not in current)
    for ref in previous_refs - current_refs:
        prev = previous_contracts_dict[ref]
        missing_contracts.append(ContractComparison(
            contract_id=0,
            reference=prev["reference"],
            customer=prev["customer"],
            cid=prev["cid"],
            region=prev["region"],
            previous_balance=prev["balance"],
            current_balance=Decimal("0"),
            previous_status=prev["state"],
            current_status=ContractState.CLOSED,
            change_type="missing",
            details=[f"Contract {prev['reference']} missing from current upload"]
        ))
    
    # New contracts (in current but not in previous)
    for ref in current_refs - previous_refs:
        curr = current_contracts_dict[ref]
        new_contracts.append(ContractComparison(
            contract_id=0,
            reference=curr["reference"],
            customer=curr["customer"],
            cid=curr["cid"],
            region=curr["region"],
            previous_balance=Decimal("0"),
            current_balance=curr["balance"],
            previous_status=ContractState.ACTIVE,
            current_status=curr["calculated_status"],
            change_type="new",
            details=[f"New contract {curr['reference']}"]
        ))
    
    # Compare existing contracts
    for ref in current_refs & previous_refs:
        curr = current_contracts_dict[ref]
        prev = previous_contracts_dict[ref]
        
        prev_balance = prev["balance"]
        curr_balance = curr["balance"]
        prev_received = prev["total_received"]
        curr_received = curr["total_received"]
        prev_due = prev["total_due"]
        curr_due = curr["total_due"]
        
        # Check if newly paid (was not fully paid, now fully paid)
        was_fully_paid = prev["total_due"] <= prev["total_received"]
        is_fully_paid = curr_due <= curr["total_received"]
        
        if not was_fully_paid and is_fully_paid:
            newly_paid.append(ContractComparison(
                contract_id=0,
                reference=curr["reference"],
                customer=curr["customer"],
                cid=curr["cid"],
                region=curr["region"],
                previous_balance=prev["balance"],
                current_balance=curr["balance"],
                previous_status=prev["state"],
                current_status=ContractState.CLOSED,
                change_type="newly_paid",
                details=[f"Contract {curr['reference']} fully paid"]
            ))
            continue
        
        # Check if newly overdue
        was_overdue = prev["balance"] > 0 and any(
            inst["status"] == InstallmentStatus.OVERDUE for inst in previous_contracts_dict[ref]["installments"]
        )
        is_overdue = curr["balance"] > 0 and any(
            inst["status"] == InstallmentStatus.OVERDUE for inst in curr["installments"]
        )
        
        if not was_overdue and is_overdue:
            newly_overdue.append(ContractComparison(
                contract_id=0,
                reference=curr["reference"],
                customer=curr["customer"],
                cid=curr["cid"],
                region=curr["region"],
                previous_balance=prev["balance"],
                current_balance=curr["balance"],
                previous_status=prev["state"],
                current_status=ContractState.ACTIVE,
                change_type="newly_overdue",
                details=[f"Contract {curr['reference']} became overdue"]
            ))
            continue
        
        # Check for corrections (amount changes)
        if curr_due != prev_due or curr["total_received"] != prev["total_received"]:
            corrections.append(ContractComparison(
                contract_id=0,
                reference=curr["reference"],
                customer=curr["customer"],
                cid=curr["cid"],
                region=curr["region"],
                previous_balance=prev["balance"],
                current_balance=curr["balance"],
                previous_status=prev["state"],
                current_status=curr["calculated_status"],
                change_type="correction",
                details=[f"Amounts changed: due {prev_due}->{curr_due}, received {prev_received}->{curr_received}"]
            ))
            continue
        
        unchanged += 1
    
    # Calculate totals
    total_outstanding_before = sum(c["balance"] for c in previous_contracts_dict.values())
    total_outstanding_after = sum(c["balance"] for c in current_contracts_dict.values())
    total_received_before = sum(c["total_received"] for c in previous_contracts_dict.values())
    total_received_after = sum(c["total_received"] for c in current_contracts_dict.values())
    
    missing_count = len(missing_contracts)
    total_previous = len(previous_contracts_dict)
    missing_share = Decimal(str(missing_count)) / Decimal(str(total_previous)) if total_previous > 0 else Decimal("0")
    
    summary = ComparisonSummary(
        total_contracts_current=len(current_contracts_dict),
        total_contracts_previous=len(previous_contracts_dict),
        newly_paid=len(newly_paid),
        newly_overdue=len(newly_overdue),
        new_contracts=len(new_contracts),
        missing_contracts=len(missing_contracts),
        corrections=len(corrections),
        unchanged=unchanged,
        total_outstanding_before=total_outstanding_before,
        total_outstanding_after=total_outstanding_after,
        total_received_before=total_received_before,
        total_received_after=total_received_after,
        missing_contracts_detail=[],
        newly_paid_detail=[],
        newly_overdue_detail=[],
        new_contracts_detail=[],
        corrections_detail=[],
        missing_share=missing_share,
    )
    
    all_changes = []
    all_changes.extend(missing_contracts)
    all_changes.extend(newly_paid)
    all_changes.extend(newly_overdue)
    all_changes.extend(new_contracts)
    all_changes.extend(corrections)
    
    return summary, [missing_contracts, newly_paid, newly_overdue, new_contracts, corrections]


async def validate_upload_rules(
    session: AsyncSession,
    upload: Upload,
    existing_upload: Optional[Upload] = None
) -> List[str]:
    """Validate upload business rules. Returns list of warnings/errors."""
    errors = []
    warnings = []
    
    # Check for identical checksum (duplicate file)
    if existing_upload:
        errors.append("File with identical content already uploaded")
    
    # Check as-of date rules
    last_confirmed = await get_last_confirmed_upload(session, upload.as_of_date)
    if last_confirmed:
        if upload.as_of_date < last_confirmed.as_of_date:
            errors.append(f"As-of date {upload.as_of_date} is older than last confirmed upload {last_confirmed.as_of_date}")
        elif upload.as_of_date == last_confirmed.as_of_date:
            warnings.append(f"Same as-of date as last confirmed upload {last_confirmed.as_of_date}")
    
    # Check if last confirmed upload was long ago (e.g., > 60 days)
    if last_confirmed:
        days_diff = (upload.as_of_date - last_confirmed.as_of_date).days
        if days_diff > 60:
            warnings.append(f"Last confirmed upload was {days_diff} days ago (more than 60 days)")
    
    return errors + warnings