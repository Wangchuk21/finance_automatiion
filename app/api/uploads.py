"""Upload API endpoints."""

import json
import os
import shutil
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_session
from app.importer.reader import import_excel_file, calculate_file_checksum
from app.importer.service import upsert_contracts, rollback_upload
from app.importer.comparison import compare_uploads, get_last_confirmed_upload, validate_upload_rules
from app.models import Upload, UploadStatus, User
from app.schemas.uploads import (
    UploadCreate,
    UploadResponse,
    UploadPreviewResponse,
    UploadConfirmRequest,
    UploadStatusResponse,
    ComparisonPreviewResponse,
    MissingContractActionRequest,
    MissingContractActionResponse,
)

router = APIRouter(tags=["uploads"])
logger = get_logger(__name__)

# Placeholder for auth dependency
async def get_current_user() -> User:
    """Placeholder for current user dependency."""
    # TODO: Implement actual auth
    from sqlalchemy import select
    from app.db.session import async_session_maker
    
    async with async_session_maker() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            # Create a default user for development
            user = User(
                username="admin",
                email="admin@example.com",
                hashed_password="dev",
                role="admin",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

# Ensure upload directory exists
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _convert_defaultdict_to_dict(obj: Any) -> Any:
    """Recursively convert defaultdict to dict for JSON serialization."""
    if isinstance(obj, defaultdict):
        return {k: _convert_defaultdict_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, dict):
        return {k: _convert_defaultdict_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_defaultdict_to_dict(v) for v in obj]
    else:
        return obj


def _serialize_summary(obj: Any) -> str:
    """Convert object to JSON string for database storage."""
    clean_obj = _convert_defaultdict_to_dict(obj)
    return json.dumps(clean_obj, default=str)


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    file: UploadFile = File(...),
    as_of_date: str = Form(...),
    sheet_name: Optional[str] = Form(None),
    header_row: Optional[int] = Form(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),  # TODO: implement auth
):
    """
    Step 1: Upload file and parse.
    Returns validation report and preview.
    """
    # Validate file type
    allowed_extensions = {".xlsx", ".xls"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Validate file size
    file_content = await file.read()
    if len(file_content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )
    
    # Calculate checksum
    checksum = calculate_file_checksum_from_bytes(file_content)
    
    # Check for duplicate
    existing = await session.execute(
        select(Upload).where(Upload.checksum == checksum)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File with identical content already uploaded"
        )
    
    # Validate upload rules
    # Get last confirmed upload for date validation
    from app.importer.comparison import get_last_confirmed_upload, validate_upload_rules
    last_confirmed = await get_last_confirmed_upload(session)
    if last_confirmed:
        temp_upload = Upload(as_of_date=date.fromisoformat(as_of_date))
        rules_result = await validate_upload_rules(session, temp_upload)
        # validate_upload_rules returns a list of strings (errors + warnings)
        # Filter to get only errors (those that don't start with "Same as-of date" or "Last confirmed")
        errors = [msg for msg in rules_result if not msg.startswith("Same as-of date") and not msg.startswith("Last confirmed")]
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="; ".join(errors)
            )
    
    # Save file temporarily
    temp_path = UPLOAD_DIR / f"temp_{checksum}{file_ext}"
    with open(temp_path, "wb") as f:
        f.write(file_content)
    
    try:
        # Parse and validate
        contracts, report, preview = import_excel_file(
            str(temp_path),
            sheet_name=sheet_name,
            header_row=header_row,
        )
        
        # Convert defaultdict to dict for JSON serialization
        clean_preview = _convert_defaultdict_to_dict(preview)
        
        # Create upload record
        upload = Upload(
            file_name=file.filename,
            checksum=checksum,
            uploaded_by=current_user.id,
            as_of_date=as_of_date,
            status=UploadStatus.PENDING,
            summary=_serialize_summary(clean_preview),
        )
        session.add(upload)
        await session.flush()
        
        # Store parsed contracts in upload summary for preview
        upload.summary = _serialize_summary({
            **clean_preview,
            "validation_report": report.to_dict(),
            "contracts_count": len(contracts),
            "temp_file": str(temp_path),
        })
        await session.commit()
        
        return UploadResponse(
            id=upload.id,
            file_name=upload.file_name,
            status=upload.status,
            as_of_date=upload.as_of_date,
            uploaded_at=upload.upload_time,
            preview=UploadPreviewResponse(
                contracts_count=len(contracts),
                validation_report=report.to_dict(),
                monthly_breakdown=preview.get("monthly_breakdown", {}),
            ),
        )
    
    except Exception as e:
        logger.error(f"Error parsing upload: {e}")
        # Cleanup temp file
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {str(e)}"
        )


