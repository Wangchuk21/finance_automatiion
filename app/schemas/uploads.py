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


# M2: Comparison and missing contract schemas
class ContractComparisonSchema(BaseModel):
    """Single contract comparison result."""
    contract_id: int
    reference: str
    customer: Optional[str] = None
    cid: Optional[str] = None
    region: Optional[str] = None
    previous_balance: Decimal
    current_balance: Decimal
    previous_status: str
    current_status: str
    change_type: str
    details: List[str] = []


class ComparisonSummarySchema(BaseModel):
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


class ComparisonPreviewResponse(BaseModel):
    """Comparison preview response."""
    summary: ComparisonSummarySchema
    missing_contracts_detail: List[ContractComparisonSchema] = []
    newly_paid_detail: List[ContractComparisonSchema] = []
    newly_overdue_detail: List[ContractComparisonSchema] = []
    new_contracts_detail: List[ContractComparisonSchema] = []
    corrections_detail: List[ContractComparisonSchema] = []
    wrong_file_warning: bool = False
    missing_share: float
    missing_share_threshold: float


class MissingContractActionRequest(BaseModel):
    """Request to handle missing contracts."""
    contract_ids: List[int]
    action: str  # "close", "keep_active", "decide_later"
    reason: Optional[str] = None
    note: Optional[str] = None


class MissingContractActionResponse(BaseModel):
    """Response for missing contract action."""
    processed: int
    total_missing: int
    action: str
    message: str


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