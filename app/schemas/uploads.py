"""Pydantic schemas for uploads API."""

import calendar
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _parse_as_of_date(v: Any) -> date:
    """
    Accept:
      - datetime.date objects  → returned as-is
      - "YYYY-MM-DD" strings  → parsed as date
      - "YYYY-MM" strings     → converted to the LAST day of that month
    Reject:
      - dates in the future   → HTTP 422
    """
    if isinstance(v, date):
        parsed = v
    elif isinstance(v, str):
        v = v.strip()
        if re.fullmatch(r"\d{4}-\d{2}", v):
            year, month = int(v[:4]), int(v[5:7])
            last_day = calendar.monthrange(year, month)[1]
            parsed = date(year, month, last_day)
        else:
            try:
                parsed = date.fromisoformat(v)
            except ValueError:
                raise ValueError(
                    f"Invalid date format '{v}'. Use YYYY-MM-DD or YYYY-MM."
                )
    else:
        raise ValueError("as_of_date must be a date string.")

    if parsed > date.today():
        raise ValueError("as_of_date cannot be in the future.")
    return parsed


class UploadCreate(BaseModel):
    """Request to create an upload."""
    file_name: str
    as_of_date: date
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None

    @field_validator("as_of_date", mode="before")
    @classmethod
    def validate_as_of_date(cls, v: Any) -> date:
        return _parse_as_of_date(v)


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
    id: Optional[int] = None
    contracts_count: int
    validation_report: Dict[str, Any]
    monthly_breakdown: Dict[str, Dict[str, float]]
    totals: Optional[Dict[str, Any]] = None


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
    # TEMPORARY - replace with real TOTP in M3
    totp_code: Optional[str] = None
    code: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""


class UploadRollbackRequest(BaseModel):
    """Request to rollback an upload."""
    # TEMPORARY - replace with real TOTP in M3
    totp_code: Optional[str] = None
    code: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""


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
    # TEMPORARY - replace with real TOTP in M3
    code: Optional[str] = None
    totp_code: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""


class MissingContractActionResponse(BaseModel):
    """Response for missing contract action."""
    processed: int
    total_missing: int
    action: str
    message: str


class CloseContractRequest(BaseModel):
    """Request to close a contract."""
    # TEMPORARY - replace with real TOTP in M3
    code: Optional[str] = None
    totp_code: Optional[str] = None
    reason: Optional[str] = "manual_close"
    note: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""


class CloseContractResponse(BaseModel):
    """Response for closing a contract."""
    contract_id: int
    status: str
    message: str


# ============================================================================
# Customer Upload Schemas (static contract/customer data)
# ============================================================================

class CustomerUploadCreate(BaseModel):
    """Request to create a customer upload."""
    file_name: str
    as_of_date: date
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None

    @field_validator("as_of_date", mode="before")
    @classmethod
    def validate_as_of_date(cls, v: Any) -> date:
        return _parse_as_of_date(v)


class CustomerUploadPreviewResponse(BaseModel):
    """Preview response for customer upload confirmation."""
    id: Optional[int] = None
    contracts_count: int
    validation_report: Dict[str, Any]
    new_customers: int
    updated_customers: int
    customers_with_errors: int


class CustomerUploadResponse(BaseModel):
    """Customer upload response."""
    id: int
    file_name: str
    status: str
    as_of_date: date
    uploaded_at: datetime
    preview: Optional[CustomerUploadPreviewResponse] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerUploadConfirmRequest(BaseModel):
    """Request to confirm a customer upload."""
    totp_code: Optional[str] = None
    code: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""


# ============================================================================
# Payment Upload Schemas (monthly installment/payment data)
# ============================================================================

class PaymentUploadCreate(BaseModel):
    """Request to create a payment upload."""
    file_name: str
    as_of_date: date
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None

    @field_validator("as_of_date", mode="before")
    @classmethod
    def validate_as_of_date(cls, v: Any) -> date:
        return _parse_as_of_date(v)


class PaymentUploadPreviewResponse(BaseModel):
    """Preview response for payment upload confirmation."""
    id: Optional[int] = None
    contracts_count: int
    validation_report: Dict[str, Any]
    monthly_breakdown: Dict[str, Dict[str, float]]
    totals: Optional[Dict[str, Any]] = None
    payments_updated: int
    payments_new: int


class PaymentUploadResponse(BaseModel):
    """Payment upload response."""
    id: int
    file_name: str
    status: str
    as_of_date: date
    uploaded_at: datetime
    preview: Optional[PaymentUploadPreviewResponse] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentUploadConfirmRequest(BaseModel):
    """Request to confirm a payment upload."""
    totp_code: Optional[str] = None
    code: Optional[str] = None

    def get_code(self) -> str:
        return self.code or self.totp_code or ""