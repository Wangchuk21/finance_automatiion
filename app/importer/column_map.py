"""Column name normalization and mapping for Excel imports."""

import re
from typing import Dict, List, Optional, Pattern, Tuple

# Canonical column names expected in the data
CANONICAL_COLUMNS = {
    # Static contract columns
    "reference": ["reference", "ref", "contract reference", "contract_ref"],
    "item": ["item", "product", "description"],
    "brand": ["brand", "make"],
    "region": ["region", "area", "zone"],
    "cost_center": ["cost center", "cost_centre", "cost centre", "cc", "cost center code"],
    "ministry_agency": ["ministry/agency", "ministry agency", "ministry", "agency", "department"],
    "payment_type": ["payment type", "payment_type", "payment mode", "mode"],
    "emi_months": ["emi months", "emi_months", "emi", "tenure", "term"],
    "customer": ["customer", "customer name", "client", "client name"],
    "cid": ["cid", "customer id", "customer_id", "c.i.d"],
    "mobile": ["mobile", "phone", "contact", "mobile no", "mobile number"],
    "contract_date": ["contract date", "contract_date", "start date", "start_date"],
    "sales_amount": ["sales amount", "sales_amount", "amount", "sale amount"],
    "gst": ["gst", "tax", "gst amount"],
    # Monthly column patterns (base names)
    "monthly_deduction": ["monthly deduction", "monthly_deduction", "emi amount", "emi_amount"],
}

# Patterns to identify month columns
MONTH_PATTERNS = [
    # "Salary Sep 27", "Salary Feb2", "Salary Sep 2024", etc.
    (r"^salary\s+([a-z]{3,9})\s*(\d{2,4})?$", "salary"),
    # "External Sep 27", "External Feb2", etc.
    (r"^external\s+([a-z]{3,9})\s*(\d{2,4})?$", "external"),
    # "Received Sep 27", "Received Feb2", etc.
    (r"^received\s+([a-z]{3,9})\s*(\d{2,4})?$", "received"),
    # "Deducted Sep 27", "Deducted Feb2", etc.
    (r"^deducted\s+([a-z]{3,9})\s*(\d{2,4})?$", "deducted"),
    # "Not Received Sep 27", "Not Deducted Feb2" - use non-capturing group for status type
    (r"^not\s+(?:received|deducted)\s+([a-z]{3,9})\s*(\d{2,4})?$", "not_status"),
    # Generic "Sep 27", "Feb2" - assume external
    (r"^([a-z]{3,9})\s*(\d{2,4})?$", "external"),
]

# More flexible patterns for month+year without space (e.g., "Feb2", "Sep24")
FLEXIBLE_MONTH_PATTERNS = [
    (r"^salary\s+([a-z]{3,9})(\d{1,4})?$", "salary"),
    (r"^external\s+([a-z]{3,9})(\d{1,4})?$", "external"),
    (r"^received\s+([a-z]{3,9})(\d{1,4})?$", "received"),
    (r"^deducted\s+([a-z]{3,9})(\d{1,4})?$", "deducted"),
    (r"^not\s+(?:received|deducted)\s+([a-z]{3,9})(\d{1,4})?$", "not_status"),
    (r"^([a-z]{3,9})(\d{1,4})?$", "external"),
]

