"""Helpers for the global "as-of month" report filter.

An as-of value is always normalised to the first day of the selected month.
It is applied as an upper bound on ``Installment.due_month`` so every
financial figure is calculated using instalments due on or before that month.
"""

from datetime import date, datetime
from typing import Optional


def parse_as_of_month(value: Optional[str]) -> Optional[date]:
    """Parse ``YYYY-MM`` or ``YYYY-MM-DD`` into the first day of that month.

    Invalid or empty values return ``None`` (meaning "no cutoff").
    """
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text[:7], "%Y-%m").date()
        return date(parsed.year, parsed.month, 1)
    except (ValueError, TypeError):
        return None


def as_of_label(value: Optional[date]) -> str:
    """Human-readable label used by the UI."""
    return value.strftime("%b %Y") if value else "Latest"
