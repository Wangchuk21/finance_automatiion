"""Pydantic schemas for uploads API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UploadCreate(BaseModel):
    """Request to create an upload."""
    file_name: str
    as_of_date: date
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None


class ValidationIssueSchema(BaseModel):
    """Single validation issue."""
    severity: str
    code: str
    message: str
    row: Optional[int] = None
    column: Optional[str] = None
    value: Optional[str] = None


class ValidationReportSchema(BaseModel):
    """Complete validation report."""
    has_errors: bool
    has_warnings: bool
    error_count: int
    warning_count: int
    issues: List[ValidationIssueSchema]
    stats: Dict[str, Any]


class UploadPreviewResponse(BaseModel):
    """Preview response for upload confirmation."""
    contracts_count: int
    validation_report: Dict[str, Any]
    monthly_breakdown: Dict[str, Dict[str, float]]


class UploadResponse(BaseModel):
    """Upload response."""
    id: int
    file_name: str
    status: str
    as_of_date: date
    uploaded_at: datetime
    preview: Optional[UploadPreviewResponse] = None

    model_config = ConfigDict(from_attributes=True)


class UploadConfirmRequest(BaseModel):
    """Request to confirm an upload."""
    totp_code: str = Field(..., min_length=6, max_length=6)


class UploadStatusResponse(BaseModel):
    """Status response after confirm/rollback."""
    id: int
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None