MONTH_NAME_TO_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Typo corrections for known column name variations
COLUMN_TYPO_MAP = {
    # Salary variations
    "salary sept": "salary sep",
    "salary septmber": "salary sep",
    "salary september": "salary sep",
    "salary feb": "salary feb",
    "salary february": "salary feb",
    "salary mar": "salary mar",
    "salary march": "salary mar",
    "salary apr": "salary apr",
    "salary april": "salary apr",
    "salary jun": "salary jun",
    "salary june": "salary jun",
    "salary jul": "salary jul",
    "salary july": "salary jul",
    "salary aug": "salary aug",
    "salary august": "salary aug",
    "salary oct": "salary oct",
    "salary october": "salary oct",
    "salary nov": "salary nov",
    "salary november": "salary nov",
    "salary dec": "salary dec",
    "salary december": "salary dec",
    "salary jan": "salary jan",
    "salary january": "salary jan",
    
    # External variations
    "external sept": "external sep",
    "external september": "external sep",
    "external feb": "external feb",
    "external february": "external feb",
    "external mar": "external mar",
    "external march": "external mar",
    "external apr": "external apr",
    "external april": "external apr",
    "external jun": "external jun",
    "external june": "external jun",
    "external jul": "external jul",
    "external july": "external jul",
    "external aug": "external aug",
    "external august": "external aug",
    "external oct": "external oct",
    "external october": "external oct",
    "external nov": "external nov",
    "external november": "external nov",
    "external dec": "external dec",
    "external december": "external dec",
    "external jan": "external jan",
    "external january": "external jan",
    
    # Received variations
    "received sept": "received sep",
    "received september": "received sep",
    "received feb": "received feb",
    "received february": "received feb",
    "received mar": "received mar",
    "received march": "received mar",
    "received apr": "received apr",
    "received april": "received apr",
    "received jun": "received jun",
    "received june": "received jun",
    "received jul": "received jul",
    "received july": "received jul",
    "received aug": "received aug",
    "received august": "received aug",
    "received oct": "received oct",
    "received october": "received oct",
    "received nov": "received nov",
    "received november": "received nov",
    "received dec": "received dec",
    "received december": "received dec",
    "received jan": "received jan",
    "received january": "received jan",
    
    # Deducted variations
    "deducted sept": "deducted sep",
    "deducted september": "deducted sep",
    "deducted feb": "deducted feb",
    "deducted february": "deducted feb",
    "deducted mar": "deducted mar",
    "deducted march": "deducted mar",
    "deducted apr": "deducted apr",
    "deducted april": "deducted apr",
    "deducted jun": "deducted jun",
    "deducted june": "deducted jun",
    "deducted jul": "deducted jul",
    "deducted july": "deducted jul",
    "deducted aug": "deducted aug",
    "deducted august": "deducted aug",
    "deducted oct": "deducted oct",
    "deducted october": "deducted oct",
    "deducted nov": "deducted nov",
    "deducted november": "deducted nov",
    "deducted dec": "deducted dec",
    "deducted december": "deducted dec",
    "deducted jan": "deducted jan",
    "deducted january": "deducted jan",
    
    # Not received/deducted variations
    "not received sept": "not received sep",
    "not received september": "not received sep",
    "not deducted sept": "not deducted sep",
    "not deducted september": "not deducted sep",
    
    # Payment type variations
    "payment type": "payment_type",
    "payment mode": "payment_type",
    "mode of payment": "payment_type",
    
    # Cost center variations
    "cost centre": "cost_center",
    "cost centre code": "cost_center",
    "cc code": "cost_center",
    
    # CID variations
    "customer id": "cid",
    "c.i.d": "cid",
    
    # Mobile variations
    "mobile no": "mobile",
    "mobile number": "mobile",
    "phone number": "mobile",
    "contact no": "mobile",
}

# Status value mappings
STATUS_VALUE_MAP = {
    "not received": "not_received",
    "not deducted": "not_deducted",
    "pending": "pending",
    "paid": "paid",
    "partial": "partial",
    "overdue": "overdue",
    "waived": "waived",
    "n/a": "not_applicable",
    "na": "not_applicable",
    "-": "not_applicable",
    "": "not_applicable",
    "nil": "not_applicable",
}


def normalize_column_name(name: str) -> str:
    """Normalize a column name to lowercase, stripped, with single spaces."""
    if not name:
        return ""
    # Replace multiple spaces, tabs, newlines with single space
    normalized = re.sub(r"\s+", " ", str(name).strip().lower())
    return normalized


