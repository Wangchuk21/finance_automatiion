"""Specialized parsers for different Excel formats."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.importer.column_map import (
    parse_amount,
    parse_date,
    clean_cid,
    clean_customer,
    clean_mobile,
    calculate_installment_due,
)


"""Specialized parsers for different Excel formats."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
import re

from app.importer.column_map import (
    parse_amount,
    parse_date,
    clean_cid,
    clean_customer,
    clean_mobile,
    calculate_installment_due,
)


def parse_salary_slip(
    rows: List[Dict[str, Any]],
    as_of: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse ERPNext Salary Slip format.

    Expected columns:
    - Reference Number (contract reference like BT26...)
    - Employee / Employee Name
    - Month (1-12)
    - Fiscal Year
    - Salary Component (e.g., "BTL Sales", "Bhutan Telecom")
    - Amount
    """
    warnings: List[str] = []

    # Group by Reference Number + Month + Year
    grouped: Dict[Tuple[str, int, int], Dict[str, Any]] = defaultdict(lambda: {
        "reference": None,
        "employee": None,
        "employee_name": None,
        "month": None,
        "year": None,
        "components": defaultdict(Decimal),
    })

    for row in rows:
        ref = str(row.get("Reference Number", "")).strip()
        if not ref or ref.lower() in ("none", "null", ""):
            continue

        employee = str(row.get("Employee", "")).strip()
        employee_name = str(row.get("Employee Name", "")).strip()
        month_raw = row.get("Month")
        fiscal_year = row.get("Fiscal Year")
        component = str(row.get("Salary Component", "")).strip()
        amount = parse_amount(row.get("Amount"))

        if amount is None:
            continue

        # Parse month and year
        try:
            month = int(month_raw) if month_raw else 1
            year = int(fiscal_year) if fiscal_year else (as_of.year if as_of else 2024)
        except (ValueError, TypeError):
            month = 1
            year = as_of.year if as_of else 2024

        key = (ref, month, year)
        group = grouped[key]
        group["reference"] = ref
        group["employee"] = employee
        group["employee_name"] = employee_name
        group["month"] = month
        group["year"] = year
        group["components"][component] += amount

    # Convert to contract format
    contracts = []
    for (ref, month, year), data in grouped.items():
        components = data["components"]

        # Map salary components to payment types
        received_amount = Decimal("0")
        salary_amount = Decimal("0")
        external_amount = Decimal("0")

        for comp, amt in components.items():
            comp_lower = comp.lower()
            if "btl" in comp_lower or "sales" in comp_lower or "received" in comp_lower:
                received_amount += amt
            elif "bhutan telecom" in comp_lower or "telecom" in comp_lower or "external" in comp_lower:
                external_amount += amt
            elif "salary" in comp_lower or "basic" in comp_lower or "allowance" in comp_lower:
                salary_amount += amt
            else:
                received_amount += amt

        due_month = date(year, month, 1)

        contracts.append({
            "reference": ref,
            "customer": data["employee_name"] or data["employee"],
            "cid": data["employee"],
            "installments": [{
                "due_month": due_month,
                "received_amount": received_amount,
                "salary_amount": salary_amount,
                "external_amount": external_amount,
                "due_amount": None,
            }],
        })

    return contracts, warnings


def parse_bank_ledger(
    rows: List[Dict[str, Any]],
    as_of: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse Payment.xlsx bank ledger format (journal entries).

    Expected columns (from ERPNext):
    - Posting Date
    - Against Account (Party name with CID)
    - Party Type
    - Party
    - Debit (BTN) / Credit (BTN) - Debit = received
    - Cost Center (region)
    - Against Voucher (contract reference like BT26...)
    - Remarks (contains "EMI" and payment mode)
    """
    warnings: List[str] = []

    # Group by contract reference + month
    grouped: Dict[Tuple[str, int, int], Dict[str, Any]] = defaultdict(lambda: {
        "reference": None,
        "customer": None,
        "cid": None,
        "region": None,
        "month": None,
        "year": None,
        "received_amount": Decimal("0"),
        "payment_mode": None,
    })

    for row in rows:
        # Contract reference is in "Against Voucher" column
        ref = str(row.get("Against Voucher", "")).strip()
        if not ref or not ref.startswith("BT"):
            continue

        # Party name is in "Against Account" column (not "Party")
        party = str(row.get("Against Account", "")).strip()
        debit = parse_amount(row.get("Debit (BTN)"))
        credit = parse_amount(row.get("Credit (BTN)"))
        cost_center = str(row.get("Cost Center", "")).strip()
        remarks = str(row.get("Remarks", "")).strip()
        posting_date_raw = row.get("Posting Date")

        # Amount received = Debit (money coming in)
        amount = debit or Decimal("0")
        if credit and credit > 0:
            # Credit might be refund/reversal
            amount -= credit

        if amount <= 0:
            continue

        # Parse customer and CID from Party field (Against Account)
        # Format: "Name(CID)" or "Name (CID)" or just "Name"
        customer = party
        cid = None
        cid_match = re.search(r'\((\d+)\)', party)
        if cid_match:
            cid = cid_match.group(1)
            customer = party[:cid_match.start()].strip()

        # Parse region from Cost Center
        region = cost_center

        # Parse month/year from Posting Date
        try:
            if posting_date_raw:
                posting_str = str(posting_date_raw)
                if "T" in posting_str:
                    posting_str = posting_str.split("T")[0]
                dt = datetime.strptime(posting_str[:10], "%Y-%m-%d")
                month = dt.month
                year = dt.year
            else:
                month = as_of.month if as_of else 10
                year = as_of.year if as_of else 2026
        except (ValueError, TypeError):
            month = as_of.month if as_of else 10
            year = as_of.year if as_of else 2026

        # Detect payment mode from remarks
        payment_mode = "external"
        if "salary" in remarks.lower() or "scan and pay" in remarks.lower() or "pos" in remarks.lower():
            payment_mode = "external"
        elif "salary deduction" in remarks.lower() or "internal" in remarks.lower():
            payment_mode = "internal"

        key = (ref, month, year)
        group = grouped[key]
        group["reference"] = ref
        group["customer"] = customer
        group["cid"] = cid
        group["region"] = region
        group["month"] = month
        group["year"] = year
        group["received_amount"] += amount
        group["payment_mode"] = payment_mode

    # Convert to contract format
    contracts = []
    for (ref, month, year), data in grouped.items():
        if data["received_amount"] <= 0:
            continue

        due_month = date(year, month, 1)

        # Allocate to salary/external based on payment_mode
        salary_amount = data["received_amount"] if data["payment_mode"] == "internal" else Decimal("0")
        external_amount = data["received_amount"] if data["payment_mode"] == "external" else Decimal("0")

        contracts.append({
            "reference": ref,
            "customer": data["customer"],
            "cid": data["cid"],
            "installments": [{
                "due_month": due_month,
                "received_amount": data["received_amount"],
                "salary_amount": salary_amount,
                "external_amount": external_amount,
                "due_amount": None,
            }],
        })

    return contracts, warnings


def detect_format(headers: List[str]) -> str:
    """Detect which parser to use based on column headers."""
    headers_lower = [str(h).strip().lower() for h in headers if h]

    # Salary Slip format
    salary_slip_indicators = {"reference number", "salary component", "employee name", "fiscal year"}
    if salary_slip_indicators.issubset(set(headers_lower)):
        return "salary_slip"

    # Bank Ledger format
    bank_ledger_indicators = {"against voucher", "party type", "debit (btn)", "credit (btn)", "cost center"}
    if bank_ledger_indicators.issubset(set(headers_lower)):
        return "bank_ledger"

    return "standard"