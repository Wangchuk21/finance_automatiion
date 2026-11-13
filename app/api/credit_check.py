"""Customer credit check API endpoint."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.installments import determine_installment_status
from app.db.session import get_session
from app.models import Contract, ContractState, Installment, InstallmentStatus, User

router = APIRouter(tags=["credit-check"])


class CreditScoreResponse(BaseModel):
    """Credit check response for a customer."""
    cid: str
    customer_name: str
    mobile: Optional[str] = None
    
    # Contract summary
    total_contracts: int = 0
    active_contracts: int = 0
    closed_contracts: int = 0
    overdue_contracts: int = 0
    
    # Financial summary
    total_outstanding: float = 0.0
    total_balance_due: float = 0.0
    total_monthly_emi: float = 0.0
    total_collected: float = 0.0
    
    # Payment behavior
    total_installments: int = 0
    paid_installments: int = 0
    overdue_installments: int = 0
    partial_installments: int = 0
    payment_rate: float = 0.0  # % of installments paid on time
    
    # Risk indicators
    max_days_overdue: int = 0
    has_overdue: bool = False
    multiple_active_loans: bool = False
    high_balance_due_ratio: bool = False
    
    # Credit score (0-100)
    credit_score: int = 0
    risk_level: str = "unknown"  # low, medium, high, critical
    recommendation: str = ""
    
    # Contract details
    contracts: list["CreditContractSummary"] = []


class CreditContractSummary(BaseModel):
    reference: str
    item: str
    brand: str
    start_date: str
    end_date: str
    status: str
    monthly_emi: float
    outstanding: float
    balance_due: float
    months_left: int
    is_overdue: bool
    overdue_amount: float


def calculate_credit_score(
    active_contracts: int,
    overdue_contracts: int,
    total_balance_due: float,
    total_monthly_emi: float,
    total_outstanding: float,
    payment_rate: float,
    max_days_overdue: int,
    has_overdue: bool,
) -> tuple[int, str, str]:
    """Calculate credit score (0-100) and risk level."""
    score = 100
    
    # Deduct for overdue contracts
    if overdue_contracts > 0:
        score -= overdue_contracts * 20
    
    # Deduct for multiple active loans
    if active_contracts > 3:
        score -= (active_contracts - 3) * 10
    elif active_contracts > 1:
        score -= (active_contracts - 1) * 5
    
    # Deduct for balance due ratio
    if total_monthly_emi > 0:
        balance_ratio = total_balance_due / total_monthly_emi
        if balance_ratio > 3:
            score -= 20
        elif balance_ratio > 2:
            score -= 10
        elif balance_ratio > 1:
            score -= 5
    
    # Deduct for payment rate
    if payment_rate < 0.8:
        score -= 30
    elif payment_rate < 0.9:
        score -= 15
    elif payment_rate < 0.95:
        score -= 5
    
    # Deduct for max days overdue
    if max_days_overdue > 90:
        score -= 25
    elif max_days_overdue > 60:
        score -= 15
    elif max_days_overdue > 30:
        score -= 10
    elif max_days_overdue > 0:
        score -= 5
    
    score = max(0, min(100, score))
    
    if score >= 80:
        risk = "low"
        rec = "Excellent creditworthiness. Approve new EMI."
    elif score >= 60:
        risk = "medium"
        rec = "Good creditworthiness. Approve with standard terms."
    elif score >= 40:
        risk = "high"
        rec = "Moderate risk. Require additional verification or co-signer."
    else:
        risk = "critical"
        rec = "High risk. Do not approve new EMI without strong justification."
    
    return score, risk, rec


@router.get("/check/{cid}", response_model=CreditScoreResponse)
async def check_customer_credit(
    cid: str,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """
    Check customer creditworthiness by CID.
    Returns credit score, risk level, and detailed contract analysis.
    """
    # Find contracts by CID
    stmt = select(Contract).where(Contract.cid == cid)
    result = await session.execute(stmt)
    contracts = result.scalars().all()
    
    if not contracts:
        raise HTTPException(
            status_code=404,
            detail=f"No contracts found for CID: {cid}"
        )
    
    customer_name = contracts[0].customer or "Unknown"
    mobile = contracts[0].mobile
    
    # Calculate metrics
    total_contracts = len(contracts)
    active_contracts = sum(1 for c in contracts if c.state == ContractState.ACTIVE)
    closed_contracts = sum(1 for c in contracts if c.state == ContractState.CLOSED)
    
    # Get all installments for these contracts
    contract_ids = [c.id for c in contracts]
    installments_stmt = select(Installment).where(Installment.contract_id.in_(contract_ids))
    installments_result = await session.execute(installments_stmt)
    installments = installments_result.scalars().all()
    
    # Financial calculations - compute from installments
    total_balance_due = 0.0
    total_outstanding = 0.0
    total_collected = 0.0
    total_monthly_emi = 0.0
    
    for c in contracts:
        # Get installments for this contract
        c_installments = [i for i in installments if i.contract_id == c.id]
        
        # Total due for this contract
        contract_due = sum(float(i.due_amount or 0) for i in c_installments)
        # Total received for this contract
        contract_received = sum(float(i.received_amount or 0) for i in c_installments)
        # Balance due
        contract_balance_due = max(0.0, contract_due - contract_received)
        # Outstanding (sales + GST - received)
        sales = float(c.sales_amount or 0)
        gst = float(c.gst or 0)
        outstanding = max(0.0, sales + gst - contract_received)
        # Collected
        collected = contract_received
        
        total_balance_due += contract_balance_due
        total_outstanding += outstanding
        total_collected += collected
        
        if c.state == ContractState.ACTIVE:
            total_monthly_emi += float(c.monthly_deduction or 0)
    
    # Installment analysis
    total_installments = len(installments)
    statuses = [
        determine_installment_status(
            i.due_amount,
            Decimal(i.received_amount or 0),
            cell_status=i.cell_status,
            due_month=i.due_month,
        )
        for i in installments
    ]
    paid_installments = sum(1 for s in statuses if s == InstallmentStatus.PAID)
    overdue_installments = sum(1 for s in statuses if s == InstallmentStatus.OVERDUE)
    partial_installments = sum(1 for s in statuses if s == InstallmentStatus.PARTIAL)
    
    payment_rate = paid_installments / total_installments if total_installments > 0 else 1.0
    
    # Overdue contracts (contracts with balance_due > 0)
    overdue_contracts = 0
    for c in contracts:
        c_installments = [i for i in installments if i.contract_id == c.id]
        contract_due = sum(float(i.due_amount or 0) for i in c_installments)
        contract_received = sum(float(i.received_amount or 0) for i in c_installments)
        contract_balance_due = max(0.0, contract_due - contract_received)
        if contract_balance_due > 0:
            overdue_contracts += 1
    
    # Max days overdue
    max_days_overdue = 0
    for c in contracts:
        if c.end_date:
            c_installments = [i for i in installments if i.contract_id == c.id]
            contract_due = sum(float(i.due_amount or 0) for i in c_installments)
            contract_received = sum(float(i.received_amount or 0) for i in c_installments)
            contract_balance_due = max(0.0, contract_due - contract_received)
            if contract_balance_due > 0:
                days = (date.today() - c.end_date).days
                if days > max_days_overdue:
                    max_days_overdue = days
    
    has_overdue = overdue_contracts > 0
    multiple_active_loans = active_contracts > 1
    high_balance_due_ratio = (
        total_monthly_emi > 0 and 
        (total_balance_due / total_monthly_emi > 2)
    )
    
# Calculate credit score
    credit_score, risk_level, recommendation = calculate_credit_score(
        active_contracts=active_contracts,
        overdue_contracts=overdue_contracts,
        total_balance_due=total_balance_due,
        total_monthly_emi=total_monthly_emi,
        total_outstanding=total_outstanding,
        payment_rate=payment_rate,
        max_days_overdue=max_days_overdue,
        has_overdue=has_overdue,
    )
    
    # Build contract summaries
    contract_summaries = []
    for c in contracts:
        c_installments = [i for i in installments if i.contract_id == c.id]
        contract_due = sum(float(i.due_amount or 0) for i in c_installments)
        contract_received = sum(float(i.received_amount or 0) for i in c_installments)
        contract_balance_due = max(0.0, contract_due - contract_received)
        
        sales = float(c.sales_amount or 0)
        gst = float(c.gst or 0)
        outstanding = max(0.0, sales + gst - contract_received)
        is_overdue = contract_balance_due > 0
        overdue_amount = contract_balance_due if is_overdue else 0.0
        
        # Calculate months left
        months_left = 0
        if c.end_date:
            today = date.today()
            if c.end_date >= today:
                months_left = (c.end_date.year - today.year) * 12 + (c.end_date.month - today.month)
            else:
                months_left = 0
        
        contract_summaries.append(CreditContractSummary(
            reference=c.reference,
            item=c.item or "",
            brand=c.brand or "",
            start_date=c.start_date.isoformat() if c.start_date else "",
            end_date=c.end_date.isoformat() if c.end_date else "",
            status=c.state.value if hasattr(c.state, 'value') else str(c.state),
            monthly_emi=float(c.monthly_deduction or 0),
            outstanding=outstanding,
            balance_due=contract_balance_due,
            months_left=months_left,
            is_overdue=is_overdue,
            overdue_amount=overdue_amount,
        ))
    
    return CreditScoreResponse(
        cid=cid,
        customer_name=customer_name,
        mobile=mobile,
        total_contracts=total_contracts,
        active_contracts=active_contracts,
        closed_contracts=closed_contracts,
        overdue_contracts=overdue_contracts,
        total_outstanding=total_outstanding,
        total_balance_due=total_balance_due,
        total_monthly_emi=total_monthly_emi,
        total_collected=total_collected,
        total_installments=total_installments,
        paid_installments=paid_installments,
        overdue_installments=overdue_installments,
        partial_installments=partial_installments,
        payment_rate=payment_rate,
        max_days_overdue=max_days_overdue,
        has_overdue=has_overdue,
        multiple_active_loans=multiple_active_loans,
        high_balance_due_ratio=high_balance_due_ratio,
        credit_score=credit_score,
        risk_level=risk_level,
        recommendation=recommendation,
        contracts=contract_summaries,
    )