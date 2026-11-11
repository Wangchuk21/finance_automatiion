"""Shared contract metric calculations."""

import math
from decimal import Decimal
from typing import Optional


def calculate_months_left(
    outstanding: float,
    monthly_deduction: Optional[Decimal],
    emi_months: Optional[int],
) -> Optional[int]:
    """EMI months still to be paid, based on the remaining amount.

    Rounded up and capped at the contract's total tenor. Returns None when the
    contract has no monthly deduction.
    """
    if not monthly_deduction or Decimal(monthly_deduction) <= 0:
        return None
    if outstanding <= 0:
        return 0
    left = math.ceil(outstanding / float(monthly_deduction))
    if emi_months:
        left = min(left, int(emi_months))
    return max(0, int(left))
