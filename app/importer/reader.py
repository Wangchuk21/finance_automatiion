"""Excel file reader and parser for the importer."""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
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
            installments = reshape_month_columns(row, parsed.month_columns)
            monthly_ded = contract.get("monthly_deduction")
            gst_amt = contract.get("gst")
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


def import_excel_file(
    file_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], ValidationReport, Dict[str, Any]]:
    """
    Complete import pipeline: read, parse, validate.

    Returns:
        (contracts, validation_report, preview_summary)
    """
    # Read and parse
    parsed = read_excel_sheet(file_path, sheet_name, header_row)

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

    # Generate preview using contracts (which have installments)
    from app.importer.validation import generate_preview_summary
    preview = generate_preview_summary(contracts, parsed.month_columns)
    return contracts, report, preview