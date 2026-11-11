"""Excel file reader and parser for the importer."""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import re

import openpyxl
from openpyxl.utils import get_column_letter

from app.importer.column_map import (
    parse_month_column,
    get_canonical_column,
    map_sheet_columns,
    parse_amount,
    parse_int,
    parse_date,
    clean_cid,
    clean_customer,
    clean_mobile,
    derive_channel,
    reshape_month_columns,
    calculate_installment_due,
)
from app.importer.validation import ValidationReport, validate_excel_import
from app.importer.specialized_parsers import (
    detect_format,
    parse_salary_slip,
    parse_bank_ledger,
)


@dataclass
class ParsedSheet:
    """Result of parsing an Excel sheet."""
    sheet_name: str
    headers: List[str]
    rows: List[Dict[str, Any]]
    month_columns: Dict[str, Tuple[str, int, int]]  # original_name -> (type, month, year)
    static_columns: Dict[str, str]  # original_name -> canonical_name
    totals_row: Optional[int] = None
    sheet_totals: Dict[str, Decimal] = None


def detect_header_row(worksheet, max_rows: int = 10) -> int:
    """Detect the header row by looking for common column names."""
    header_keywords = {"reference", "ref", "cid", "customer", "mobile", "salary", "external", "received"}
    
    for row_idx in range(1, min(max_rows + 1, worksheet.max_row + 1)):
        row_values = []
        for col_idx in range(1, worksheet.max_column + 1):
            cell = worksheet.cell(row=row_idx, column=col_idx)
            val = str(cell.value).strip().lower() if cell.value else ""
            row_values.append(val)
        
        # Count how many header keywords match
        matches = sum(1 for v in row_values if any(kw in v for kw in header_keywords))
        if matches >= 3:  # At least 3 recognizable headers
            return row_idx
    
    return 1  # Default to first row


def read_excel_sheet(
    file_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
) -> ParsedSheet:
    """
    Read and parse an Excel sheet.
    
    Args:
        file_path: Path to the Excel file
        sheet_name: Specific sheet name (None = first sheet)
        header_row: 1-indexed header row (None = auto-detect)
    
    Returns:
        ParsedSheet with parsed data and column mappings
    """
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    
    try:
        if sheet_name:
            ws = wb[sheet_name]
        else:
            ws = wb.active
        
        # Detect header row if not specified
        if header_row is None:
            header_row = detect_header_row(ws)
        
        # Read headers
        header_cells = list(ws.iter_rows(min_row=header_row, max_row=header_row))[0]
        headers = []
        for cell in header_cells:
            val = cell.value if hasattr(cell, "value") else cell
            if val is not None:
                if isinstance(val, (datetime, date)):
                    header = val.strftime("%b-%y")
                else:
                    header = str(val).strip()
            else:
                header = f"col_{len(headers) + 1}"
            headers.append(header)
        
        # Map columns using adjacency pairing
        month_columns, static_columns = map_sheet_columns(headers)
        
        # Read data rows
        rows = []
        sheet_totals = {}
        totals_row = None
        
        for row_tuple in ws.iter_rows(min_row=header_row + 1):
            row_data = {}
            is_empty = True
            
            for col_idx, header in enumerate(headers):
                cell = row_tuple[col_idx] if col_idx < len(row_tuple) else None
                if cell is None:
                    row_data[header] = None
                    continue
                
                val = cell.value if hasattr(cell, "value") else cell
                fmt = getattr(cell, "number_format", None)
                
                if val is not None and str(val).strip():
                    is_empty = False
                
                # Check for zero-padded numeric formatting (e.g. "0000" on 249 -> "0249")
                if fmt and isinstance(val, (int, float)) and not isinstance(val, bool) and re.match(r"^0+$", str(fmt).strip("\"'")):
                    width = len(str(fmt).strip("\"'"))
                    if width > 1:
                        if isinstance(val, int):
                            val = f"{val:0{width}d}"
                        elif isinstance(val, float) and val.is_integer():
                            val = f"{int(val):0{width}d}"
                
                row_data[header] = val
            
            if is_empty:
                continue
            
            # Check if this might be a totals row
            first_col = str(row_data.get(headers[0], "")).strip().lower() if headers else ""
            if any(kw in first_col for kw in ["total", "sum", "grand total", "subtotal"]):
                totals_row = True
                for header in headers:
                    val = row_data.get(header)
                    if val is not None:
                        parsed = parse_amount(val)
                        if parsed is not None:
                            sheet_totals[header] = parsed
            
            rows.append(row_data)
        
        return ParsedSheet(
            sheet_name=ws.title,
            headers=headers,
            rows=rows,
            month_columns=month_columns,
            static_columns=static_columns,
            totals_row=totals_row,
            sheet_totals=sheet_totals,
        )
    
    finally:
        wb.close()


