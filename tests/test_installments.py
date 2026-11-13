"""Tests for the shared installment status rule."""

from datetime import date
from decimal import Decimal

from app.core.installments import determine_installment_status, month_start
from app.models import InstallmentStatus


AS_OF = date(2026, 11, 13)


def test_month_start():
    assert month_start(date(2026, 11, 13)) == date(2026, 11, 1)


def test_paid_when_fully_received():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("4660.00"), due_month=date(2026, 9, 1), as_of=AS_OF
        )
        == InstallmentStatus.PAID
    )


def test_overpaid_is_paid():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("9320.00"), due_month=date(2026, 9, 1), as_of=AS_OF
        )
        == InstallmentStatus.PAID
    )


def test_partial_when_some_received():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("1000.00"), due_month=date(2025, 9, 1), as_of=AS_OF
        )
        == InstallmentStatus.PARTIAL
    )


def test_past_unpaid_month_is_overdue():
    # September is unpaid while October has been received: September is due.
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("0"), due_month=date(2026, 9, 1), as_of=AS_OF
        )
        == InstallmentStatus.OVERDUE
    )


def test_previous_year_unpaid_month_is_overdue():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("0"), due_month=date(2025, 6, 1), as_of=AS_OF
        )
        == InstallmentStatus.OVERDUE
    )


def test_current_month_unpaid_is_pending():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("0"), due_month=date(2026, 11, 1), as_of=AS_OF
        )
        == InstallmentStatus.PENDING
    )


def test_future_month_unpaid_is_pending():
    assert (
        determine_installment_status(
            Decimal("4660.00"), Decimal("0"), due_month=date(2027, 3, 1), as_of=AS_OF
        )
        == InstallmentStatus.PENDING
    )


def test_missing_due_month_unpaid_is_pending():
    assert (
        determine_installment_status(Decimal("4660.00"), Decimal("0"), as_of=AS_OF)
        == InstallmentStatus.PENDING
    )


def test_no_due_amount_outside_schedule():
    assert (
        determine_installment_status(None, Decimal("0"), as_of=AS_OF)
        == InstallmentStatus.PENDING
    )
    assert (
        determine_installment_status(None, Decimal("500.00"), as_of=AS_OF)
        == InstallmentStatus.PAID
    )


def test_cell_status_does_not_override_amounts():
    # The Excel "not received" marker must not hide a genuinely overdue month.
    assert (
        determine_installment_status(
            Decimal("4660.00"),
            Decimal("0"),
            cell_status="not_received",
            due_month=date(2026, 9, 1),
            as_of=AS_OF,
        )
        == InstallmentStatus.OVERDUE
    )