def apply_typo_correction(name: str) -> str:
    """Apply known typo corrections to a normalized column name."""
    normalized = normalize_column_name(name)
    return COLUMN_TYPO_MAP.get(normalized, normalized)


def parse_month_column(name: str) -> Optional[Tuple[str, int, int]]:
    """
    Parse a month column name.
    Returns (column_type, month, year) or None if not a month column.
    column_type: 'salary', 'external', 'received', 'deducted', 'not_received', 'not_deducted'
    """
    normalized = apply_typo_correction(name)
    
    # Try standard patterns first (with space)
    for pattern, col_type in MONTH_PATTERNS:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            return _extract_month_year(match, col_type, normalized)
    
    # Try flexible patterns (without space, e.g., "Feb2")
    for pattern, col_type in FLEXIBLE_MONTH_PATTERNS:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            return _extract_month_year(match, col_type, normalized)
    
    return None


def _extract_month_year(match, col_type: str, normalized: str) -> Optional[Tuple[str, int, int]]:
    """Extract month and year from regex match."""
    groups = match.groups()
    
    if col_type == "not_status":
        # Groups: (month, year)
        month_str = groups[0].lower()
        year_str = groups[1] if len(groups) > 1 and groups[1] else None
        
        # Determine if not_received or not_deducted from the original string
        if "not received" in normalized:
            col_type = "not_received"
        elif "not deducted" in normalized:
            col_type = "not_deducted"
        else:
            col_type = "not_received"  # default
    else:
        # Groups: (month, year)
        month_str = groups[0].lower()
        year_str = groups[1] if len(groups) > 1 and groups[1] else None
    
    month = MONTH_NAME_TO_NUM.get(month_str)
    if not month:
        return None
    
    # Parse year
    if year_str:
        year = int(year_str)
        if len(year_str) == 1:
            # Single digit year like "2" in "Feb2" -> assume current decade
            # e.g., 2 -> 2024, 3 -> 2024, etc.
            from datetime import date
            current_year = date.today().year
            decade = (current_year // 10) * 10
            year = decade + year
        elif year < 100:
            year += 2000 if year < 50 else 1900
    else:
        year = 2024  # Default, will be inferred from context
    
    return (col_type, month, year)


def get_canonical_column(name: str) -> Optional[str]:
    """Map a column name to its canonical form."""
    normalized = normalize_column_name(name)
    corrected = apply_typo_correction(normalized)
    
    for canonical, aliases in CANONICAL_COLUMNS.items():
        if corrected in [normalize_column_name(a) for a in aliases]:
            return canonical
    
    return None


def normalize_status_value(value: str) -> str:
    """Normalize a status value from Excel."""
    if not value:
        return "not_applicable"
    normalized = normalize_column_name(value)
    return STATUS_VALUE_MAP.get(normalized, normalized)


def parse_amount(value: any) -> Optional[float]:
    """Parse a numeric amount from Excel cell."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    
    str_val = str(value).strip()
    if not str_val or str_val.lower() in ("", "na", "n/a", "-", "nil"):
        return None
    
    # Remove commas, currency symbols, spaces
    cleaned = re.sub(r"[,\s₹$€£]", "", str_val)
    
    # Handle parentheses as negative
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(value: any) -> Optional[str]:
    """Parse a date from Excel cell, return ISO format string."""
    if value is None:
        return None
    
    from datetime import date, datetime
    
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    
    str_val = str(value).strip()
    if not str_val:
        return None
    
    # Try common date formats
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%b-%d-%Y",
        "%b-%d-%y",
        "%Y/%m/%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str_val, fmt).date().isoformat()
        except ValueError:
            continue
    
    return None


def clean_cid(value: any) -> str:
    """Clean CID value, preserving leading zeros."""
    if value is None:
        return ""
    # Convert to string, preserve leading zeros
    cid = str(value).strip()
    # Remove .0 if it's a float like "12345.0"
    if cid.endswith(".0"):
        cid = cid[:-2]
    return cid


def clean_mobile(value: any) -> Tuple[str, bool]:
    """Clean mobile number, return (cleaned, is_valid)."""
    if value is None:
        return "", True  # Blank is allowed but flagged
    
    mobile = str(value).strip()
    if not mobile:
        return "", True
    
    # Remove common formatting
    cleaned = re.sub(r"[\s\-\(\)\+]", "", mobile)
    
    # Check if it's a valid Indian mobile (10 digits starting with 6-9)
    is_valid = bool(re.match(r"^[6-9]\d{9}$", cleaned))
    
    # If it has country code, strip it
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
        is_valid = bool(re.match(r"^[6-9]\d{9}$", cleaned))
    
    return cleaned, is_valid


def derive_channel(payment_type: str, month_columns: Dict[str, List[str]]) -> Tuple[str, List[str]]:
    """
    Derive channel from payment type and cross-check with month columns.
    Returns (channel, warnings).
    """
    warnings = []
    pt = normalize_column_name(payment_type)
    
    # Map payment type to channel
    if "emi" in pt or "installment" in pt:
        channel = "internal"
    elif "external" in pt or "outsource" in pt:
        channel = "external"
    elif "salary" in pt or "payroll" in pt:
        channel = "internal"
    else:
        channel = "unknown"
    
    # Cross-check: if channel is internal, salary columns should have data
    # If channel is external, external columns should have data
    has_salary_data = any(
        col_type == "salary" and cols 
        for col_type, cols in month_columns.items()
    )
    has_external_data = any(
        col_type == "external" and cols 
        for col_type, cols in month_columns.items()
    )
    
    if channel == "internal" and not has_salary_data and has_external_data:
        warnings.append(f"Payment type suggests internal but only external month columns have data")
    elif channel == "external" and not has_external_data and has_salary_data:
        warnings.append(f"Payment type suggests external but only salary month columns have data")
    
    return channel, warnings


def reshape_month_columns(
    row: Dict[str, any],
    month_column_map: Dict[str, Tuple[str, int, int]]
) -> List[Dict[str, any]]:
    """
    Reshape wide month columns into long format (one row per contract per month).
    
    Args:
        row: Dict of column_name -> value for a single Excel row
        month_column_map: Dict of original_column_name -> (col_type, month, year)
    
    Returns:
        List of dicts with keys: due_month, external_amount, salary_amount, 
        received_amount, deducted_amount, not_status
    """
    from collections import defaultdict
    
    # Group by (year, month)
    month_data = defaultdict(lambda: {
        "external_amount": None,
        "salary_amount": None,
        "received_amount": None,
        "deducted_amount": None,
        "not_status": None,
    })
    
    for orig_col, (col_type, month, year) in month_column_map.items():
        value = row.get(orig_col)
        key = (year, month)
        
        if col_type == "salary":
            month_data[key]["salary_amount"] = parse_amount(value)
        elif col_type == "external":
            month_data[key]["external_amount"] = parse_amount(value)
        elif col_type == "received":
            month_data[key]["received_amount"] = parse_amount(value)
        elif col_type == "deducted":
            month_data[key]["deducted_amount"] = parse_amount(value)
        elif col_type in ("not_received", "not_deducted"):
            # Only set not_status if the cell has a meaningful value
            if value is not None:
                str_val = str(value).strip().lower()
                if str_val and str_val not in ("", "n/a", "na", "-", "nil", "no", "false", "0", "none"):
                    month_data[key]["not_status"] = col_type
    
    # Convert to list of rows
    result = []
    for (year, month), data in sorted(month_data.items()):
        # Only include months that have at least some data
        if any(v is not None for v in data.values()):
            from datetime import date
            due_month = date(year, month, 1)
            result.append({
                "due_month": due_month,
                **data,
            })
    
    return result