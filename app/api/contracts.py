"""
Contracts API router.

# TEMPORARY - replace with real TOTP in M3
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.confirm import verify_confirm_code
from app.db.session import get_session
from app.models import Contract, ContractClosure, ContractState, User
from app.api.uploads import get_current_user
from app.schemas.uploads import CloseContractRequest, CloseContractResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{contract_id}/close", response_model=CloseContractResponse)
async def close_contract_endpoint(
    contract_id: int,
    request: CloseContractRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
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