@router.get("/{upload_id}/preview", response_model=UploadPreviewResponse)
async def get_upload_preview(
    upload_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Step 2-3: Get validation report and preview for confirmation."""
    upload = await session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if upload.status != UploadStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Upload already {upload.status.value}"
        )
    
    # Parse JSON string back to dict
    summary = json.loads(upload.summary) if upload.summary else {}
    validation_report = summary.get("validation_report", {})
    
    return UploadPreviewResponse(
        contracts_count=summary.get("contracts_count", 0),
        validation_report=validation_report,
        monthly_breakdown=summary.get("monthly_breakdown", {}),
    )


@router.get("/{upload_id}/comparison", response_model=ComparisonPreviewResponse)
async def get_upload_comparison(
    upload_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get comparison preview between current upload and last confirmed upload."""
    from app.importer.comparison import compare_uploads
    from dataclasses import asdict
    
    upload = await session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if upload.status != UploadStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Upload already {upload.status.value}"
        )
    
    # Run comparison
    summary, changes = await compare_uploads(session, upload_id)
    
    # Check missing share threshold
    missing_share = float(summary.missing_share)
    upload_missing_share = float(upload.missing_share_threshold)
    wrong_file_warning = missing_share > upload_missing_share
    
    # Convert dataclass to dict for Pydantic
    summary_dict = asdict(summary)
    # Convert Decimal to float for JSON serialization
    for key, value in summary_dict.items():
        if isinstance(value, Decimal):
            summary_dict[key] = float(value)
    
    # Flatten the list of lists
    changes_list = []
    for change_list in changes:
        for change in change_list:
            change_dict = asdict(change)
            for key, value in change_dict.items():
                if isinstance(value, Decimal):
                    change_dict[key] = float(value)
            changes_list.append(change_dict)
    
    return ComparisonPreviewResponse(
        summary=summary_dict,
        missing_contracts_detail=[c for c in changes_list if c.get("change_type") == "missing"],
        newly_paid_detail=[c for c in changes_list if c.get("change_type") == "newly_paid"],
        newly_overdue_detail=[c for c in changes_list if c.get("change_type") == "newly_overdue"],
        new_contracts_detail=[c for c in changes_list if c.get("change_type") == "new"],
        corrections_detail=[c for c in changes_list if c.get("change_type") == "correction"],
        wrong_file_warning=wrong_file_warning,
        missing_share=missing_share,
        missing_share_threshold=upload_missing_share,
    )


