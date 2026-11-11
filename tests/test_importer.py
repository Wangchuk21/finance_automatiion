"""Comprehensive tests for the Excel importer."""

import pytest
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.importer.column_map import (
    normalize_column_name,
    apply_typo_correction,
    parse_month_column,
    get_canonical_column,
    parse_amount,
    parse_date,
    clean_cid,
    clean_customer,
    clean_mobile,
    format_text_cell,
    normalize_status_value,
    reshape_month_columns,
    derive_channel,
    pair_adjacent_month_columns,
    map_sheet_columns,
    validate_consecutive_months,
    calculate_installment_due,
)
from app.importer.validation import validate_excel_import, ValidationReport
from app.importer.reader import read_excel_sheet, parse_sheet_to_contracts, import_excel_file, ParsedSheet
from app.importer.derived import compute_contract_metrics


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
        assert get_canonical_column("Posting Date") == "start_date"
        assert get_canonical_column("Ending Date") == "end_date"
        assert get_canonical_column("Start Date") == "start_date"
        assert get_canonical_column("End Date") == "end_date"
        assert get_canonical_column("Contract Date") == "contract_date"
        assert get_canonical_column("Unknown Column") is None
    
    def test_parse_amount(self):
        assert parse_amount(1000) == 1000.0
        assert parse_amount("1,000.50") == 1000.50
        assert parse_amount("₹1,22,640") == 122640.0
        assert parse_amount("Nu. 1,22,640") == 122640.0
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
        assert parse_date(datetime(2024, 1, 15, 10, 30)) == "2024-01-15"
        assert parse_date(date(2024, 1, 15)) == "2024-01-15"
        assert parse_date("") is None
        assert parse_date("invalid") is None

    def test_posting_and_ending_date_parsing_and_derivation(self):
        from app.importer.reader import ParsedSheet, parse_sheet_to_contracts
        parsed = ParsedSheet(
            sheet_name="Test",
            headers=["Reference", "Posting Date", "Ending Date", "EMI Months", "Monthly Deduction", "Salary Sep 24"],
            rows=[
                {
                    "Reference": "REF-01",
                    "Posting Date": "2024-09-01",
                    "Ending Date": "2025-08-01",
                    "EMI Months": 12,
                    "Monthly Deduction": 1000,
                    "Salary Sep 24": 1000,
                },
                {
                    "Reference": "REF-02",
                    "Posting Date": "2024-09-01",
                    "Ending Date": None,
                    "EMI Months": 12,
                    "Monthly Deduction": 1000,
                    "Salary Sep 24": 1000,
                },
                {
                    "Reference": "REF-03",
                    "Posting Date": None,
                    "Ending Date": "2025-08-01",
                    "EMI Months": 12,
                    "Monthly Deduction": 1000,
                    "Salary Sep 24": 1000,
                },
            ],
            month_columns={"Salary Sep 24": ("salary", 9, 2024)},
            static_columns={
                "Reference": "reference",
                "Posting Date": "start_date",
                "Ending Date": "end_date",
                "EMI Months": "emi_months",
                "Monthly Deduction": "monthly_deduction",
            },
        )
        contracts = parse_sheet_to_contracts(parsed)
        assert len(contracts) == 3

        c1 = next(c for c in contracts if c["reference"] == "REF-01")
        assert c1["start_date"] == "2024-09-01"
        assert c1["contract_date"] == "2024-09-01"
        assert c1["end_date"] == "2025-08-01"
        assert len(c1["installments"]) == 1

        c2 = next(c for c in contracts if c["reference"] == "REF-02")
        assert c2["start_date"] == "2024-09-01"
        assert c2["contract_date"] == "2024-09-01"
        assert c2["end_date"] == "2025-08-01"
        assert len(c2["installments"]) == 1

        c3 = next(c for c in contracts if c["reference"] == "REF-03")
        assert c3.get("start_date") is None
        assert len(c3["installments"]) == 0
        assert "schedule_error" in c3
    
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


class TestChannelFromPaymentType:
    """Tests for Channel derivation from Payment Type."""

    def test_internal_keywords(self):
        # words employee, staff, salary => internal
        for pt in [
            "Employee Installment",
            "employee",
            "Staff Loan",
            "staff deduction",
            "Salary Deduction",
            "salary mode",
        ]:
            channel, warnings = derive_channel(pt)
            assert channel == "internal"
            assert len(warnings) == 0

    def test_external_keywords(self):
        # words external, customer => external
        for pt in [
            "External Installment",
            "external payment",
            "Customer Direct",
            "customer installment",
            "External",
        ]:
            channel, warnings = derive_channel(pt)
            assert channel == "external"
            assert len(warnings) == 0

    def test_emi_not_automatically_internal(self):
        # "EMI" does not map to internal; without data it is unknown + warning
        channel, warnings = derive_channel("EMI")
        assert channel == "unknown"
        assert len(warnings) == 1
        assert "Payment type 'EMI' is unknown" in warnings[0]

        # Same for "EMI Installment"
        channel2, warnings2 = derive_channel("EMI Installment")
        assert channel2 == "unknown"
        assert len(warnings2) == 1

    def test_emi_inferred_from_salary_data(self):
        # "EMI" with salary data in row => inferred internal + warning
        row_salary = {"Salary Sep 24": 5000, "External Sep 24": 0}
        channel, warnings = derive_channel("EMI", data=row_salary)
        assert channel == "internal"
        assert len(warnings) == 1
        assert "inferred channel 'internal' from data" in warnings[0]

        # With installments list
        inst_salary = [{"salary_amount": 3500, "external_amount": None}]
        channel_inst, warnings_inst = derive_channel("EMI", data=inst_salary)
        assert channel_inst == "internal"
        assert len(warnings_inst) == 1

    def test_emi_inferred_from_external_data(self):
        # "EMI" with external data in row => inferred external + warning
        row_external = {"Salary Sep 24": 0, "External Sep 24": 5000}
        channel, warnings = derive_channel("EMI", data=row_external)
        assert channel == "external"
        assert len(warnings) == 1
        assert "inferred channel 'external' from data" in warnings[0]

    def test_unknown_payment_type_inferred_from_data(self):
        # Unrecognized payment type => infer from data + warning
        row_salary = {"Salary Feb 25": 1870}
        channel, warnings = derive_channel("Direct Transfer", data=row_salary)
        assert channel == "internal"
        assert len(warnings) == 1

        # Blank/None payment type
        channel_blank, warnings_blank = derive_channel("", data=row_salary)
        assert channel_blank == "internal"
        assert len(warnings_blank) == 1

        channel_none, warnings_none = derive_channel(None, data={"External Feb 25": 1870})
        assert channel_none == "external"
        assert len(warnings_none) == 1

    def test_unknown_payment_type_without_data(self):
        channel, warnings = derive_channel("Random Mode", data=None)
        assert channel == "unknown"
        assert len(warnings) == 1


