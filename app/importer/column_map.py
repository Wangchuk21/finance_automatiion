"""Column name normalization and mapping for Excel imports."""

import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Pattern, Tuple, Union

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
    "start_date": ["posting date", "posting_date", "posting", "start date", "start_date"],
    "contract_date": ["contract date", "contract_date"],
    "end_date": ["ending date", "ending_date", "end date", "end_date"],
    "sales_amount": ["sales amount", "sales_amount", "amount", "sale amount", "sales amt"],
    "gst": ["gst", "tax", "gst amount"],
    # Monthly column patterns (base names)
    "monthly_deduction": ["monthly deduction", "monthly_deduction", "emi amount", "emi_amount"],
    "emi_received": ["emi received", "emi_received", "total received", "sum of emi received"],
    "overall_outstanding": ["overall outstanding", "overall_outstanding", "balance due", "outstanding"],
}

# Patterns to identify month columns
MONTH_PATTERNS = [
    # "Salary Sep 27", "Salary Feb2", "Salary Sep-24", "Salary Sep 2024", etc.
    (r"^salary\s+([a-z]{3,9})[-\s]*(\d{1,4})?$", "salary"),
    # "External Sep 27", "External Feb2", "External Feb-25", etc.
    (r"^external\s+([a-z]{3,9})[-\s]*(\d{1,4})?$", "external"),
    # "Received Sep 27", "Received Feb2", "Received Feb-25", etc.
    (r"^received\s+([a-z]{3,9})[-\s]*(\d{1,4})?$", "received"),
    # "Deducted Sep 27", "Deducted Feb2", etc.
    (r"^deducted\s+([a-z]{3,9})[-\s]*(\d{1,4})?$", "deducted"),
    # "Not Received Sep 27", "Not Deducted Feb2" - use non-capturing group for status type
    (r"^not\s+(?:received|deducted)\s+([a-z]{3,9})[-\s]*(\d{1,4})?$", "not_status"),
    # Generic "Sep 27", "Feb2", "Feb-25", "Feb 25", "February-25" - assume external
    (r"^([a-z]{3,9})[-\s]*(\d{1,4})?$", "external"),
    # Numeric month with year, like "02-25", "02/25", "02-2025" - assume external
    (r"^(\d{1,2})[-\s/]+(\d{2,4})$", "external"),
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


def parse_month_column(
    name: Any, paired_with: Optional[Tuple[int, int]] = None
) -> Optional[Tuple[str, int, int]]:
    """
    Parse a month column name or cell value.
    Supports:
    - Text strings like "Feb-25", "Feb 25", "External Sep 24", "Salary Feb2"
    - Excel date cells / datetime / date objects
    - ISO date strings like "2025-02-01"
    - Adjacency pairing via `paired_with`=(month, year)
    Returns (column_type, month, year) or None if not a month column.
    column_type: 'salary', 'external', 'received', 'deducted', 'not_received', 'not_deducted'
    """
    if name is None:
        return None

    # Direct Excel date cells
    if isinstance(name, (datetime, date)):
        return ("external", name.month, name.year)

    str_val = str(name).strip()
    if not str_val:
        return None

    # Check for ISO date string e.g. "2025-02-01 00:00:00" or "2025-02-01"
    iso_match = re.match(
        r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$",
        str_val,
    )
    if iso_match:
        y, m = int(iso_match.group(1)), int(iso_match.group(2))
        if 1 <= m <= 12:
            return ("external", m, y)

    normalized = apply_typo_correction(str_val)

    # If paired with adjacent month and this is a salary column
    if paired_with and (normalized.startswith("salary") or "salary" in normalized):
        return ("salary", paired_with[0], paired_with[1])

    # Try standard patterns first (with space or hyphen/slash)
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
        month_str = groups[0].lower()
        year_str = groups[1] if len(groups) > 1 and groups[1] else None

        if "not received" in normalized:
            col_type = "not_received"
        elif "not deducted" in normalized:
            col_type = "not_deducted"
        else:
            col_type = "not_received"
    else:
        month_str = groups[0].lower()
        year_str = groups[1] if len(groups) > 1 and groups[1] else None

    if month_str.isdigit():
        month = int(month_str)
        if not (1 <= month <= 12):
            return None
    else:
        month = MONTH_NAME_TO_NUM.get(month_str)
        if not month:
            return None

    # Parse year
    if year_str:
        year = int(year_str)
        if len(year_str) == 1:
            # Single digit year like "2" in "Feb2" -> assume current decade
            current_year = date.today().year
            decade = (current_year // 10) * 10
            year = decade + year
        elif year < 100:
            year += 2000 if year < 50 else 1900
    else:
        year = 2024  # Default, will be inferred from context if paired

    return (col_type, month, year)


def pair_adjacent_month_columns(headers: List[Any]) -> Dict[Any, Tuple[str, int, int]]:
    """
    Pair each month column with the Salary column right next to it (adjacency).
    When a month column (external or base month) is followed immediately by a Salary column,
    the Salary column inherits the (month, year) of the preceding month column.
    E.g.:
      "Feb-26" followed by "Salary Feb2" -> Salary Feb2 is (salary, 2, 2026)
      "Sep-26" followed by "Salary Sep 27" -> Salary Sep 27 is (salary, 9, 2026)
      "Mar-26" followed by "Salary March" -> Salary March is (salary, 3, 2026)
    """
    month_columns: Dict[Any, Tuple[str, int, int]] = {}
    i = 0
    n = len(headers)

    while i < n:
        header = headers[i]
        header_str = str(header).strip() if header is not None else ""

        # Skip static columns
        if get_canonical_column(header_str):
            i += 1
            continue

        month_info = parse_month_column(header)
        if not month_info:
            i += 1
            continue

        col_type, m, y = month_info

        # If this is a base/external month column, check if the adjacent column is a Salary column
        if col_type == "external" and i + 1 < n:
            next_header = headers[i + 1]
            next_str = str(next_header).strip().lower()

            if next_str.startswith("salary") or "salary" in next_str:
                month_columns[header] = month_info
                # Pair with adjacency: inherits (m, y) from the preceding month column
                month_columns[next_header] = ("salary", m, y)
                i += 2
                continue

        month_columns[header] = month_info
        i += 1

    return month_columns


def map_sheet_columns(
    headers: List[Any],
) -> Tuple[Dict[Any, Tuple[str, int, int]], Dict[str, str]]:
    """
    Map Excel headers into month columns (with adjacency pairing) and static columns.
    Returns (month_columns, static_columns).
    """
    month_columns = pair_adjacent_month_columns(headers)
    static_columns: Dict[str, str] = {}

    for header in headers:
        if header not in month_columns:
            header_str = str(header).strip() if header is not None else ""
            canonical = get_canonical_column(header_str)
            if canonical:
                static_columns[str(header)] = canonical

    return month_columns, static_columns


def validate_consecutive_months(
    months: List[Tuple[int, int]]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a sequence of (year, month) tuples are strictly consecutive.
    Returns (is_valid, error_message).
    """
    if not months or len(months) <= 1:
        return True, None

    for i in range(len(months) - 1):
        y1, m1 = months[i]
        y2, m2 = months[i + 1]
        expected_y, expected_m = (y1 + 1, 1) if m1 == 12 else (y1, m1 + 1)
        if (y2, m2) != (expected_y, expected_m):
            return False, (
                f"Month columns are not consecutive: {m1:02d}/{y1} is followed by "
                f"{m2:02d}/{y2} instead of {expected_m:02d}/{expected_y}"
            )

    return True, None


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


def parse_amount(value: Any) -> Optional[Decimal]:
    """Parse a numeric amount from Excel cell and return Decimal quantized to 0.01 (ROUND_HALF_UP)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    str_val = str(value).strip()
    if not str_val or str_val.lower() in ("", "na", "n/a", "-", "nil"):
        return None
    
    if str_val.lower() in ("not received", "not_received", "not deducted", "not_deducted"):
        return None

    # Remove commas, currency symbols, spaces (but keep decimal point)
    cleaned = re.sub(r"[,\s₹$€£]", "", str_val)
    # Also remove currency words like "Nu", "Nu.", "INR", etc.
    cleaned = re.sub(r"(?i)\b(nu\.?|inr)\b", "", cleaned)
    
    # Handle parentheses as negative
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_int(value: Any) -> Optional[int]:
    """Parse a whole-number field (EMI months, counts)."""
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    str_val = str(value).strip()
    if not str_val or str_val.lower() in ("", "na", "n/a", "-", "nil"):
        return None
    try:
        return int(round(float(str_val)))
    except (ValueError, TypeError):
        return None


def calculate_installment_due(
    monthly_deduction: Optional[Decimal],
    gst: Optional[Decimal] = None,
    month_index: int = 0,
) -> Decimal:
    """
    Calculate due amount for an installment:
    - first-month due = Monthly Deduction + GST
    - other months = Monthly Deduction
    """
    base = monthly_deduction or Decimal("0")
    if not isinstance(base, Decimal):
        base = Decimal(str(base))

    if month_index == 0:
        tax = gst or Decimal("0")
        if not isinstance(tax, Decimal):
            tax = Decimal(str(tax))
        return (base + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_date(value: Any) -> Optional[str]:
    """Parse a date from Excel cell (text, Excel date cell, datetime, serial), return ISO format string."""
    if value is None:
        return None

    # Handle openpyxl Cell object
    if hasattr(value, "value"):
        value = value.value
        if value is None:
            return None

    from datetime import date, datetime, timedelta

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    # Handle numeric Excel serial date (e.g. 45550 -> 2024-09-15)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 10000 <= value <= 100000:
            try:
                excel_epoch = datetime(1899, 12, 30)
                return (excel_epoch + timedelta(days=float(value))).date().isoformat()
            except Exception:
                pass

    str_val = str(value).strip()
    if not str_val or str_val.lower() in ("", "na", "n/a", "-", "nil", "none"):
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
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(str_val, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def format_text_cell(value: Any, number_format: Optional[str] = None) -> str:
    """
    Format a cell value as text, preserving leading zeros and formatting
    if numeric with a zero-padded format.
    E.g. numeric cell 249 with number_format="0000" returns "0249".
    """
    if value is None:
        return ""

    # If an openpyxl Cell object was passed
    if hasattr(value, "value"):
        number_format = getattr(value, "number_format", number_format)
        value = value.value
        if value is None:
            return ""

    # If value is already a string
    if isinstance(value, str):
        s = value.strip()
        if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
            return s[:-2]
        return s

    # Check if number_format specifies zero padding, e.g. "0000" or 00000
    if number_format:
        fmt = str(number_format).strip("\"'")
        if re.match(r"^0+$", fmt):
            width = len(fmt)
            if width > 1:
                if isinstance(value, int) and not isinstance(value, bool):
                    return f"{value:0{width}d}"
                elif isinstance(value, float) and value.is_integer():
                    return f"{int(value):0{width}d}"

    # If value is float/int
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)

    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)

    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def clean_cid(value: Any, number_format: Optional[str] = None) -> str:
    """Clean CID value, preserving leading zeros and text formatting."""
    return format_text_cell(value, number_format)


def clean_customer(value: Any, number_format: Optional[str] = None) -> str:
    """Clean Customer value, ensuring Customer stays text and zero-padded if formatted."""
    return format_text_cell(value, number_format)


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


def derive_channel(
    payment_type: Optional[str] = None,
    data: Optional[Any] = None,
    month_columns: Optional[Any] = None,
) -> Tuple[str, List[str]]:
    """
    Derive channel from Payment Type:
    - words employee/staff/salary => internal
    - words external/customer => external
    - Not "EMI"
    - Unknown => infer from data + warning

    Returns (channel, warnings).
    """
    warnings: List[str] = []
    pt = str(payment_type).strip().lower() if payment_type is not None else ""

    # Check words in payment_type
    has_internal_word = bool(re.search(r"\b(employee|staff|salary)\b", pt))
    has_external_word = bool(re.search(r"\b(external|customer)\b", pt))

    # Explicit requirement: Not "EMI"
    # "EMI" and generic "installment" do not map to internal or external
    channel: Optional[str] = None
    if has_internal_word and not has_external_word:
        channel = "internal"
    elif has_external_word and not has_internal_word:
        channel = "external"

    # Inspect data for amounts or presence of salary vs external
    salary_amount_total = Decimal("0")
    external_amount_total = Decimal("0")
    has_salary_data = False
    has_external_data = False

    # Case A: data is a list (e.g. list of installments)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                sal = item.get("salary_amount")
                ext = item.get("external_amount")
                if sal is not None:
                    parsed_sal = parse_amount(sal)
                    if parsed_sal is not None and parsed_sal > 0:
                        salary_amount_total += parsed_sal
                        has_salary_data = True
                if ext is not None:
                    parsed_ext = parse_amount(ext)
                    if parsed_ext is not None and parsed_ext > 0:
                        external_amount_total += parsed_ext
                        has_external_data = True

    # Case B: data is a dict (e.g. row dict or contract dict)
    elif isinstance(data, dict):
        if "installments" in data and isinstance(data["installments"], list):
            for item in data["installments"]:
                if isinstance(item, dict):
                    sal = item.get("salary_amount")
                    ext = item.get("external_amount")
                    if sal is not None:
                        parsed_sal = parse_amount(sal)
                        if parsed_sal is not None and parsed_sal > 0:
                            salary_amount_total += parsed_sal
                            has_salary_data = True
                    if ext is not None:
                        parsed_ext = parse_amount(ext)
                        if parsed_ext is not None and parsed_ext > 0:
                            external_amount_total += parsed_ext
                            has_external_data = True

        for k, v in data.items():
            if k == "installments" or v is None or v == "":
                continue
            k_lower = str(k).lower()
            parsed_v = parse_amount(v)
            if "salary" in k_lower:
                if parsed_v is not None and parsed_v > 0:
                    salary_amount_total += parsed_v
                    has_salary_data = True
                elif str(v).strip().lower() not in ("n/a", "na", "-", "nil", "none", "0"):
                    has_salary_data = True
            elif "external" in k_lower:
                if parsed_v is not None and parsed_v > 0:
                    external_amount_total += parsed_v
                    has_external_data = True
                elif str(v).strip().lower() not in ("n/a", "na", "-", "nil", "none", "0"):
                    has_external_data = True

    # Case C: month_columns provided (backward compatibility with dict of col_type -> cols)
    check_cols = month_columns or (
        data if isinstance(data, dict) and any(t in data for t in ("salary", "external")) else None
    )
    if isinstance(check_cols, dict):
        if "salary" in check_cols and check_cols["salary"]:
            has_salary_data = True
        if "external" in check_cols and check_cols["external"]:
            has_external_data = True

    if channel is None:
        # Unknown payment type => infer from data + warning
        if salary_amount_total > 0 and external_amount_total == 0:
            inferred = "internal"
        elif external_amount_total > 0 and salary_amount_total == 0:
            inferred = "external"
        elif salary_amount_total > external_amount_total and salary_amount_total > 0:
            inferred = "internal"
        elif external_amount_total > salary_amount_total and external_amount_total > 0:
            inferred = "external"
        elif has_salary_data and not has_external_data:
            inferred = "internal"
        elif has_external_data and not has_salary_data:
            inferred = "external"
        else:
            inferred = "unknown"

        channel = inferred
        pt_label = f"'{payment_type}'" if payment_type else "empty"
        if channel != "unknown":
            warnings.append(
                f"Payment type {pt_label} is unknown or ambiguous; inferred channel '{channel}' from data"
            )
        else:
            warnings.append(
                f"Payment type {pt_label} is unknown and could not infer channel from data"
            )
    else:
        # Cross-check if channel was determined from payment type
        if channel == "internal" and has_external_data and not has_salary_data:
            warnings.append("Payment type suggests internal but only external month columns have data")
        elif channel == "external" and has_salary_data and not has_external_data:
            warnings.append("Payment type suggests external but only salary month columns have data")

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
        received_amount, deducted_amount, not_status, status
    """
    from collections import defaultdict
    
    # Group by (year, month)
    month_data = defaultdict(lambda: {
        "external_amount": None,
        "salary_amount": None,
        "received_amount": None,
        "deducted_amount": None,
        "not_status": None,
        "status": None,
    })
    
    for orig_col, (col_type, month, year) in month_column_map.items():
        value = row.get(orig_col)
        key = (year, month)
        
        # Check if cell value is a status like "Not Received" or "Not Deducted"
        str_val = str(value).strip().lower() if value is not None else ""
        if str_val in ("not received", "not_received"):
            month_data[key]["not_status"] = "not_received"
            month_data[key]["status"] = "not_received"
            # Amount remains empty (None)
        elif str_val in ("not deducted", "not_deducted"):
            month_data[key]["not_status"] = "not_deducted"
            month_data[key]["status"] = "not_deducted"
            # Amount remains empty (None)
        elif col_type == "salary":
            parsed = parse_amount(value)
            if parsed is None and str_val not in ("", "n/a", "na", "-", "nil", "none"):
                month_data[key]["not_status"] = "note"
            else:
                month_data[key]["salary_amount"] = parsed
        elif col_type == "external":
            parsed = parse_amount(value)
            if parsed is None and str_val not in ("", "n/a", "na", "-", "nil", "none"):
                month_data[key]["not_status"] = "note"
            else:
                month_data[key]["external_amount"] = parsed
        elif col_type == "received":
            parsed = parse_amount(value)
            if parsed is None and str_val not in ("", "n/a", "na", "-", "nil", "none"):
                month_data[key]["not_status"] = "note"
            else:
                month_data[key]["received_amount"] = parsed
        elif col_type == "deducted":
            month_data[key]["deducted_amount"] = parse_amount(value)
        elif col_type in ("not_received", "not_deducted"):
            # Only set not_status if the cell has a meaningful value
            if value is not None and str_val not in ("", "n/a", "na", "-", "nil", "no", "false", "0", "none"):
                month_data[key]["not_status"] = col_type
                month_data[key]["status"] = col_type
        elif str_val in ("pending", "paid", "partial", "overdue", "waived"):
            month_data[key]["status"] = str_val

    
    # Convert to list of rows – emit ALL months (including blank ones)
    result = []
    for (year, month), data in sorted(month_data.items()):
        from datetime import date
        due_month = date(year, month, 1)
        result.append({
            "due_month": due_month,
            **data,
        })

    return result