def parse_sheet_to_contracts(parsed: ParsedSheet) -> List[Dict[str, Any]]:
    """
    Convert parsed sheet rows to contract records with monthly installments.
    
    Returns list of contract dicts, each containing:
    - static fields (reference, customer, etc.)
    - installments: list of monthly installment dicts
    """
    contracts = []
    
    for row in parsed.rows:
        # Skip total/summary rows
        ref = str(row.get("Reference", "")).strip().lower()
        if ref in ("total", "sum", "grand total", "subtotal"):
            continue
        
        # Build static contract data
        contract = {}
        
        # Map static columns
        for orig_col, canonical in parsed.static_columns.items():
            value = row.get(orig_col)
            
            if canonical == "cid":
                contract[canonical] = clean_cid(value)
            elif canonical == "customer":
                contract[canonical] = clean_customer(value)
            elif canonical == "mobile":
                mobile, _ = clean_mobile(value)
                contract[canonical] = mobile
            elif canonical in ("contract_date", "start_date", "end_date"):
                contract[canonical] = parse_date(value)
            elif canonical in ("emi_months", "count", "months"):
                parsed_val = parse_int(value)
                if parsed_val is not None:
                    contract[canonical] = parsed_val
            elif canonical in ("monthly_deduction", "sales_amount", "gst", "emi_received", "overall_outstanding"):
                parsed_val = parse_amount(value)
                if parsed_val is not None:
                    contract[canonical] = parsed_val
            else:
                contract[canonical] = str(value).strip() if value is not None else None

        # Map header "Posting Date" -> start_date (also fill contract_date with the same value)
        if contract.get("start_date"):
            contract["contract_date"] = contract["start_date"]
        elif contract.get("contract_date"):
            contract["start_date"] = contract["contract_date"]

        # Missing Ending Date is a WARNING (derive it as posting month + EMI months - 1)
        if not contract.get("end_date") and contract.get("start_date") and contract.get("emi_months"):
            try:
                import calendar
                s_date = datetime.strptime(str(contract["start_date"])[:10], "%Y-%m-%d").date()
                emi_m = int(contract["emi_months"])
                total_m = (s_date.year * 12 + s_date.month - 1) + (emi_m - 1)
                end_y = total_m // 12
                end_m = (total_m % 12) + 1
                max_d = calendar.monthrange(end_y, end_m)[1]
                end_d = min(s_date.day, max_d)
                contract["end_date"] = date(end_y, end_m, end_d).isoformat()
            except Exception:
                pass

        # A missing or invalid Posting Date is an ERROR for that row (the schedule cannot be built)
        has_posting_col = any(c in ("start_date", "contract_date") for c in parsed.static_columns.values())
        if has_posting_col and not contract.get("start_date"):
            contract["schedule_error"] = "Missing or invalid Posting Date (the schedule cannot be built)"
            installments = []
        else:
            # Reshape monthly columns
            raw_installments = reshape_month_columns(row, parsed.month_columns)
            monthly_ded = contract.get("monthly_deduction")
            gst_amt = contract.get("gst")

            # Determine contract schedule: start_month through end_month
            def _to_month_start(val: Any) -> Optional[date]:
                if not val:
                    return None
                if isinstance(val, datetime):
                    return date(val.year, val.month, 1)
                if isinstance(val, date):
                    return date(val.year, val.month, 1)
                if isinstance(val, str) and val.strip():
                    try:
                        d = datetime.strptime(val[:10], "%Y-%m-%d").date()
                        return date(d.year, d.month, 1)
                    except ValueError:
                        return None
                return None

            start_month = _to_month_start(contract.get("start_date"))
            end_month = _to_month_start(contract.get("end_date"))

            # Check schedule length vs emi_months
            if start_month and end_month and contract.get("emi_months") is not None:
                try:
                    sched_len = (end_month.year - start_month.year) * 12 + (end_month.month - start_month.month) + 1
                    emi_m = int(contract["emi_months"])
                    if sched_len != emi_m:
                        ref_str = contract.get("reference", "")
                        contract["schedule_warning"] = (
                            f"Contract {ref_str}: schedule length ({sched_len}) differs from EMI months ({emi_m})"
                        )
                except (ValueError, TypeError):
                    pass

            if start_month is not None:
                installments = []
                for inst in raw_installments:
                    due_m = inst.get("due_month")
                    if not due_m:
                        continue

                    is_inside = (due_m >= start_month) and (end_month is None or due_m <= end_month)
                    if is_inside:
                        # Inside schedule: create the row; due_amount = monthly_deduction (+ GST in first month)
                        if due_m == start_month:
                            inst["due_amount"] = calculate_installment_due(monthly_ded, gst_amt, month_index=0)
                        else:
                            inst["due_amount"] = calculate_installment_due(monthly_ded, gst_amt, month_index=1)
                        installments.append(inst)
                    else:
                        # Outside schedule: create a row ONLY if the cell has a payment or a note;
                        # then due_amount = NULL and the amount/cell_status are kept.
                        has_payment = False
                        for amt_field in ("salary_amount", "external_amount", "received_amount", "deducted_amount"):
                            amt_val = inst.get(amt_field)
                            if amt_val is not None:
                                try:
                                    if Decimal(str(amt_val)) > Decimal("0"):
                                        has_payment = True
                                        break
                                except Exception:
                                    pass

                        has_note = (
                            inst.get("not_status") == "note"
                            or inst.get("cell_status") == "note"
                            or bool(inst.get("note"))
                        )

                        if has_payment or has_note:
                            inst["due_amount"] = None
                            installments.append(inst)
            else:
                # Fallback for sheets without posting date headers (preserves legacy tests)
                installments = raw_installments
                for idx, inst in enumerate(installments):
                    inst["due_amount"] = calculate_installment_due(monthly_ded, gst_amt, idx)

        if not contract.get("reference"):
            continue  # Skip rows without reference

        # Derive channel
        channel, _ = derive_channel(contract.get("payment_type"), row, parsed.month_columns)
        contract["channel"] = channel

        contract["installments"] = installments
        contracts.append(contract)

    return contracts