class TestAdjacencyMonthSalaryPairing:
    """Tests for pairing each month column with the Salary column right next to it."""

    def test_pair_month_and_salary_adjacent(self):
        # Tests "Salary Feb2", "Salary Sep 27", "Salary March" adjacent to base month columns
        headers = [
            "Reference",
            "Feb-26",
            "Salary Feb2",
            "Mar-26",
            "Salary March",
            "Sep-26",
            "Salary Sep 27",
        ]
        month_columns = pair_adjacent_month_columns(headers)

        assert month_columns["Feb-26"] == ("external", 2, 2026)
        assert month_columns["Salary Feb2"] == ("salary", 2, 2026)

        assert month_columns["Mar-26"] == ("external", 3, 2026)
        assert month_columns["Salary March"] == ("salary", 3, 2026)

        assert month_columns["Sep-26"] == ("external", 9, 2026)
        assert month_columns["Salary Sep 27"] == ("salary", 9, 2026)

    def test_parse_month_column_paired_with(self):
        # Direct parsing with paired_with=(month, year) context
        assert parse_month_column("Salary Feb2", paired_with=(2, 2026)) == ("salary", 2, 2026)
        assert parse_month_column("Salary Sep 27", paired_with=(9, 2026)) == ("salary", 9, 2026)
        assert parse_month_column("Salary March", paired_with=(3, 2026)) == ("salary", 3, 2026)

    def test_map_sheet_columns_pairs_correctly(self):
        headers = [
            "Customer",
            "CID",
            "External Sep 24",
            "Salary Sep 24",
            "External Oct 24",
            "Salary Oct 24",
        ]
        month_columns, static_columns = map_sheet_columns(headers)

        assert static_columns["Customer"] == "customer"
        assert static_columns["CID"] == "cid"
        assert month_columns["External Sep 24"] == ("external", 9, 2024)
        assert month_columns["Salary Sep 24"] == ("salary", 9, 2024)
        assert month_columns["External Oct 24"] == ("external", 10, 2024)
        assert month_columns["Salary Oct 24"] == ("salary", 10, 2024)


class TestMonthHeaderParsingAndConsecutive:
    """Tests for month headers text/date cell parsing and consecutive validation."""

    def test_text_month_headers(self):
        assert parse_month_column("Feb-25") == ("external", 2, 2025)
        assert parse_month_column("Feb 25") == ("external", 2, 2025)
        assert parse_month_column("Feb-2025") == ("external", 2, 2025)
        assert parse_month_column("February-25") == ("external", 2, 2025)
        assert parse_month_column("02-25") == ("external", 2, 2025)
        assert parse_month_column("02/25") == ("external", 2, 2025)
        assert parse_month_column("02-2025") == ("external", 2, 2025)
        assert parse_month_column("2025-02") == ("external", 2, 2025)

    def test_excel_date_cells(self):
        dt_val = datetime(2025, 2, 1, 0, 0)
        assert parse_month_column(dt_val) == ("external", 2, 2025)

        date_val = date(2025, 2, 1)
        assert parse_month_column(date_val) == ("external", 2, 2025)

        assert parse_month_column("2025-02-01 00:00:00") == ("external", 2, 2025)
        assert parse_month_column("2025-02-01") == ("external", 2, 2025)

    def test_consecutive_months_validator(self):
        # Consecutive sequence
        is_valid, err = validate_consecutive_months([(2025, 2), (2025, 3), (2025, 4)])
        assert is_valid is True
        assert err is None

        # Across year boundary
        is_valid, err = validate_consecutive_months([(2024, 11), (2024, 12), (2025, 1), (2025, 2)])
        assert is_valid is True
        assert err is None

        # Gap between Feb and Apr (missing March)
        is_valid, err = validate_consecutive_months([(2025, 2), (2025, 4)])
        assert is_valid is False
        assert "Month columns are not consecutive" in err
        assert "02/2025 is followed by 04/2025 instead of 03/2025" in err

        # Out of order
        is_valid, err = validate_consecutive_months([(2025, 3), (2025, 2)])
        assert is_valid is False
        assert "Month columns are not consecutive" in err

    def test_validation_report_catches_non_consecutive_months(self):
        rows = [{"Reference": "REF-001", "Feb-25": 1000, "Apr-25": 1000}]
        month_map = {
            "Feb-25": ("external", 2, 2025),
            "Apr-25": ("external", 4, 2025),
        }
        static_cols = {"Reference": "reference"}

        report = validate_excel_import(rows, month_map, static_cols)
        assert report.has_errors
        assert any(i.code == "non_consecutive_months" for i in report.issues)


class TestCustomerAndCIDZeroPaddedText:
    """Tests for Customer and CID staying text, and zero-padded format returning '0249'."""

    def test_clean_cid_preserves_text_and_zero_padded(self):
        assert clean_cid("0249") == "0249"
        assert clean_cid(249, number_format="0000") == "0249"
        assert clean_cid(249, number_format="00000") == "00249"
        assert clean_cid("12345.0") == "12345"
        assert clean_cid(12345.0) == "12345"
        assert clean_cid(11508003636) == "11508003636"
        assert clean_cid(None) == ""

    def test_clean_customer_preserves_text_and_zero_padded(self):
        assert clean_customer("0249") == "0249"
        assert clean_customer(249, number_format="0000") == "0249"
        assert clean_customer(249, number_format="00000") == "00249"
        assert clean_customer("Yeshi Wangmo") == "Yeshi Wangmo"
        assert clean_customer(12345) == "12345"
        assert clean_customer(None) == ""

    def test_format_text_cell_with_cell_object(self):
        class MockCell:
            def __init__(self, value, number_format):
                self.value = value
                self.number_format = number_format

        cell = MockCell(249, "0000")
        assert format_text_cell(cell) == "0249"
        assert clean_cid(cell) == "0249"
        assert clean_customer(cell) == "0249"

    def test_excel_import_zero_padded_numeric_cells(self, tmp_path):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "EMI Data"

        # Headers
        ws.append(["Reference", "Customer", "CID", "Feb-25", "Salary Feb"])

        # Row 2: Customer and CID as numbers with zero-padded format "0000"
        ws.append(["REF-PAD", 249, 249, 1000, 1000])
        # Apply number formats
        ws["B2"].number_format = "0000"
        ws["C2"].number_format = "0000"

        file_path = str(tmp_path / "test_padded.xlsx")
        wb.save(file_path)

        parsed = read_excel_sheet(file_path)
        assert parsed.rows[0]["Customer"] == "0249"
        assert parsed.rows[0]["CID"] == "0249"

        contracts = parse_sheet_to_contracts(parsed)
        assert len(contracts) == 1
        assert contracts[0]["customer"] == "0249"
        assert contracts[0]["cid"] == "0249"
        assert isinstance(contracts[0]["customer"], str)
        assert isinstance(contracts[0]["cid"], str)


