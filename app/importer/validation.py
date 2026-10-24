"""Validation logic for Excel imports."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import date
from decimal import Decimal
import re

from app.importer.column_map import parse_amount, parse_date, clean_cid, clean_mobile


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: str  # "error", "warning", "info"
    code: str      # Machine-readable code
    message: str   # Human-readable message
    row: Optional[int] = None
    column: Optional[str] = None
    value: Any = None


@dataclass
class ValidationReport:
    """Complete validation report for an import."""
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    
    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
    
    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")
    
    def add_error(self, code: str, message: str, row: int = None, column: str = None, value: Any = None):
        self.issues.append(ValidationIssue("error", code, message, row, column, value))
    
    def add_warning(self, code: str, message: str, row: int = None, column: str = None, value: Any = None):
        self.issues.append(ValidationIssue("warning", code, message, row, column, value))
    
    def add_info(self, code: str, message: str, row: int = None, column: str = None, value: Any = None):
        self.issues.append(ValidationIssue("info", code, message, row, column, value))
    
    def get_errors_by_code(self, code: str) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error" and i.code == code]
    
    def get_warnings_by_code(self, code: str) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning" and i.code == code]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "row": i.row,
                    "column": i.column,
                    "value": str(i.value) if i.value is not None else None,
                }
                for i in self.issues
            ],
            "stats": self.stats,
        }


def validate_excel_import(
    rows: List[Dict[str, Any]],
    month_column_map: Dict[str, tuple],
    static_columns: Optional[Dict[str, str]] = None,
    sheet_totals: Optional[Dict[str, float]] = None,
) -> ValidationReport:
    """
    Validate imported Excel data.
    
    Args:
        rows: List of dicts representing each row (with original column names as keys)
        month_column_map: Mapping of original column names to (type, month, year)
        static_columns: Mapping of original column names to canonical names
        sheet_totals: Optional dict with expected totals from sheet (e.g., {'total_receivable': 100000})
    
    Returns:
        ValidationReport with all issues
    """
    report = ValidationReport()
    
    if not rows:
        report.add_error("empty_file", "No data rows found in the sheet")
        return report
    
    # Build reverse mapping from canonical to original column names
    canonical_to_original = {}
    if static_columns:
        for orig, canon in static_columns.items():
            canonical_to_original[canon] = orig
    
    def get_orig_col(canonical: str) -> str:
        """Get original column name for a canonical name."""
        return canonical_to_original.get(canonical, canonical)
    
    # Track seen references and CIDs
    seen_references: Dict[str, List[int]] = {}
    seen_cids: Dict[str, List[int]] = {}
    
    # Track totals for cross-checking
    total_receivable = Decimal("0")
    total_collected = Decimal("0")
    total_overdue = Decimal("0")
    
    for idx, row in enumerate(rows):
        row_num = idx + 2  # 1-indexed + header row
        
        # Validate Reference
        ref_col = get_orig_col("reference")
        ref_raw = row.get(ref_col)
        if ref_raw is None or str(ref_raw).strip() == "":
            report.add_error("missing_reference", "Reference is required", row=row_num, column=ref_col)
            ref = ""
        else:
            ref = str(ref_raw).strip()
            if ref in seen_references:
                seen_references[ref].append(row_num)
                report.add_error(
                    "duplicate_reference",
                    f"Duplicate reference '{ref}' (also in row {seen_references[ref][0]})",
                    row=row_num,
                    column=ref_col,
                    value=ref
                )
            else:
                seen_references[ref] = [row_num]
        
        # Validate CID
        cid_col = get_orig_col("cid")
        cid_raw = row.get(cid_col)
        cid = clean_cid(cid_raw)
        if cid:
            if cid in seen_cids:
                seen_cids[cid].append(row_num)
            else:
                seen_cids[cid] = [row_num]
        
        # Validate mobile
        mobile_col = get_orig_col("mobile")
        mobile_raw = row.get(mobile_col)
        mobile, is_valid = clean_mobile(mobile_raw)
        if mobile_raw is not None and str(mobile_raw).strip() == "":
            report.add_warning("blank_mobile", "Mobile number is blank", row=row_num, column=mobile_col)
        elif mobile and not is_valid:
            report.add_warning("invalid_mobile", f"Invalid mobile format: '{mobile_raw}'", row=row_num, column=mobile_col, value=mobile_raw)
        
        # Validate dates
        contract_date_col = get_orig_col("contract_date")
        date_val = row.get(contract_date_col)
        if date_val is not None and str(date_val).strip():
            parsed = parse_date(date_val)
            if not parsed:
                report.add_error("invalid_date", f"Invalid date format: '{date_val}'", row=row_num, column=contract_date_col, value=date_val)
        
        # Validate amounts
        for amt_col in ["monthly_deduction", "sales_amount", "gst"]:
            orig_col = get_orig_col(amt_col)
            amt_val = row.get(orig_col)
            parsed = parse_amount(amt_val)
            if parsed is not None:
                if parsed < 0:
                    report.add_error("negative_amount", f"Negative amount not allowed: {parsed}", row=row_num, column=orig_col, value=amt_val)
            elif amt_val is not None and str(amt_val).strip():
                report.add_error("invalid_amount", f"Could not parse amount: '{amt_val}'", row=row_num, column=orig_col, value=amt_val)
        
        # Validate monthly columns
        for orig_col, (col_type, month, year) in month_column_map.items():
            value = row.get(orig_col)
            if value is not None and str(value).strip():
                parsed = parse_amount(value)
                if parsed is None:
                    # Check if it's a status value
                    status = str(value).strip().lower()
                    if status not in ("not received", "not deducted", "pending", "paid", "partial", "overdue", "waived", "n/a", "na", "-", "", "nil"):
                        report.add_warning(
                            "unparseable_month_value",
                            f"Could not parse {col_type} value for {month}/{year}: '{value}'",
                            row=row_num,
                            column=orig_col,
                            value=value
                        )
                elif parsed < 0:
                    report.add_error(
                        "negative_month_amount",
                        f"Negative {col_type} amount for {month}/{year}: {parsed}",
                        row=row_num,
                        column=orig_col,
                        value=value
                    )
        
        # Calculate totals from monthly data
        from collections import defaultdict
        month_data = defaultdict(lambda: {"external": Decimal("0"), "salary": Decimal("0"), "received": Decimal("0")})
        
        for orig_col, (col_type, month, year) in month_column_map.items():
            value = row.get(orig_col)
            if value is not None:
                parsed = parse_amount(value)
                if parsed is not None:
                    key = (year, month)
                    if col_type == "external":
                        month_data[key]["external"] = Decimal(str(parsed))
                    elif col_type == "salary":
                        month_data[key]["salary"] = Decimal(str(parsed))
                    elif col_type == "received":
                        month_data[key]["received"] = Decimal(str(parsed))
        
        for (year, month), data in month_data.items():
            due = max(data["external"], data["salary"])
            received = data["received"]
            total_receivable += due
            total_collected += received
            if due > received:
                total_overdue += (due - received)
    
    # Check for duplicate references
    for ref, row_nums in seen_references.items():
        if len(row_nums) > 1:
            # Already reported above
            pass
    
    # Cross-check totals if provided
    if sheet_totals:
        if "total_receivable" in sheet_totals:
            expected = Decimal(str(sheet_totals["total_receivable"]))
            diff = abs(total_receivable - expected)
            if diff > Decimal("0.01"):  # Allow small rounding differences
                report.add_warning(
                    "total_mismatch",
                    f"Total receivable mismatch: calculated {total_receivable}, sheet says {expected} (diff: {diff})"
                )
        
        if "total_collected" in sheet_totals:
            expected = Decimal(str(sheet_totals["total_collected"]))
            diff = abs(total_collected - expected)
            if diff > Decimal("0.01"):
                report.add_warning(
                    "total_mismatch",
                    f"Total collected mismatch: calculated {total_collected}, sheet says {expected} (diff: {diff})"
                )
    
    # Summary stats
    report.stats = {
        "total_rows": len(rows),
        "unique_references": len(seen_references),
        "duplicate_references": sum(1 for v in seen_references.values() if len(v) > 1),
        "unique_cids": len(seen_cids),
        "total_receivable": float(total_receivable),
        "total_collected": float(total_collected),
        "total_overdue": float(total_overdue),
        "rows_with_errors": len(set(i.row for i in report.issues if i.severity == "error" and i.row)),
        "rows_with_warnings": len(set(i.row for i in report.issues if i.severity == "warning" and i.row)),
    }
    
    return report


def generate_preview_summary(rows: List[Dict[str, Any]], month_column_map: Dict[str, tuple]) -> Dict[str, Any]:
    """Generate a preview summary for the upload confirmation step."""
    from collections import defaultdict
    from datetime import date
    from decimal import Decimal
    
    stats = {
        "total_contracts": len(rows),
        "new_contracts": 0,  # Would need DB check
        "updated_contracts": 0,
        "monthly_breakdown": defaultdict(lambda: {"contracts": 0, "due": Decimal("0"), "received": Decimal("0")}),
        "status_changes": defaultdict(int),
    }
    
    # If rows have installments (already parsed), use those
    if rows and "installments" in rows[0]:
        for contract in rows:
            for inst in contract.get("installments", []):
                due_month = inst.get("due_month")
                if not due_month:
                    continue
                key = due_month.strftime("%Y-%m")
                due = inst.get("external_amount") or inst.get("salary_amount") or Decimal("0")
                received = inst.get("received_amount") or Decimal("0")
                if not isinstance(due, Decimal):
                    due = Decimal(str(due))
                if not isinstance(received, Decimal):
                    received = Decimal(str(received))
                
                stats["monthly_breakdown"][key]["due"] += due
                stats["monthly_breakdown"][key]["received"] += received
                stats["monthly_breakdown"][key]["contracts"] += 1
    else:
        # Fallback: use original rows and month_column_map
        for row in rows:
            for orig_col, (col_type, month, year) in month_column_map.items():
                value = row.get(orig_col)
                if value is not None:
                    parsed = parse_amount(value)
                    if parsed is not None:
                        key = f"{year}-{month:02d}"
                        if col_type in ("external", "salary"):
                            stats["monthly_breakdown"][key]["due"] += Decimal(str(parsed))
                        elif col_type == "received":
                            stats["monthly_breakdown"][key]["received"] += Decimal(str(parsed))
    
    # Convert Decimal to float for JSON
    for key in stats["monthly_breakdown"]:
        stats["monthly_breakdown"][key]["due"] = float(stats["monthly_breakdown"][key]["due"])
        stats["monthly_breakdown"][key]["received"] = float(stats["monthly_breakdown"][key]["received"])
    
    return stats