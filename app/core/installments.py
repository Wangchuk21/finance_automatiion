"""Shared installment status rules.

Installment statuses are time-dependent: an installment that is unpaid becomes
``overdue`` once its due month is before the current month. The importer and the
read API must agree on this, so the rule lives here.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from app.models import InstallmentStatus


def month_start(value: date) -> date:
    """Return the first day of ``value``'s month."""
    return date(value.year, value.month, 1)


def determine_installment_status(
    due_amount: Optional[Decimal],
    received_amount: Decimal,
    cell_status: Optional[str] = None,
    as_of: Optional[date] = None,
    due_month: Optional[date] = None,
) -> InstallmentStatus:
    """Return the status for one installment.

    - No due amount (outside the schedule): paid if anything was received.
    - Fully received: ``paid``.
    - Partly received: ``partial``.
    - Nothing received: ``overdue`` when the due month is in the past,
      otherwise ``pending``.
    """
    received = Decimal(received_amount or 0)

    if due_amount is None:
        return (
            InstallmentStatus.PAID
            if received > Decimal("0")
            else InstallmentStatus.PENDING
        )

    due = Decimal(due_amount)
    if received >= due:
        return InstallmentStatus.PAID
    if received > Decimal("0"):
        return InstallmentStatus.PARTIAL

    # Nothing received. Only a past month counts as overdue; the current month
    # is still within its payment window.
    today = as_of or date.today()
    if due_month is not None and month_start(due_month) < month_start(today):
        return InstallmentStatus.OVERDUE

    return InstallmentStatus.PENDING