class TestMonthCellStatusValues:
    """Tests for 'Not Received' and 'Not Deducted' in month cells becoming status with empty amount and no error."""

    def test_not_received_in_month_cell_becomes_status_amount_empty(self):
        row = {
            "External Sep 24": 5000,
            "Received Sep 24": "Not Received",
        }
        month_map = {
            "External Sep 24": ("external", 9, 2024),
            "Received Sep 24": ("received", 9, 2024),
        }
        res = reshape_month_columns(row, month_map)

        assert len(res) == 1
        assert res[0]["not_status"] == "not_received"
        assert res[0]["status"] == "not_received"
        assert res[0]["received_amount"] is None  # amount empty
        assert res[0]["external_amount"] == 5000.0

    def test_not_deducted_in_month_cell_becomes_status_amount_empty(self):
        row = {
            "Salary Sep 24": "Not Deducted",
        }
        month_map = {
            "Salary Sep 24": ("salary", 9, 2024),
        }
        res = reshape_month_columns(row, month_map)

        assert len(res) == 1
        assert res[0]["not_status"] == "not_deducted"
        assert res[0]["status"] == "not_deducted"
        assert res[0]["salary_amount"] is None  # amount empty

    def test_not_received_and_not_deducted_not_an_error_in_validation(self):
        rows = [
            {
                "Reference": "REF-001",
                "Payment Type": "External Installment",
                "External Sep 24": 5000,
                "Received Sep 24": "Not Received",
                "Salary Sep 24": "Not Deducted",
            }
        ]
        month_map = {
            "External Sep 24": ("external", 9, 2024),
            "Salary Sep 24": ("salary", 9, 2024),
            "Received Sep 24": ("received", 9, 2024),
        }
        static_cols = {"Reference": "reference", "Payment Type": "payment_type"}

        report = validate_excel_import(rows, month_map, static_cols)
        assert not report.has_errors
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_full_pipeline_month_cell_status(self, tmp_path):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "EMI Data"

        ws.append(["Reference", "Payment Type", "Feb-25", "Salary Feb", "Received Feb 25"])
        ws.append(["REF-STAT", "External Installment", 1870, "Not Deducted", "Not Received"])

        file_path = str(tmp_path / "test_status.xlsx")
        wb.save(file_path)

        contracts, report, preview = import_excel_file(file_path)
        assert not report.has_errors
        assert len(contracts) == 1

        inst = contracts[0]["installments"][0]
        assert inst["due_month"] == date(2025, 2, 1)
        assert inst["external_amount"] == 1870.0
        assert inst["salary_amount"] is None  # amount empty, not an error
        assert inst["received_amount"] is None  # amount empty, not an error
        assert inst["not_status"] in ("not_received", "not_deducted")
        assert inst["status"] in ("not_received", "not_deducted")

    def test_formatted_amount_parsing_in_month_cells_and_static_cols(self):
        from app.importer.reader import ParsedSheet
        row = {
            "Reference": "REF-AMT",
            "Sales Amount": "1,22,640",
            "Monthly Deduction": "5,110.00",
            "Feb-25": "1,22,640",
            "Salary Feb": "5,110.00",
        }
        month_map = {
            "Feb-25": ("external", 2, 2025),
            "Salary Feb": ("salary", 2, 2025),
        }
        static_cols = {
            "Reference": "reference",
            "Sales Amount": "sales_amount",
            "Monthly Deduction": "monthly_deduction",
        }
        parsed = ParsedSheet(
            sheet_name="Test",
            headers=list(row.keys()),
            rows=[row],
            month_columns=month_map,
            static_columns=static_cols,
        )
        contracts = parse_sheet_to_contracts(parsed)
        assert contracts[0]["sales_amount"] == 122640.0
        assert contracts[0]["monthly_deduction"] == 5110.00
        assert contracts[0]["installments"][0]["external_amount"] == 122640.0
        assert contracts[0]["installments"][0]["salary_amount"] == 5110.00


class TestDecimalPrecisionAndTotals:
    """Test money is Decimal, sums are exact, and 3-row file total equals expected amount."""

    def test_decimal_precision_and_three_row_file_totals(self, tmp_path):
        # 1. Sum of 0.1 ten times is exact Decimal
        ten_parts = [parse_amount(0.1) for _ in range(10)]
        assert all(isinstance(v, Decimal) for v in ten_parts)
        sum_ten = sum(ten_parts)
        assert sum_ten == Decimal("1.00")
        assert isinstance(sum_ten, Decimal)

        # 2. Sum of 7201.20 + 13701.20 + 6500.00 is exact Decimal
        amt1 = parse_amount(7201.20)
        amt2 = parse_amount(13701.20)
        amt3 = parse_amount(6500.00)
        assert all(isinstance(v, Decimal) for v in (amt1, amt2, amt3))
        three_sum = amt1 + amt2 + amt3
        assert three_sum == Decimal("27402.40")
        assert isinstance(three_sum, Decimal)

        # 3. 3-row file's total equals the exact expected amount
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"

        ws.append(["Reference", "Sales Amount", "Salary Feb", "Feb-25"])
        ws.append(["R1", 7201.20, 7201.20, None])
        ws.append(["R2", 13701.20, 13701.20, None])
        ws.append(["R3", 6500.00, 6500.00, None])

        file_path = str(tmp_path / "three_rows.xlsx")
        wb.save(file_path)

        parsed = read_excel_sheet(file_path)
        report = validate_excel_import(parsed.rows, parsed.month_columns, parsed.static_columns)
        assert report.stats["total_receivable"] == Decimal("27402.40")
        assert isinstance(report.stats["total_receivable"], Decimal)

        contracts = parse_sheet_to_contracts(parsed)
        sales_total = sum((c["sales_amount"] for c in contracts), Decimal("0"))
        assert sales_total == Decimal("27402.40")
        assert isinstance(sales_total, Decimal)