def calculate_file_checksum(file_path: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class UploadType(str, Enum):
    """Upload type enumeration."""
    FULL = "full"           # Original: contracts + installments
    CUSTOMER = "customer"   # Customer/contract static data only
    PAYMENT = "payment"     # Payment/installment data only


def import_excel_file(
    file_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    as_of: Optional[date] = None,
    upload_type: UploadType = UploadType.FULL,
) -> Tuple[List[Dict[str, Any]], ValidationReport, Dict[str, Any]]:
    """
    Complete import pipeline: read, parse, validate.

    Args:
        file_path: Path to Excel file
        sheet_name: Specific sheet name
        header_row: Header row number
        as_of: As-of date for calculations
        upload_type: Type of upload (FULL, CUSTOMER, PAYMENT)

    Returns:
        (contracts, validation_report, preview_summary)
    """
    # Read and parse
    parsed = read_excel_sheet(file_path, sheet_name, header_row)

    if upload_type == UploadType.CUSTOMER:
        return _import_customer_upload(parsed, header_row, as_of)
    elif upload_type == UploadType.PAYMENT:
        return _import_payment_upload(parsed, header_row, as_of)
    else:
        return _import_full_upload(parsed, header_row, as_of)


def _import_full_upload(
    parsed: ParsedSheet,
    header_row: Optional[int],
    as_of: Optional[date],
) -> Tuple[List[Dict[str, Any]], ValidationReport, Dict[str, Any]]:
    """Original full import: contracts + installments."""
    # Validate using original parsed rows (with original column names)
    report = validate_excel_import(
        parsed.rows,
        parsed.month_columns,
        parsed.static_columns,
        parsed.sheet_totals,
    )

    # Check Posting Date and Ending Date errors/warnings per row
    posting_orig = None
    ending_orig = None
    for orig_col, canon in parsed.static_columns.items():
        if canon in ("start_date", "contract_date"):
            posting_orig = orig_col
        elif canon == "end_date":
            ending_orig = orig_col

    if posting_orig or ending_orig:
        for row_idx, row in enumerate(parsed.rows, start=header_row + 1 if header_row else 2):
            ref_val = str(row.get("Reference", "")).strip().lower()
            if ref_val in ("total", "sum", "grand total", "subtotal"):
                continue

            # Posting Date: missing or invalid is an ERROR
            if posting_orig:
                val = row.get(posting_orig)
                if val is None or not str(val).strip():
                    report.add_error("missing_posting_date", f"Missing Posting Date", row=row_idx, column=posting_orig)
                elif not parse_date(val):
                    if not any(i.code == "invalid_date" and i.row == row_idx for i in report.issues):
                        report.add_error("invalid_date", f"Invalid date format: '{val}'", row=row_idx, column=posting_orig, value=val)

            # Ending Date: missing or invalid is a WARNING
            if ending_orig:
                val = row.get(ending_orig)
                if val is None or not str(val).strip():
                    report.add_warning("missing_ending_date", f"Missing Ending Date; derived from posting month and EMI months", row=row_idx, column=ending_orig)
                elif not parse_date(val):
                    report.add_warning("invalid_ending_date", f"Invalid Ending Date format: '{val}'; derived from posting month and EMI months", row=row_idx, column=ending_orig, value=val)
            elif posting_orig:
                report.add_warning("missing_ending_date", f"Missing Ending Date; derived from posting month and EMI months", row=row_idx)

    # Convert to contract format
    contracts = parse_sheet_to_contracts(parsed)

    # Check schedule length mismatch warnings
    for row_idx, contract in enumerate(contracts, start=header_row + 1 if header_row else 2):
        if contract.get("schedule_warning"):
            report.add_warning(
                "schedule_length_mismatch",
                f"{contract['schedule_warning']} at row {row_idx}",
                row=row_idx,
            )

    # Generate preview using contracts (which have installments)
    from app.importer.validation import generate_preview_summary
    preview = generate_preview_summary(contracts, parsed.month_columns, as_of=as_of)
    return contracts, report, preview


def _import_customer_upload(
    parsed: ParsedSheet,
    header_row: Optional[int],
    as_of: Optional[date],
) -> Tuple[List[Dict[str, Any]], ValidationReport, Dict[str, Any]]:
    """Customer upload: static contract/customer data only (no installments)."""
    # Validate static columns only
    report = validate_excel_import(
        parsed.rows,
        {},  # No month columns for customer upload
        parsed.static_columns,
        parsed.sheet_totals,
    )

    # Check required fields for customer upload
    for row_idx, row in enumerate(parsed.rows, start=header_row + 1 if header_row else 2):
        ref_val = str(row.get("Reference", "")).strip().lower()
        if ref_val in ("total", "sum", "grand total", "subtotal"):
            continue

        # Customer upload requires reference and at least one identifier
        has_cid = any(canon == "cid" for canon in parsed.static_columns.values())
        has_mobile = any(canon == "mobile" for canon in parsed.static_columns.values())
        has_customer = any(canon == "customer" for canon in parsed.static_columns.values())

        if not has_cid and not has_mobile and not has_customer:
            report.add_warning(
                "missing_customer_identifier",
                f"Row {row_idx}: No CID, mobile, or customer name provided",
                row=row_idx,
            )

    # Parse static contract data only (no installments)
    contracts = parse_sheet_to_contracts_customer_only(parsed)

    # Generate preview for customer upload
    preview = generate_customer_preview_summary(contracts, as_of=as_of)
    return contracts, report, preview


def _import_payment_upload(
    parsed: ParsedSheet,
    header_row: Optional[int],
    as_of: Optional[date],
) -> Tuple[List[Dict[str, Any]], ValidationReport, Dict[str, Any]]:
    """Payment upload: installment/payment data only (supports multiple formats)."""
    # Detect format
    format_type = detect_format(parsed.headers)
    
    if format_type == "salary_slip":
        # Parse ERPNext Salary Slip format
        contracts, warnings = parse_salary_slip(parsed.rows, as_of=as_of)
        report = ValidationReport()
        for w in warnings:
            report.add_warning("salary_slip_parser", w)
        
    elif format_type == "bank_ledger":
        # Parse Payment.xlsx bank ledger format
        contracts, warnings = parse_bank_ledger(parsed.rows, as_of=as_of)
        report = ValidationReport()
        for w in warnings:
            report.add_warning("bank_ledger_parser", w)
        
    else:
        # Standard payment format (reference + month columns)
        report = validate_excel_import(
            parsed.rows,
            parsed.month_columns,
            parsed.static_columns,
            parsed.sheet_totals,
        )

        # Check for required reference column
        has_reference = any(canon == "reference" for canon in parsed.static_columns.values())
        if not has_reference:
            report.add_error(
                "missing_reference_column",
                "Payment upload requires a Reference column to match payments to contracts",
            )

        # Check for month columns
        if not parsed.month_columns:
            report.add_error(
                "missing_month_columns",
                "Payment upload requires at least one month column (e.g., 'Received Sep 24', 'Salary Oct 24')",
            )

        contracts = parse_sheet_to_payments(parsed)

    # Generate preview for payment upload
    preview = generate_payment_preview_summary(contracts, parsed.month_columns, as_of=as_of)
    return contracts, report, preview


def parse_sheet_to_contracts_customer_only(parsed: ParsedSheet) -> List[Dict[str, Any]]:
    """
    Convert parsed sheet rows to contract records WITHOUT installments.
    Only extracts static customer/contract fields.
    """
    contracts = []

    for row in parsed.rows:
        # Skip total/summary rows
        ref = str(row.get("Reference", "")).strip().lower()
        if ref in ("total", "sum", "grand total", "subtotal"):
            continue

        # Build static contract data
        contract = {}

        # Map static columns
        for orig_col, canonical in parsed.static_columns.items():
            value = row.get(orig_col)

            if canonical == "cid":
                contract[canonical] = clean_cid(value)
            elif canonical == "customer":
                contract[canonical] = clean_customer(value)
            elif canonical == "mobile":
                mobile, _ = clean_mobile(value)
                contract[canonical] = mobile
            elif canonical in ("contract_date", "start_date", "end_date"):
                contract[canonical] = parse_date(value)
            elif canonical in ("emi_months", "count", "months"):
                parsed_val = parse_int(value)
                if parsed_val is not None:
                    contract[canonical] = parsed_val
            elif canonical in ("monthly_deduction", "sales_amount", "gst", "emi_received", "overall_outstanding"):
                parsed_val = parse_amount(value)
                if parsed_val is not None:
                    contract[canonical] = parsed_val
            else:
                contract[canonical] = str(value).strip() if value is not None else None

        # Map header "Posting Date" -> start_date (also fill contract_date with the same value)
        if contract.get("start_date"):
            contract["contract_date"] = contract["start_date"]
        elif contract.get("contract_date"):
            contract["start_date"] = contract["contract_date"]

        # Missing Ending Date is a WARNING (derive it as posting month + EMI months - 1)
        if not contract.get("end_date") and contract.get("start_date") and contract.get("emi_months"):
            try:
                import calendar
                s_date = datetime.strptime(str(contract["start_date"])[:10], "%Y-%m-%d").date()
                emi_m = int(contract["emi_months"])
                total_m = (s_date.year * 12 + s_date.month - 1) + (emi_m - 1)
                end_y = total_m // 12
                end_m = (total_m % 12) + 1
                max_d = calendar.monthrange(end_y, end_m)[1]
                end_d = min(s_date.day, max_d)
                contract["end_date"] = date(end_y, end_m, end_d).isoformat()
            except Exception:
                pass

        # A missing or invalid Posting Date is an ERROR for that row
        has_posting_col = any(c in ("start_date", "contract_date") for c in parsed.static_columns.values())
        if has_posting_col and not contract.get("start_date"):
            contract["schedule_error"] = "Missing or invalid Posting Date (the schedule cannot be built)"

        if not contract.get("reference"):
            continue  # Skip rows without reference

        # Derive channel from payment type
        channel, _ = derive_channel(contract.get("payment_type"), row, parsed.month_columns)
        contract["channel"] = channel

        # Empty installments for customer-only upload
        contract["installments"] = []
        contracts.append(contract)

    return contracts


def parse_sheet_to_payments(parsed: ParsedSheet) -> List[Dict[str, Any]]:
    """
    Convert parsed sheet rows to payment records.
    Only extracts reference + monthly payment data (received, salary, external amounts).
    """
    contracts = []

    for row in parsed.rows:
        # Skip total/summary rows
        ref = str(row.get("Reference", "")).strip().lower()
        if ref in ("total", "sum", "grand total", "subtotal"):
            continue

        contract = {"reference": row.get("Reference")}

        # Get reference column
        ref_canon = None
        for orig_col, canonical in parsed.static_columns.items():
            if canonical == "reference":
                ref_canon = orig_col
                break

        if not contract.get("reference"):
            continue

        # Reshape monthly columns to get payment data
        raw_installments = reshape_month_columns(row, parsed.month_columns)

        # Filter to only keep months with payment data
        installments = []
        for inst in raw_installments:
            due_m = inst.get("due_month")
            if not due_m:
                continue

            # Check if this month has any payment data
            has_payment = False
            for amt_field in ("salary_amount", "external_amount", "received_amount", "deducted_amount"):
                amt_val = inst.get(amt_field)
                if amt_val is not None:
                    try:
                        if Decimal(str(amt_val)) > Decimal("0"):
                            has_payment = True
                            break
                    except Exception:
                        pass

            has_note = (
                inst.get("not_status") == "note"
                or inst.get("cell_status") == "note"
                or bool(inst.get("note"))
            )

            if has_payment or has_note:
                # Keep only payment-related fields
                installments.append({
                    "due_month": due_m,
                    "salary_amount": inst.get("salary_amount"),
                    "external_amount": inst.get("external_amount"),
                    "received_amount": inst.get("received_amount"),
                    "deducted_amount": inst.get("deducted_amount"),
                    "not_status": inst.get("not_status"),
                    "status": inst.get("status"),
                })

        if installments:
            contract["installments"] = installments
            contracts.append(contract)

    return contracts


def generate_customer_preview_summary(contracts: List[Dict[str, Any]], as_of: Optional[date] = None) -> Dict[str, Any]:
    """Generate preview summary for customer upload."""
    new_customers = 0
    updated_customers = 0
    customers_with_errors = 0

    for c in contracts:
        if c.get("schedule_error"):
            customers_with_errors += 1
        # In a real implementation, we'd check if reference exists in DB
        # For preview, we'll estimate based on whether it looks like a new record
        # (e.g., has all required fields)
        if c.get("cid") or c.get("customer") or c.get("mobile"):
            new_customers += 1
        else:
            updated_customers += 1

    return {
        "contracts_count": len(contracts),
        "new_customers": new_customers,
        "updated_customers": updated_customers,
        "customers_with_errors": customers_with_errors,
        "validation_report": {},  # Will be filled from report
    }


def generate_payment_preview_summary(
    contracts: List[Dict[str, Any]],
    month_columns: Dict[str, Tuple[str, int, int]],
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """Generate preview summary for payment upload."""
    from app.importer.validation import generate_preview_summary

    # Reuse the existing preview generation but with payment data
    # Convert payment format to contract-like format for preview
    contract_like = []
    for c in contracts:
        contract_like.append({
            "reference": c["reference"],
            "installments": c["installments"],
        })

    preview = generate_preview_summary(contract_like, month_columns, as_of=as_of)

    # Add payment-specific stats
    payments_updated = 0
    payments_new = 0
    for c in contracts:
        payments_new += len(c["installments"])

    preview["payments_updated"] = payments_updated
    preview["payments_new"] = payments_new

    return preview