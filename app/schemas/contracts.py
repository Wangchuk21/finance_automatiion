"""Pydantic schemas for the contracts API."""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ContractUpdateRequest(BaseModel):
    """Fields an admin may edit on a contract.

    ``reference`` and ``state`` are intentionally excluded: the reference is the
    import key, and state changes go through the close-contract endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    customer: Optional[str] = None
    cid: Optional[str] = None
    mobile: Optional[str] = None
    item: Optional[str] = None
    brand: Optional[str] = None
    region: Optional[str] = None
    cost_center: Optional[str] = None
    ministry_agency: Optional[str] = None
    payment_type: Optional[str] = None
    emi_months: Optional[int] = Field(None, ge=0)
    monthly_deduction: Optional[Decimal] = Field(None, ge=0)
    sales_amount: Optional[Decimal] = Field(None, ge=0)
    gst: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