class TestMobileValidationWarnings:
    """Tests for blank and invalid mobile numbers producing warnings without errors or sensitive data."""

    def test_blank_and_invalid_mobile_give_warning_without_number_in_message(self):
        rows = [
            {"Reference": "REF-01", "Mobile": "", "Payment Type": "Salary"},
            {"Reference": "REF-02", "Mobile": None, "Payment Type": "Salary"},
            {"Reference": "REF-03", "Mobile": "12345", "Payment Type": "Salary"},
        ]
        month_map = {}
        static_cols = {"Reference": "reference", "Mobile": "mobile", "Payment Type": "payment_type"}

        report = validate_excel_import(rows, month_map, static_cols)

        # Must give WARNING only, no errors
        assert not report.has_errors
        assert report.has_warnings
        assert report.error_count == 0
        assert report.warning_count == 3

        blank_warnings = report.get_warnings_by_code("blank_mobile")
        assert len(blank_warnings) == 2
        assert all(w.severity == "warning" for w in blank_warnings)

        invalid_warnings = report.get_warnings_by_code("invalid_mobile")
        assert len(invalid_warnings) == 1
        assert invalid_warnings[0].severity == "warning"
        # Message must not contain the number
        assert "12345" not in invalid_warnings[0].message
        assert invalid_warnings[0].message == "Invalid mobile format"


class TestReconciliationAndDueAmount:
    """Tests for EMI reconciliation warnings and installment due calculation."""

    def test_warning_month_cells_differs_from_emi_received(self):
        # (a) sum of month cells (5000 + 5000 = 10000) differs from EMI Received (8000) by > 0.01
        rows = [
            {
                "Reference": "REF-A1",
                "Payment Type": "Salary",
                "Salary Feb": 5000,
                "Salary Mar": 5000,
                "EMI Received": 8000,
            }
        ]
        month_map = {
            "Salary Feb": ("salary", 2, 2025),
            "Salary Mar": ("salary", 3, 2025),
        }
        static_cols = {
            "Reference": "reference",
            "Payment Type": "payment_type",
            "EMI Received": "emi_received",
        }

        report = validate_excel_import(rows, month_map, static_cols)

        assert not report.has_errors
        assert report.has_warnings
        warnings = report.get_warnings_by_code("emi_received_mismatch")
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"
        # Message includes Reference and the two amounts, nothing personal
        assert "REF-A1" in warnings[0].message
        assert "10000" in warnings[0].message
        assert "8000" in warnings[0].message

    def test_warning_sales_minus_received_gst_differs_from_overall_outstanding(self):
        # (b) Sales Amt: 50000, GST: 5000, EMI Received: 20000
        # Sales Amt - (received - GST) = 50000 - (20000 - 5000) = 35000
        # Sheet's Overall Outstanding = 30000 (differs by 5000 > 0.01)
        rows = [
            {
                "Reference": "REF-B1",
                "Payment Type": "Salary",
                "Sales Amt": 50000,
                "GST": 5000,
                "EMI Received": 20000,
                "Overall Outstanding": 30000,
            }
        ]
        month_map = {}
        static_cols = {
            "Reference": "reference",
            "Payment Type": "payment_type",
            "Sales Amt": "sales_amount",
            "GST": "gst",
            "EMI Received": "emi_received",
            "Overall Outstanding": "overall_outstanding",
        }

        report = validate_excel_import(rows, month_map, static_cols)

        assert not report.has_errors
        assert report.has_warnings
        warnings = report.get_warnings_by_code("overall_outstanding_mismatch")
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"
        # Message includes Reference and the two amounts, nothing personal
        assert "REF-B1" in warnings[0].message
        assert "35000" in warnings[0].message
        assert "30000" in warnings[0].message

    def test_first_month_due_equals_monthly_deduction_plus_gst_other_months_equal_monthly_deduction(self):
        # Direct function check
        monthly_deduction = Decimal("5000.00")
        gst = Decimal("900.00")
        assert calculate_installment_due(monthly_deduction, gst, month_index=0) == Decimal("5900.00")
        assert calculate_installment_due(monthly_deduction, gst, month_index=1) == Decimal("5000.00")
        assert calculate_installment_due(monthly_deduction, gst, month_index=2) == Decimal("5000.00")

        # Parsing contract installments check
        row = {
            "Reference": "REF-DUE",
            "Payment Type": "Salary",
            "Monthly Deduction": "5000.00",
            "GST": "900.00",
            "Salary Feb": "5900.00",
            "Salary Mar": "5000.00",
            "Salary Apr": "5000.00",
        }
        month_map = {
            "Salary Feb": ("salary", 2, 2025),
            "Salary Mar": ("salary", 3, 2025),
            "Salary Apr": ("salary", 4, 2025),
        }
        static_cols = {
            "Reference": "reference",
            "Payment Type": "payment_type",
            "Monthly Deduction": "monthly_deduction",
            "GST": "gst",
        }
        parsed = ParsedSheet(
            sheet_name="TestSheet",
            headers=list(row.keys()),
            rows=[row],
            month_columns=month_map,
            static_columns=static_cols,
        )
        contracts = parse_sheet_to_contracts(parsed)
        assert len(contracts) == 1
        installments = contracts[0]["installments"]
        assert len(installments) == 3
        # First month due = Monthly Deduction + GST
        assert installments[0]["due_amount"] == Decimal("5900.00")
        # Other months due = Monthly Deduction
        assert installments[1]["due_amount"] == Decimal("5000.00")
        assert installments[2]["due_amount"] == Decimal("5000.00")


class TestNoteCellHandling:
    """Month cell with unparseable text → cell_status='note', no value in messages."""

    def test_text_cell_with_digits_and_name(self):
        from app.importer.column_map import reshape_month_columns, map_sheet_columns
        from app.importer.validation import validate_excel_import, ValidationReport
        from datetime import date

        # Build a minimal month_column_map with one external month column
        month_column_map = {"Feb-25": ("external", 2, 2025)}

        # Row: text that contains digits and a name - must NOT appear in any message
        row = {"Feb-25": "John 500"}

        installments = reshape_month_columns(row, month_column_map)
        assert len(installments) == 1
        inst = installments[0]
        # Amount must be NULL (not guessed)
        assert inst.get("external_amount") is None
        assert inst.get("salary_amount") is None
        # cell_status must be 'note'
        assert inst.get("not_status") == "note"

        # Now check validation: the warning message must not contain the cell value
        from app.importer.reader import ParsedSheet
        headers = ["Reference", "Feb-25"]
        rows = [{"Reference": "REF-001", "Feb-25": "John 500"}]
        static_cols = {"reference": "Reference"}
        parsed = ParsedSheet(
            sheet_name="Sheet1",
            headers=headers,
            rows=rows,
            month_columns=month_column_map,
            static_columns=static_cols,
        )
        report = validate_excel_import(rows, month_column_map, static_cols)
        all_messages = " ".join(
            issue["message"] for issue in report.to_dict().get("issues", [])
        )
        # The cell value must not appear verbatim in any message
        assert "John 500" not in all_messages
        assert "500" not in all_messages or "John" not in all_messages  # at minimum no combined personal text


