2b: PASS - amounts '5,110.00' and '1,22,640' in month cells and Sales Amt / Monthly Deduction parse correctly to 5110.00 and 122640.0
2b-fix: PASS - amounts parse to Decimal quantized to 0.01 (ROUND_HALF_UP), sums computed via Decimal, whole numbers isolated from text fields, and DB money columns verified Numeric.
2c: PASS - blank mobile and invalid mobile produce warnings only (no errors), and warning messages omit the phone number.
2d2e: PASS - warnings added for month cell sum vs EMI Received and Sales Amt - (received - GST) vs Overall Outstanding; first-month due = Monthly Deduction + GST confirmed.
db-write: PASS - service.py rewrote _upsert_installments (external+salary→received, due_amount explicit/nullable, cell_status stored, sales_amount on contract); reshape emits all months; 3-contract DB test passes against finance_test (49 passed).
asof-fix: PASS - frontend uses type=date (YYYY-MM-DD, max=today); schema converts YYYY-MM to month-end and rejects future with 422; DB errors return 'Could not save the upload record' without SQL; 3 new tests pass (51 total).
note-cell: PASS - warning omits cell value (shows ref/row/col only); reshape stores cell_status='note' with amount=None for unparseable text; test confirms 'John 500' absent from all messages (52 passed).