@router.post("/{upload_id}/missing-action", response_model=MissingContractActionResponse)
async def handle_missing_contracts(
    upload_id: int,
    request: MissingContractActionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Handle missing contract actions: close, keep active, or decide later."""
    from app.models import ContractClosure, ContractState
    
    upload = await session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if upload.status != UploadStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Upload already {upload.status.value}"
        )
    
    # Parse JSON string back to dict
    import json
    summary = json.loads(upload.summary) if upload.summary else {}
    validation_report = summary.get("validation_report", {})
    
    # Re-parse from temp file to get current contracts
    temp_file = summary.get("temp_file")
    if not temp_file or not os.path.exists(temp_file):
        raise HTTPException(400, "Temporary file not found, please re-upload")
    
    contracts, report, preview = import_excel_file(temp_file)
    
    # Get previous upload for comparison
    from app.importer.comparison import compare_uploads, get_last_confirmed_upload
    last_confirmed = await get_last_confirmed_upload(session, upload.as_of_date)
    
    if not last_confirmed:
        raise HTTPException(400, "No previous confirmed upload to compare against")
    
    # Get missing contracts from comparison
    summary_obj, changes = await compare_uploads(session, upload.id)
    missing_contracts = [c for c in changes if c.change_type == "missing"]
    
    # Verify all requested contract IDs are actually missing
    missing_ids = set(m.contract_id for c in missing_contracts)
    requested_ids = set(request.contract_ids)
    if not requested_ids.issubset(missing_ids):
        invalid = requested_ids - missing_ids
        raise HTTPException(400, f"Invalid contract IDs: {invalid}")
    
    processed = 0
    for contract_id in request.contract_ids:
        if request.action == "close":
            if request.reason is None:
                raise HTTPException(400, "Reason required for closing contract")
            
            # Check if contract has balance due
            from app.models import Contract
            contract = await session.get(Contract, contract_id)
            if contract and contract.monthly_deduction and contract.monthly_deduction > 0:
                # Check if balance is zero
                from app.models import Installment
                from sqlalchemy import func
                balance_result = await session.execute(
                    select(func.coalesce(func.sum(Installment.due_amount - Installment.received_amount), 0))
                    .where(Installment.contract_id == contract_id)
                )
                balance = balance_result.scalar() or 0
                
                if balance > 0 and request.reason == "completed":
                    raise HTTPException(
                        400, 
                        f"Contract has balance due ({balance}), cannot mark as 'completed'"
                    )
            
            # Create closure record
            closure = ContractClosure(
                contract_id=contract_id,
                upload_id=upload.id,
                reason=request.reason,
                note=request.note,
                balance_at_closing=0,  # TODO: calculate actual balance
                closed_by=current_user.id,
            )
            session.add(closure)
            
            # Update contract state
            contract = await session.get(Contract, contract_id)
            if contract:
                contract.state = ContractState.CLOSED
            
            processed += 1
            
        elif request.action == "keep_active":
            # Just mark as keep active (no action needed, will remain active)
            processed += 1
            
        elif request.action == "decide_later":
            # Mark for later decision (no action needed)
            processed += 1
    
    # Update upload with missing contracts count
    upload.missing_contracts_count = len(missing_contracts)
    
    await session.commit()
    
    return MissingContractActionResponse(
        processed=processed,
        total_missing=len(missing_contracts),
        action=request.action,
        message=f"Processed {processed} of {len(missing_contracts)} missing contracts"
    )


@router.post("/{upload_id}/confirm", response_model=UploadStatusResponse)
async def confirm_upload(
    upload_id: int,
    request: UploadConfirmRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),  # TODO: implement auth
):
    """
    Step 4: Confirm upload and persist to database.
    Requires TOTP code for security.
    """
    upload = await session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if upload.status != UploadStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Upload already {upload.status.value}"
        )
    
    # TODO: Verify TOTP code
    # if not verify_totp(current_user, request.totp_code):
    #     raise HTTPException(400, "Invalid authenticator code")
    
    # Parse JSON string back to dict
    summary = json.loads(upload.summary) if upload.summary else {}
    
    # Re-parse from temp file
    temp_file = summary.get("temp_file")
    if not temp_file or not os.path.exists(temp_file):
        raise HTTPException(400, "Temporary file not found, please re-upload")
    
    try:
        contracts, report, preview = import_excel_file(temp_file)
        
        if report.has_errors:
            raise HTTPException(
                status_code=400,
                detail="Validation errors found. Cannot confirm."
            )
        
        # Upsert to database
        from app.importer.service import upsert_contracts
        result = await upsert_contracts(session, contracts, upload.id)
        
        # Create installment history records for ALL installments (not just changed ones)
        # This ensures a complete history baseline for future comparisons
        from app.models import Installment, InstallmentHistory
        from sqlalchemy import select
        installments = await session.execute(select(Installment))
        for inst in installments.scalars().all():
            history = InstallmentHistory(
                installment_id=inst.id,
                upload_id=upload.id,
                previous_status=None,
                new_status=inst.status,
                previous_received=None,
                new_received=inst.received_amount,
            )
            session.add(history)
        
        # Update upload status
        upload.status = UploadStatus.CONFIRMED
        upload.summary = _serialize_summary({
            **preview,
            "upsert_result": {
                "contracts_created": result.contracts_created,
                "contracts_updated": result.contracts_updated,
                "installments_created": result.installments_created,
                "installments_updated": result.installments_updated,
                "installments_unchanged": result.installments_unchanged,
            },
        })
        await session.commit()
        
        # Cleanup temp file
        os.unlink(summary.get("temp_file", ""))
        
        return UploadStatusResponse(
            id=upload.id,
            status=upload.status,
            message=f"Upload confirmed: {result.contracts_created} created, {result.contracts_updated} updated",
            details=json.loads(upload.summary) if upload.summary else {},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming upload: {e}")
        raise HTTPException(500, f"Failed to confirm upload: {str(e)}")


@router.post("/{upload_id}/rollback", response_model=UploadStatusResponse)
async def rollback_upload_endpoint(
    upload_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Rollback a confirmed upload."""
    upload = await session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found")
    
    if upload.status != UploadStatus.CONFIRMED:
        raise HTTPException(400, f"Can only rollback confirmed uploads, current: {upload.status.value}")
    
    # TODO: Implement proper rollback using installment_history
    success = await rollback_upload(session, upload_id)
    
    if success:
        upload.status = UploadStatus.ROLLED_BACK
        await session.commit()
        return UploadStatusResponse(
            id=upload.id,
            status=upload.status,
            message="Upload rolled back",
        )
    else:
        raise HTTPException(500, "Rollback failed")


@router.get("", response_model=List[UploadResponse])
async def list_uploads(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List uploads with pagination."""
    from sqlalchemy import select, desc
    
    stmt = select(Upload).order_by(desc(Upload.upload_time)).offset(skip).limit(limit)
    
    if status_filter:
        try:
            status_enum = UploadStatus(status_filter)
            stmt = stmt.where(Upload.status == status_enum)
        except ValueError:
            pass
    
    result = await session.execute(stmt)
    uploads = result.scalars().all()
    
    return [
        UploadResponse(
            id=u.id,
            file_name=u.file_name,
            status=u.status,
            as_of_date=u.as_of_date,
            uploaded_at=u.upload_time,
        )
        for u in uploads
    ]


def calculate_file_checksum_from_bytes(content: bytes) -> str:
    """Calculate SHA256 from bytes."""
    import hashlib
    return hashlib.sha256(content).hexdigest()