# ---------------------------------------------------------------------------
# Input-only headers + derived (calculated) columns
# ---------------------------------------------------------------------------

class TestDerivedColumns:
    """Uploading only the input columns must still produce the derived values."""

    def test_new_template_header_aliases(self):
        assert get_canonical_column("Item Name") == "item"
        assert get_canonical_column("CID/PASSPORT No/Work Permit") == "cid"
        assert get_canonical_column("Mobile/Contact No") == "mobile"
        # punctuation/spacing variants
        assert get_canonical_column("CID / Passport No / Work Permit") == "cid"
        assert get_canonical_column("Mobile / Contact No.") == "mobile"

    def test_derived_metrics_fully_paid(self):
        from datetime import date as _date
        installments = [
            {
                "due_month": _date(2025, 2, 1),
                "due_amount": Decimal("1870"),
                "received_amount": Decimal("1870"),
            }
            for _ in range(20)
        ]
        m = compute_contract_metrics(
            monthly_deduction=Decimal("1870"),
            gst=None,
            sales_amount=Decimal("44880"),
            emi_months=20,
            start_date=_date(2025, 2, 26),
            as_of=_date(2026, 9, 30),
            installments=installments,
        )
        assert m.no_of_ins_to_be_recd == 20
        assert m.emi_receivable == Decimal("37400.00")
        assert m.emi_received == Decimal("37400.00")
        assert m.balance_due == Decimal("0.00")
        assert m.advance == Decimal("0.00")
        assert m.overall_outstanding == Decimal("7480.00")
        assert m.no_on_inst_due == Decimal("0.00")
        assert m.age_days == 0
        assert m.alert == "Normal"
        assert m.aging_bucket == "0-30"

    def test_derived_metrics_partial_and_advance(self):
        from datetime import date as _date
        start = _date(2025, 1, 15)

        partial = [
            {"due_amount": Decimal("1000"), "received_amount": Decimal("1000")},
            {"due_amount": Decimal("1000"), "received_amount": Decimal("1000")},
            {"due_amount": Decimal("1000"), "received_amount": Decimal("1000")},
            {"due_amount": Decimal("1000"), "received_amount": Decimal("0")},
        ]
        m = compute_contract_metrics(
            monthly_deduction=Decimal("1000"),
            gst=Decimal("0"),
            sales_amount=Decimal("12000"),
            emi_months=12,
            start_date=start,
            as_of=_date(2025, 4, 30),
            installments=partial,
        )
        assert m.no_of_ins_to_be_recd == 4
        assert m.emi_receivable == Decimal("4000.00")
        assert m.balance_due == Decimal("1000.00")
        assert m.no_on_inst_due == Decimal("1.00")
        assert m.age_days == 30
        assert m.alert == "Watch"
        assert m.aging_bucket == "0-30"

        overpaid = [
            {"due_amount": Decimal("1000"), "received_amount": Decimal("2500")},
        ]
        m2 = compute_contract_metrics(
            monthly_deduction=Decimal("1000"),
            gst=Decimal("0"),
            sales_amount=Decimal("12000"),
            emi_months=12,
            start_date=start,
            as_of=_date(2025, 1, 31),
            installments=overpaid,
        )
        assert m2.emi_receivable == Decimal("1000.00")
        assert m2.advance == Decimal("1500.00")
        assert m2.balance_due == Decimal("0.00")

    def test_preview_summary_uses_scheduled_due_and_totals(self):
        from datetime import date as _date
        from app.importer.validation import generate_preview_summary

        contracts = [{
            "reference": "X1",
            "start_date": _date(2025, 1, 1),
            "emi_months": 2,
            "monthly_deduction": Decimal("1000"),
            "gst": Decimal("0"),
            "sales_amount": Decimal("2500"),
            "installments": [
                {"due_month": _date(2025, 1, 1), "due_amount": Decimal("1000"),
                 "received_amount": Decimal("1000")},
                {"due_month": _date(2025, 2, 1), "due_amount": Decimal("1000"),
                 "received_amount": Decimal("500")},
            ],
        }]
        stats = generate_preview_summary(contracts, {}, as_of=_date(2025, 3, 1))

        assert Decimal(stats["monthly_breakdown"]["2025-01"]["due"]) == Decimal("1000")
        assert Decimal(stats["monthly_breakdown"]["2025-02"]["due"]) == Decimal("1000")
        assert Decimal(stats["monthly_breakdown"]["2025-02"]["received"]) == Decimal("500")
        assert Decimal(stats["totals"]["emi_received"]) == Decimal("1500")
        assert Decimal(stats["totals"]["emi_receivable"]) == Decimal("2000")
        assert Decimal(stats["totals"]["balance_due"]) == Decimal("500")
        assert Decimal(stats["totals"]["overall_outstanding"]) == Decimal("1000")

    def test_adding_next_month_column(self, tmp_path):
        """Adding an Oct-26 pair must create/update installments without errors."""
        from datetime import date as _date
        from openpyxl import Workbook

        headers = [
            "Item Name", "Brand", "Reference", "CC", "Region", "Cost Center",
            "Ministry/Agency", "Payment Type", "EMI Months", "Customer",
            "CID/PASSPORT No/Work Permit", "Mobile/Contact No", "Posting Date",
            "Month", "Year", "Ending Date", "Monthly Deduction", "Rate", "Data",
            "Sales Amt", "Qty", "GST", "Deferred",
            "Aug-26", "Salary Aug 26", "Sep-26", "Salary Sep 27",
            "Oct-26", "Salary Oct 26",
        ]

        def make_row(ref, posting, ending, sep=None, oct_ext=None, oct_sal=None):
            return [
                "Phone", "Samsung", ref, "CC1", "Western Region", "CC1",
                "MOESD", "Employee Installment", 2, "Test Customer",
                "1122334455", "17123456", posting, None, None, ending,
                1000, None, None, 2000, 1, 0, 1,
                None, None, sep, None, oct_ext, oct_sal,
            ]

        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        # P: Sep-26..Oct-26, October paid (inside schedule)
        ws.append(make_row("TEST-OCT-IN", _date(2026, 9, 10), _date(2026, 10, 10),
                           sep=1000, oct_ext=1000))
        # Q: Aug-26..Sep-26, extra October salary payment (outside schedule)
        ws.append(make_row("TEST-OCT-OUT", _date(2026, 8, 10), _date(2026, 9, 10),
                           sep=1000, oct_sal=1000))
        # R: Aug-26..Sep-26, no October payment (no outside row)
        ws.append(make_row("TEST-OCT-NONE", _date(2026, 8, 10), _date(2026, 9, 10),
                           sep=1000))

        path = tmp_path / "second_month.xlsx"
        wb.save(path)

        contracts, report, preview = import_excel_file(
            str(path), as_of=_date(2026, 10, 31)
        )
        assert report.error_count == 0
        by_ref = {c["reference"]: c["installments"] for c in contracts}

        inside = by_ref["TEST-OCT-IN"]
        assert len(inside) == 2
        assert inside[-1]["due_month"] == _date(2026, 10, 1)
        assert inside[-1]["due_amount"] == Decimal("1000.00")
        assert inside[-1]["external_amount"] == Decimal("1000")

        outside = by_ref["TEST-OCT-OUT"]
        assert len(outside) == 3
        assert outside[-1]["due_month"] == _date(2026, 10, 1)
        assert outside[-1]["due_amount"] is None
        assert outside[-1]["salary_amount"] == Decimal("1000")

        no_payment = by_ref["TEST-OCT-NONE"]
        assert len(no_payment) == 2
        assert all(i["due_month"] != _date(2026, 10, 1) for i in no_payment)

        assert Decimal(preview["totals"]["emi_received"]) == Decimal("5000")
        assert Decimal(preview["totals"]["emi_receivable"]) == Decimal("6000")
        assert Decimal(preview["totals"]["balance_due"]) == Decimal("1000")
        assert Decimal(preview["totals"]["overall_outstanding"]) == Decimal("1000")

    def test_upload_without_derived_columns(self, tmp_path):
        from datetime import date as _date
        from openpyxl import Workbook

        headers = [
            "Item Name", "Brand", "Reference", "CC", "Region", "Cost Center",
            "Ministry/Agency", "Payment Type", "EMI Months", "Customer",
            "CID/PASSPORT No/Work Permit", "Mobile/Contact No", "Posting Date",
            "Month", "Year", "Ending Date", "Monthly Deduction", "Rate", "Data",
            "Sales Amt", "Qty", "GST", "Deferred",
            "Feb-25", "Salary Feb", "Mar-25", "Salary Mar",
        ]
        row = [
            "Laptop", "Dell", "TEST-INT-1", "CC1", "Western Region", "CC1",
            "MOESD", "Employee Installment", 2, "Test Employee",
            "1122334455", "17123456", _date(2025, 2, 10),
            2, 2025, _date(2025, 3, 10), 1000, None, None,
            2400, 1, 0, 1,
            None, 1000, None, 1000,
        ]
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        ws.append(row)
        path = tmp_path / "input_only.xlsx"
        wb.save(path)

        contracts, report, preview = import_excel_file(
            str(path), as_of=_date(2026, 9, 30)
        )
        assert not report.has_errors
        assert len(contracts) == 1
        c = contracts[0]
        assert c["item"] == "Laptop"
        assert c["cid"] == "1122334455"
        assert c["mobile"] == "17123456"
        assert c["reference"] == "TEST-INT-1"
        assert len(c["installments"]) == 2

        assert Decimal(preview["totals"]["emi_received"]) == Decimal("2000")
        assert Decimal(preview["totals"]["emi_receivable"]) == Decimal("2000")
        assert Decimal(preview["totals"]["balance_due"]) == Decimal("0")
        assert Decimal(preview["totals"]["overall_outstanding"]) == Decimal("400")


