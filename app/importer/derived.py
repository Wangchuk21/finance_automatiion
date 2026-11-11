"""Derived contract columns equivalent to the Excel "master data" sheet.

The upload sheet only needs the input columns (everything up to the last month
column, e.g. ``Sep-26`` / ``Salary Sep 27``). Columns such as *EMI Received*,
*EMI receivable*, *Balance Due*, *Overall Outstanding*, *Advance*, *Age (Days)*
and *Alert* are calculated here instead of being read from the file.

Formulas mirror the spreadsheet:
    EMI Received        = SUM(all month cells)
    No of Ins. To Be Recd = months from Posting Date through as-of, capped at EMI Months
    EMI receivable      = No of Ins. To Be Recd * Monthly Deduction + GST
    Advance             = MAX(0, EMI Received - EMI receivable)
    Balance Due         = EMI receivable - EMI Received + Advance
    Overall Outstanding = Sales Amt + GST - EMI Received
    No on Inst. Due     = Balance Due / Monthly Deduction
    Age (Days)          = 0 / 30 / 60 / 90 / 120 / 121 bucket from No on Inst. Due
    Alert               = Normal / Watch / Follow-up / Critical
"""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _received_of(inst: Any) -> Decimal:
    """Received amount of one installment.

    Parsed rows from the importer carry ``external_amount``/``salary_amount``
    and leave ``received_amount`` for the DB layer to fill, so fall back to
    their sum when the direct value is absent.
    """
    received = _to_decimal(_field(inst, "received_amount"))
    if received == 0:
        external = _field(inst, "external_amount")
        salary = _field(inst, "salary_amount")
        if external is not None or salary is not None:
            received = _to_decimal(external) + _to_decimal(salary)
    return received


@dataclass(frozen=True)
class ContractMetrics:
    """Calculated columns for one contract."""

    emi_received: Decimal
    no_of_ins_to_be_recd: int
    emi_receivable: Decimal
    balance_due: Decimal
    no_on_inst_due: Decimal
    overall_outstanding: Decimal
    advance: Decimal
    age_days: int
    alert: str
    aging_bucket: str

    def as_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "emi_received",
            "emi_receivable",
            "balance_due",
            "no_on_inst_due",
            "overall_outstanding",
            "advance",
        ):
            data[key] = float(data[key])
        return data


def _age_bucket(no_on_inst_due: Decimal) -> tuple[int, str, str]:
    """Map installments-due to the spreadsheet's 30-day buckets.

    Mirrors the sheet's nested IF exactly: only whole values 1-4 map to
    30/60/90/120; any other non-zero value (including fractions such as 2.1)
    maps to 121.
    """
    if no_on_inst_due == 0:
        age = 0
    elif no_on_inst_due == 1:
        age = 30
    elif no_on_inst_due == 2:
        age = 60
    elif no_on_inst_due == 3:
        age = 90
    elif no_on_inst_due == 4:
        age = 120
    else:
        age = 121

    if age == 0:
        alert = "Normal"
    elif age == 30:
        alert = "Watch"
    elif age == 60:
        alert = "Follow-up"
    else:
        alert = "Critical"

    if age <= 30:
        bucket = "0-30"
    elif age <= 60:
        bucket = "31-60"
    elif age <= 90:
        bucket = "61-90"
    elif age <= 120:
        bucket = "91-120"
    else:
        bucket = "120+"

    return age, alert, bucket


def compute_contract_metrics(
    *,
    monthly_deduction: Any = None,
    gst: Any = None,
    sales_amount: Any = None,
    emi_months: Any = None,
    start_date: Optional[date] = None,
    as_of: Optional[date] = None,
    installments: Iterable[Any] = (),
) -> ContractMetrics:
    """Calculate the spreadsheet's derived columns for a single contract."""
    monthly = _to_decimal(monthly_deduction)
    tax = _to_decimal(gst)
    sales = _to_decimal(sales_amount)
    as_of = as_of or date.today()

    inst_list = list(installments)
    received = _money(sum((_received_of(i) for i in inst_list), ZERO))

    # Number of installments that should have been received by the as-of date.
    # When the contract is fully settled against Sales + GST the spreadsheet
    # counts the whole tenor; otherwise it counts the months elapsed so far.
    outstanding = _money(sales + tax - received)
    if emi_months and start_date:
        try:
            emi = int(emi_months)
            elapsed = (
                (as_of.year - start_date.year) * 12
                + (as_of.month - start_date.month)
                + 1
            )
            no_of_ins = emi if outstanding == 0 else max(0, min(emi, elapsed))
        except (TypeError, ValueError):
            no_of_ins = sum(
                1 for i in inst_list if _field(i, "due_amount") is not None
            )
    else:
        no_of_ins = sum(1 for i in inst_list if _field(i, "due_amount") is not None)

    receivable = _money(no_of_ins * monthly + tax)
    advance = _money(max(ZERO, received - receivable))
    balance = _money(receivable - received + advance)

    if outstanding == 0 or monthly == 0:
        no_on_inst_due = ZERO
    else:
        no_on_inst_due = (balance / monthly).quantize(CENT, rounding=ROUND_HALF_UP)

    age, alert, bucket = _age_bucket(no_on_inst_due)

    return ContractMetrics(
        emi_received=received,
        no_of_ins_to_be_recd=no_of_ins,
        emi_receivable=receivable,
        balance_due=balance,
        no_on_inst_due=no_on_inst_due,
        overall_outstanding=outstanding,
        advance=advance,
        age_days=age,
        alert=alert,
        aging_bucket=bucket,
    )


def compute_contract_metrics_for_row(
    contract: dict,
    as_of: Optional[date] = None,
) -> ContractMetrics:
    """Convenience wrapper for a parsed contract dict (with ``installments``)."""
    start = contract.get("start_date") or contract.get("contract_date")
    if isinstance(start, str) and start:
        try:
            start = date.fromisoformat(start[:10])
        except ValueError:
            start = None

    return compute_contract_metrics(
        monthly_deduction=contract.get("monthly_deduction"),
        gst=contract.get("gst"),
        sales_amount=contract.get("sales_amount"),
        emi_months=contract.get("emi_months"),
        start_date=start,
        as_of=as_of,
        installments=contract.get("installments", []),
    )
