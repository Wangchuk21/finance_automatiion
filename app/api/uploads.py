"""Upload API endpoints."""

import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_session
from app.importer.reader import import_excel_file, calculate_file_checksum
from app.importer.service import upsert_contracts, rollback_upload
from app.models import Upload, UploadStatus, User
from app.schemas.uploads import (
    UploadCreate,
    UploadResponse,
    UploadPreviewResponse,
    UploadConfirmRequest,
    UploadStatusResponse,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])
logger = get_logger(__name__)

# Ensure upload directory exists
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
        
        # Create upload record
        upload = Upload(
            file_name=file.filename,
            checksum=checksum,
            uploaded_by=current_user.id,
            as_of_date=as_of_date,
            status=UploadStatus.PENDING,
            summary=preview,
        )
        session.add(upload)
        await session.flush()
        
        # Store parsed contracts in upload summary for preview
        upload.summary = {
            **preview,
            "validation_report": report.to_dict(),
            "contracts_count": len(contracts),
            "temp_file": str(temp_path),
        }
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
    
    summary = upload.summary or {}
    validation_report = summary.get("validation_report", {})
    
    return UploadPreviewResponse(
        contracts_count=summary.get("contracts_count", 0),
        validation_report=validation_report,
        monthly_breakdown=summary.get("monthly_breakdown", {}),
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
    
    # Re-parse from temp file
    summary = upload.summary or {}
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
        result = await upsert_contracts(session, contracts, upload_id)
        
        # Update upload status
        upload.status = UploadStatus.CONFIRMED
        upload.summary = {
            **preview,
            "upsert_result": {
                "contracts_created": result.contracts_created,
                "contracts_updated": result.contracts_updated,
                "installments_created": result.installments_created,
                "installments_updated": result.installments_updated,
                "installments_unchanged": result.installments_unchanged,
            },
        }
        await session.commit()
        
        # Cleanup temp file
        os.unlink(temp_file)
        
        return UploadStatusResponse(
            id=upload.id,
            status=upload.status,
            message=f"Upload confirmed: {result.contracts_created} created, {result.contracts_updated} updated",
            details=upload.summary,
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


def calculate_file_checksum_from_bytes(content: bytes) -> str:
    """Calculate SHA256 from bytes."""
    import hashlib
    return hashlib.sha256(content).hexdigest()