# ---------------------------------------------------------------------------
# as_of_date schema validator tests
# ---------------------------------------------------------------------------

class TestAsOfDateValidator:
    """Tests for _parse_as_of_date in app/schemas/uploads.py."""

    def test_yyyy_mm_dd_accepted(self):
        from app.schemas.uploads import _parse_as_of_date
        from datetime import date
        result = _parse_as_of_date("2025-03-15")
        assert result == date(2025, 3, 15)

    def test_yyyy_mm_converted_to_month_end(self):
        from app.schemas.uploads import _parse_as_of_date
        from datetime import date
        # February 2025 has 28 days
        result = _parse_as_of_date("2025-02")
        assert result == date(2025, 2, 28)
        # January 2025 has 31 days
        result = _parse_as_of_date("2025-01")
        assert result == date(2025, 1, 31)

    def test_future_date_rejected_with_422(self):
        from app.schemas.uploads import _parse_as_of_date
        from datetime import date, timedelta
        future = (date.today() + timedelta(days=1)).isoformat()
        with pytest.raises(ValueError, match="cannot be in the future"):
            _parse_as_of_date(future)


# ---------------------------------------------------------------------------
# DB-write tests – run against finance_test (never finance_automation)
# ---------------------------------------------------------------------------

import asyncio
import os
import pytest

# Only run when DATABASE_URL explicitly points at finance_test
# Only run against finance_test (never finance_automation)
_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL")
    if "finance_test" in os.environ.get("DATABASE_URL", "")
    else "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test",
)
assert "finance_test" in _DB_URL, f"Expected finance_test in URL, got {_DB_URL}"
assert "finance_automation" not in _DB_URL, "MUST NEVER RUN AGAINST finance_automation"

_SKIP_DB = "finance_test" not in _DB_URL


@pytest.mark.skipif(_SKIP_DB, reason="Needs finance_test DATABASE_URL")
def test_three_contracts_db_write():
    """End-to-end upsert test against finance_test DB (3 synthetic contracts with dates and tenure)."""
    asyncio.run(_run_db_write_test())


