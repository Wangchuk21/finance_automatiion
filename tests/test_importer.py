"""Comprehensive tests for the Excel importer."""

import pytest
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.importer.column_map import (
    normalize_column_name,
    apply_typo_correction,
    parse_month_column,
    get_canonical_column,
    parse_amount,
    parse_date,
    clean_cid,
    clean_mobile,
    normalize_status_value,
    reshape_month_columns,
)
from app.importer.validation import validate_excel_import, ValidationReport
from app.importer.reader import read_excel_sheet, parse_sheet_to_contracts, import_excel_file


class TestColumnMap:
    """Tests for column name normalization and mapping."""
    
    def test_normalize_column_name(self):
        assert normalize_column_name("  Reference  ") == "reference"
        assert normalize_column_name("Cost\tCenter") == "cost center"
        assert normalize_column_name("Payment\nType") == "payment type"
        assert normalize_column_name("") == ""
    
    def test_apply_typo_correction(self):
        assert apply_typo_correction("cost centre") == "cost_center"
        assert apply_typo_correction("customer id") == "cid"
        assert apply_typo_correction("mobile no") == "mobile"
        assert apply_typo_correction("salary sept") == "salary sep"
        assert apply_typo_correction("external september") == "external sep"
        assert apply_typo_correction("normal column") == "normal column"
    
    def test_parse_month_column(self):
        # Standard format
        assert parse_month_column("External Sep 24") == ("external", 9, 2024)
        assert parse_month_column("Salary Sep 24") == ("salary", 9, 2024)
        assert parse_month_column("Received Sep 24") == ("received", 9, 2024)
        
        # Typo variations
        # "Feb2" -> single digit year, interpreted as current decade
        current_decade = (date.today().year // 10) * 10
        expected_year_feb2 = current_decade + 2
        assert parse_month_column("Salary Feb2") == ("salary", 2, expected_year_feb2)
        assert parse_month_column("Salary Sep 27") == ("salary", 9, 2027)
        assert parse_month_column("External  Sep  24") == ("external", 9, 2024)
        assert parse_month_column("SALARY SEPTEMBER 24") == ("salary", 9, 2024)
        
        # Not status
        assert parse_month_column("Not Received Sep 24") == ("not_received", 9, 2024)
        assert parse_month_column("Not Deducted Oct 24") == ("not_deducted", 10, 2024)
        
        # Generic
        assert parse_month_column("Sep 24") == ("external", 9, 2024)
        
        # Non-month columns
        assert parse_month_column("Reference") is None
        assert parse_month_column("Customer") is None
    
    def test_get_canonical_column(self):
        assert get_canonical_column("Reference") == "reference"
        assert get_canonical_column("Cost Center") == "cost_center"
        assert get_canonical_column("Payment Type") == "payment_type"
        assert get_canonical_column("Customer ID") == "cid"
        assert get_canonical_column("Mobile No") == "mobile"
        assert get_canonical_column("Unknown Column") is None
    
    def test_parse_amount(self):
        assert parse_amount(1000) == 1000.0
        assert parse_amount("1,000.50") == 1000.50
        assert parse_amount("₹1,22,640") == 122640.0
        assert parse_amount("(500)") == -500.0
        assert parse_amount("-1,000") == -1000.0
        assert parse_amount("") is None
        assert parse_amount("N/A") is None
        assert parse_amount("-") is None
        assert parse_amount("abc") is None
    
    def test_parse_date(self):
        assert parse_date("2024-01-15") == "2024-01-15"
        assert parse_date("15-01-2024") == "2024-01-15"
        assert parse_date("15/01/2024") == "2024-01-15"
        assert parse_date("15-Jan-2024") == "2024-01-15"
        assert parse_date("Jan-15-2024") == "2024-01-15"
        assert parse_date("") is None
        assert parse_date("invalid") is None
    
    def test_clean_cid(self):
        assert clean_cid("CID12345") == "CID12345"
        assert clean_cid("12345.0") == "12345"
        assert clean_cid("  CID123  ") == "CID123"
        assert clean_cid(None) == ""
        assert clean_cid("00123") == "00123"  # Leading zeros preserved
    
    def test_clean_mobile(self):
        assert clean_mobile("9876543210") == ("9876543210", True)
        assert clean_mobile("+91-9876543210") == ("9876543210", True)
        assert clean_mobile("987654321") == ("987654321", False)  # Too short
        assert clean_mobile("1234567890") == ("1234567890", False)  # Doesn't start with 6-9
        assert clean_mobile("") == ("", True)  # Blank allowed
        assert clean_mobile(None) == ("", True)  # None allowed
    
    def test_normalize_status_value(self):
        assert normalize_status_value("Not Received") == "not_received"
        assert normalize_status_value("Not Deducted") == "not_deducted"
        assert normalize_status_value("Pending") == "pending"
        assert normalize_status_value("Paid") == "paid"
        assert normalize_status_value("") == "not_applicable"
        assert normalize_status_value("-") == "not_applicable"
        assert normalize_status_value("N/A") == "not_applicable"
    
    def test_reshape_month_columns(self):
        row = {
            "External Sep 24": 5000,
            "Salary Sep 24": 5000,
            "Received Sep 24": 5000,
            "External Oct 24": 5000,
            "Salary Oct 24": 5000,
            "Received Oct 24": 0,
        }
        month_map = {
            "External Sep 24": ("external", 9, 2024),
            "Salary Sep 24": ("salary", 9, 2024),
            "Received Sep 24": ("received", 9, 2024),
            "External Oct 24": ("external", 10, 2024),
            "Salary Oct 24": ("salary", 10, 2024),
            "Received Oct 24": ("received", 10, 2024),
        }
        result = reshape_month_columns(row, month_map)
        
        assert len(result) == 2
        assert result[0]["due_month"].month == 9
        assert result[0]["external_amount"] == 5000
        assert result[0]["salary_amount"] == 5000
        assert result[0]["received_amount"] == 5000
        assert result[1]["due_month"].month == 10
        assert result[1]["received_amount"] == 0


class TestValidation:
    """Tests for validation logic."""
    
    def test_validate_missing_reference(self):
        rows = [{"Reference": "", "CID": "CID123", "Mobile": "9876543210"}]
        month_map = {}
        static_cols = {"Reference": "reference", "CID": "cid", "Mobile": "mobile"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.has_errors
        assert any(i.code == "missing_reference" for i in report.issues)
    
    def test_validate_duplicate_reference(self):
        rows = [
            {"Reference": "REF-001", "CID": "CID123", "Mobile": "9876543210"},
            {"Reference": "REF-001", "CID": "CID456", "Mobile": "8765432109"},
        ]
        month_map = {}
        static_cols = {"Reference": "reference", "CID": "cid", "Mobile": "mobile"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.has_errors
        assert any(i.code == "duplicate_reference" for i in report.issues)
    
    def test_validate_invalid_date(self):
        rows = [{"Reference": "REF-001", "Contract Date": "2024-13-45"}]
        month_map = {}
        static_cols = {"Reference": "reference", "Contract Date": "contract_date"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.has_errors
        assert any(i.code == "invalid_date" for i in report.issues)
    
    def test_validate_negative_amount(self):
        rows = [{"Reference": "REF-001", "Monthly Deduction": -1000}]
        month_map = {}
        static_cols = {"Reference": "reference", "Monthly Deduction": "monthly_deduction"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.has_errors
        assert any(i.code == "negative_amount" for i in report.issues)
    
    def test_validate_invalid_mobile_warning(self):
        rows = [{"Reference": "REF-001", "Mobile": "12345"}]
        month_map = {}
        static_cols = {"Reference": "reference", "Mobile": "mobile"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.has_warnings
        assert any(i.code == "invalid_mobile" for i in report.issues)
    
    def test_validate_totals_calculation(self):
        rows = [
            {
                "Reference": "REF-001",
                "External Sep 24": 5000,
                "Salary Sep 24": 5000,
                "Received Sep 24": 5000,
            }
        ]
        month_map = {
            "External Sep 24": ("external", 9, 2024),
            "Salary Sep 24": ("salary", 9, 2024),
            "Received Sep 24": ("received", 9, 2024),
        }
        static_cols = {"Reference": "reference"}
        
        report = validate_excel_import(rows, month_map, static_cols)
        
        assert report.stats["total_receivable"] == 5000.0  # max(5000, 5000)
        assert report.stats["total_collected"] == 5000.0
        assert report.stats["total_overdue"] == 0.0


class TestReader:
    """Tests for Excel reader."""
    
    def test_read_valid_excel(self):
        file_path = "/home/wangchuk/Documents/BT Work/finance automation/test_import.xlsx"
        parsed = read_excel_sheet(file_path)
        
        assert parsed.sheet_name == "EMI Data"
        assert len(parsed.headers) == 35
        assert len(parsed.static_columns) == 15
        assert len(parsed.month_columns) == 20
        assert len(parsed.rows) == 5  # Includes TOTAL row
    
    def test_parse_to_contracts(self):
        file_path = "/home/wangchuk/Documents/BT Work/finance automation/test_import.xlsx"
        parsed = read_excel_sheet(file_path)
        contracts = parse_sheet_to_contracts(parsed)
        
        assert len(contracts) == 4  # TOTAL row skipped
        for c in contracts:
            assert "reference" in c
            assert "installments" in c
            assert len(c["installments"]) == 6
    
    def test_full_import_pipeline(self):
        file_path = "/home/wangchuk/Documents/BT Work/finance automation/test_import.xlsx"
        contracts, report, preview = import_excel_file(file_path)
        
        assert len(contracts) == 4
        assert not report.has_errors
        assert "monthly_breakdown" in preview
        assert len(preview["monthly_breakdown"]) == 6
    
    def test_broken_file_rejected(self):
        file_path = "/home/wangchuk/Documents/BT Work/finance automation/test_broken_import.xlsx"
        contracts, report, preview = import_excel_file(file_path)
        
        assert report.has_errors
        assert report.error_count == 5
        # Should still parse valid rows
        assert len(contracts) == 6  # 7 rows - 1 missing ref


if __name__ == "__main__":
    pytest.main([__file__, "-v"])