async def _run_db_write_test():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    from app.importer.service import upsert_contracts
    from app.models import Installment, Contract
    from sqlalchemy import select

    engine = create_async_engine(_DB_URL, echo=False)
    # Create tables fresh
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    months = [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)]

    def _inst(due_month, ext, sal, due, cell_status=None):
        return {
            "due_month": due_month,
            "external_amount": Decimal(str(ext)) if ext is not None else None,
            "salary_amount": Decimal(str(sal)) if sal is not None else None,
            "due_amount": Decimal(str(due)) if due is not None else None,
            "not_status": cell_status,
        }

    contracts = [
        # 1 – Employee: salary payments only
        {
            "reference": "EMP-001",
            "payment_type": "salary",
            "sales_amount": Decimal("30000.00"),
            "gst": Decimal("900.00"),
            "monthly_deduction": Decimal("5000.00"),
            "start_date": "2025-02-01",
            "end_date": "2025-04-01",
            "emi_months": 3,
            "installments": [
                _inst(months[0], None, "5900.00", "5900.00"),
                _inst(months[1], None, "5000.00", "5000.00"),
                _inst(months[2], None, "5000.00", "5000.00"),
            ],
        },
        # 2 – External: external payments only
        {
            "reference": "EXT-001",
            "payment_type": "external",
            "sales_amount": Decimal("20000.00"),
            "gst": Decimal("600.00"),
            "monthly_deduction": Decimal("3000.00"),
            "start_date": date(2025, 2, 1),
            "end_date": date(2025, 4, 1),
            "emi_months": 3,
            "installments": [
                _inst(months[0], "3600.00", None, "3600.00"),
                _inst(months[1], "3000.00", None, "3000.00"),
                _inst(months[2], "3000.00", None, "3000.00"),
            ],
        },
        # 3 – Blank cells with one "Not Received"
        {
            "reference": "BLK-001",
            "payment_type": "external",
            "sales_amount": Decimal("10000.00"),
            "gst": Decimal("300.00"),
            "monthly_deduction": Decimal("2000.00"),
            "start_date": "2025-02-01",
            "end_date": "2025-04-01",
            "emi_months": 3,
            "installments": [
                _inst(months[0], None, None, "2300.00", cell_status="not_received"),
                _inst(months[1], None, None, "2000.00"),
                _inst(months[2], None, None, "2000.00"),
            ],
        },
    ]

    async with async_session() as s, s.begin():
        await upsert_contracts(s, contracts, upload_id=1)
        await s.flush()

        # Assert start_date, end_date, emi_months, monthly_deduction stored for all 3 contracts
        for ref, exp_start, exp_end, exp_emi, exp_md in [
            ("EMP-001", date(2025, 2, 1), date(2025, 4, 1), 3, Decimal("5000.00")),
            ("EXT-001", date(2025, 2, 1), date(2025, 4, 1), 3, Decimal("3000.00")),
            ("BLK-001", date(2025, 2, 1), date(2025, 4, 1), 3, Decimal("2000.00")),
        ]:
            c = (await s.execute(select(Contract).where(Contract.reference == ref))).scalar_one()
            assert c.start_date == exp_start, f"{ref}: expected start_date {exp_start}, got {c.start_date}"
            assert c.end_date == exp_end, f"{ref}: expected end_date {exp_end}, got {c.end_date}"
            assert c.contract_date == exp_start, f"{ref}: expected contract_date {exp_start}, got {c.contract_date}"
            assert c.emi_months == exp_emi, f"{ref}: expected emi_months {exp_emi}, got {c.emi_months}"
            assert c.monthly_deduction == exp_md, f"{ref}: expected monthly_deduction {exp_md}, got {c.monthly_deduction}"

        # installment counts
        for ref, expected in [("EMP-001", 3), ("EXT-001", 3), ("BLK-001", 3)]:
            stmt = (
                select(Installment)
                .join(Contract, Contract.id == Installment.contract_id)
                .where(Contract.reference == ref)
            )
            rows = (await s.execute(stmt)).scalars().all()
            assert len(rows) == expected, f"{ref}: expected {expected} rows, got {len(rows)}"

        # EMP-001 salary sums
        emp_rows = (await s.execute(
            select(Installment)
            .join(Contract, Contract.id == Installment.contract_id)
            .where(Contract.reference == "EMP-001")
        )).scalars().all()
        assert sum(r.salary_amount or Decimal("0") for r in emp_rows) == Decimal("15900.00")
        assert sum(r.received_amount for r in emp_rows) == Decimal("15900.00")
        assert all(r.external_amount is None for r in emp_rows)

        # EXT-001 external sum and sales_amount
        ext_rows = (await s.execute(
            select(Installment)
            .join(Contract, Contract.id == Installment.contract_id)
            .where(Contract.reference == "EXT-001")
        )).scalars().all()
        assert sum(r.external_amount or Decimal("0") for r in ext_rows) == Decimal("9600.00")
        ext_c = (await s.execute(select(Contract).where(Contract.reference == "EXT-001"))).scalar_one()
        assert ext_c.sales_amount == Decimal("20000.00")

        # BLK-001 first month cell_status
        blk_rows = sorted(
            (await s.execute(
                select(Installment)
                .join(Contract, Contract.id == Installment.contract_id)
                .where(Contract.reference == "BLK-001")
            )).scalars().all(),
            key=lambda r: r.due_month,
        )
        assert blk_rows[0].cell_status == "not_received"
        assert blk_rows[0].received_amount == Decimal("0.00")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_contract_schedule_inside_outside_and_db():
    """
    Test contract schedule:
    - Contract A: posted mid-range (starts Mar 25, ends May 25, EMI 3) -> 3 rows, all due_amount populated.
    - Contract B: ending before last sheet month (starts Jan 25, ends Mar 25, EMI 3) -> 3 rows, all due_amount populated.
    - Contract C: with payment cell before its start month (starts Mar 25, payment in Feb 25) -> 4 rows,
      Feb 25 has due_amount = NULL, and C's payment is kept.
    - Schedule length mismatch warning test (reference + row only, no personal values).
    - Inserted into finance_test (never finance_automation).
    """
    from app.importer.reader import ParsedSheet, parse_sheet_to_contracts
    from app.importer.service import upsert_contracts
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.models import Base, Contract, Installment
    from decimal import Decimal
    from datetime import date

    TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test"
    assert "finance_test" in TEST_DB_URL
    assert "finance_automation" not in TEST_DB_URL

    # Define 5 sheet months: Jan 2025 .. May 2025
    month_columns = {
        "Salary Jan 25": ("salary", 1, 2025),
        "Salary Feb 25": ("salary", 2, 2025),
        "Salary Mar 25": ("salary", 3, 2025),
        "Salary Apr 25": ("salary", 4, 2025),
        "Salary May 25": ("salary", 5, 2025),
    }
    static_columns = {
        "Reference": "reference",
        "Payment Type": "payment_type",
        "Posting Date": "start_date",
        "Ending Date": "end_date",
        "EMI Months": "emi_months",
        "Monthly Deduction": "monthly_deduction",
        "GST": "gst",
    }

    # Contract A: posted mid-range (starts Mar 25, ends May 25, EMI 3)
    # Sheet has Jan..May (5 months). Jan, Feb are before start month and blank -> omitted.
    # Mar, Apr, May inside schedule -> 3 rows.
    row_a = {
        "Reference": "CTR-A",
        "Payment Type": "salary",
        "Posting Date": "2025-03-01",
        "Ending Date": "2025-05-01",
        "EMI Months": "3",
        "Monthly Deduction": "5000.00",
        "GST": "900.00",
        "Salary Jan 25": None,
        "Salary Feb 25": None,
        "Salary Mar 25": "5900.00",
        "Salary Apr 25": "5000.00",
        "Salary May 25": "5000.00",
    }

    # Contract B: ending before last sheet month (starts Jan 25, ends Mar 25, EMI 3)
    # Sheet has Jan..May (5 months). Jan, Feb, Mar inside schedule -> 3 rows.
    # Apr, May after end month and blank -> omitted.
    row_b = {
        "Reference": "CTR-B",
        "Payment Type": "salary",
        "Posting Date": "2025-01-01",
        "Ending Date": "2025-03-01",
        "EMI Months": "3",
        "Monthly Deduction": "3000.00",
        "GST": "600.00",
        "Salary Jan 25": "3600.00",
        "Salary Feb 25": "3000.00",
        "Salary Mar 25": "3000.00",
        "Salary Apr 25": None,
        "Salary May 25": None,
    }

    # Contract C: with payment cell before its start month (starts Mar 25, ends May 25, EMI 3)
    # Jan is blank -> omitted. Feb has payment (4500) before start month -> created with due_amount=NULL!
    # Mar, Apr, May inside schedule -> 4 rows total.
    row_c = {
        "Reference": "CTR-C",
        "Payment Type": "salary",
        "Posting Date": "2025-03-01",
        "Ending Date": "2025-05-01",
        "EMI Months": "3",
        "Monthly Deduction": "4000.00",
        "GST": "500.00",
        "Salary Jan 25": None,
        "Salary Feb 25": "4500.00",
        "Salary Mar 25": "4500.00",
        "Salary Apr 25": "4000.00",
        "Salary May 25": "4000.00",
    }

    # Contract D: schedule length mismatch (starts Jan 25, ends Apr 25 = 4 months, but EMI months = 3)
    row_d = {
        "Reference": "CTR-D",
        "Payment Type": "salary",
        "Posting Date": "2025-01-01",
        "Ending Date": "2025-04-01",
        "EMI Months": "3",
        "Monthly Deduction": "2000.00",
        "GST": "300.00",
        "Salary Jan 25": "2300.00",
        "Salary Feb 25": "2000.00",
        "Salary Mar 25": "2000.00",
        "Salary Apr 25": "2000.00",
        "Salary May 25": None,
    }

    parsed = ParsedSheet(
        sheet_name="ScheduleTest",
        headers=list(row_a.keys()),
        rows=[row_a, row_b, row_c, row_d],
        month_columns=month_columns,
        static_columns=static_columns,
    )

    contracts = parse_sheet_to_contracts(parsed)
    assert len(contracts) == 4

    contract_a = next(c for c in contracts if c["reference"] == "CTR-A")
    contract_b = next(c for c in contracts if c["reference"] == "CTR-B")
    contract_c = next(c for c in contracts if c["reference"] == "CTR-C")
    contract_d = next(c for c in contracts if c["reference"] == "CTR-D")

    # Assert row counts from parsing
    assert len(contract_a["installments"]) == 3
    assert len(contract_b["installments"]) == 3
    assert len(contract_c["installments"]) == 4

    # Assert schedule length mismatch warning for D (reference + row only, no personal values)
    assert "schedule_warning" in contract_d
    assert "CTR-D" in contract_d["schedule_warning"]
    assert "schedule length (4) differs from EMI months (3)" in contract_d["schedule_warning"]

    # Database testing in finance_test
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s, s.begin():
        await upsert_contracts(s, [contract_a, contract_b, contract_c], upload_id=1)
        await s.flush()

        # Query and assert Contract A: 3 rows, all due_amount populated
        rows_a = sorted(
            (await s.execute(
                select(Installment)
                .join(Contract, Contract.id == Installment.contract_id)
                .where(Contract.reference == "CTR-A")
            )).scalars().all(),
            key=lambda r: r.due_month,
        )
        assert len(rows_a) == 3
        assert [r.due_month for r in rows_a] == [date(2025, 3, 1), date(2025, 4, 1), date(2025, 5, 1)]
        assert rows_a[0].due_amount == Decimal("5900.00")  # first month: deduction + GST
        assert rows_a[1].due_amount == Decimal("5000.00")
        assert rows_a[2].due_amount == Decimal("5000.00")
        assert all(r.due_amount is not None for r in rows_a)

        # Query and assert Contract B: 3 rows, all due_amount populated
        rows_b = sorted(
            (await s.execute(
                select(Installment)
                .join(Contract, Contract.id == Installment.contract_id)
                .where(Contract.reference == "CTR-B")
            )).scalars().all(),
            key=lambda r: r.due_month,
        )
        assert len(rows_b) == 3
        assert [r.due_month for r in rows_b] == [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)]
        assert rows_b[0].due_amount == Decimal("3600.00")  # first month: deduction + GST
        assert rows_b[1].due_amount == Decimal("3000.00")
        assert rows_b[2].due_amount == Decimal("3000.00")
        assert all(r.due_amount is not None for r in rows_b)

        # Query and assert Contract C: 4 rows, NULL due_amount outside schedule, payment kept
        rows_c = sorted(
            (await s.execute(
                select(Installment)
                .join(Contract, Contract.id == Installment.contract_id)
                .where(Contract.reference == "CTR-C")
            )).scalars().all(),
            key=lambda r: r.due_month,
        )
        assert len(rows_c) == 4
        assert [r.due_month for r in rows_c] == [
            date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1), date(2025, 5, 1)
        ]
        # Feb 2025 is outside schedule -> due_amount must be NULL (None)
        assert rows_c[0].due_amount is None
        # C's payment is kept in Feb 2025
        assert rows_c[0].salary_amount == Decimal("4500.00")
        assert rows_c[0].received_amount == Decimal("4500.00")

        # Mar, Apr, May are inside schedule -> due_amount is populated
        assert rows_c[1].due_amount == Decimal("4500.00")  # first schedule month: 4000 + 500 GST
        assert rows_c[2].due_amount == Decimal("4000.00")
        assert rows_c[3].due_amount == Decimal("4000.00")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])