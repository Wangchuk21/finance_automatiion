"""
Tests for dashboard date filter and KPI aggregations.
Runs strictly against finance_test (never finance_automation).
"""

import os
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.dashboard import resolve_date_bounds
from app.db.session import Base, get_session
from app.main import app
from app.models import Contract, Installment, InstallmentStatus

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test",
)

# Strict safety verification
assert "finance_test" in TEST_DB_URL, f"Expected finance_test in URL, got {TEST_DB_URL}"
assert "finance_automation" not in TEST_DB_URL, "MUST NEVER RUN AGAINST finance_automation"


def test_date_bounds_presets():
    """Verify Bhutan fiscal year and relative date presets."""
    ref_oct = date(2026, 10, 25)
    ref_mar = date(2026, 3, 15)

    # All
    assert resolve_date_bounds("all") == (None, None)

    # This month
    assert resolve_date_bounds("this_month", ref_date=ref_oct) == (date(2026, 10, 1), date(2026, 10, 1))

    # Last month
    assert resolve_date_bounds("last_month", ref_date=ref_oct) == (date(2026, 9, 1), date(2026, 9, 1))
    assert resolve_date_bounds("last_month", ref_date=date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 1))

    # Last 3 months
    assert resolve_date_bounds("last_3_months", ref_date=ref_oct) == (date(2026, 8, 1), date(2026, 10, 1))

    # Bhutan FY: 1 July to 30 June
    # In Oct 2026, this_fy is 2026-07 to 2027-06
    assert resolve_date_bounds("this_fy", ref_date=ref_oct) == (date(2026, 7, 1), date(2027, 6, 1))
    # In Mar 2026, this_fy is 2025-07 to 2026-06
    assert resolve_date_bounds("this_fy", ref_date=ref_mar) == (date(2025, 7, 1), date(2026, 6, 1))

    # Last FY
    assert resolve_date_bounds("last_fy", ref_date=ref_oct) == (date(2025, 7, 1), date(2026, 6, 1))
    assert resolve_date_bounds("last_fy", ref_date=ref_mar) == (date(2024, 7, 1), date(2025, 6, 1))

    # Custom
    assert resolve_date_bounds("custom", "2026-07", "2026-09") == (date(2026, 7, 1), date(2026, 9, 1))


@pytest.mark.asyncio
async def test_dashboard_filters_e2e():
    """
    Test dashboard with 3 contracts across 3 months against finance_test.
    Assert Due, Collected, Overdue for:
      1. 'all'
      2. one month ('2026-08')
      3. a 3-month range ('2026-07' to '2026-09')
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed 3 synthetic contracts
    async with async_session() as s, s.begin():
        c1 = Contract(
            reference="SYNTH-C1",
            region="Thimphu",
            payment_type="Salary",
            monthly_deduction=Decimal("1000.00"),
            sales_amount=Decimal("12000.00"),
        )
        c2 = Contract(
            reference="SYNTH-C2",
            region="Phuentsholing",
            payment_type="External",
            monthly_deduction=Decimal("2000.00"),
            sales_amount=Decimal("24000.00"),
        )
        c3 = Contract(
            reference="SYNTH-C3",
            region="Paro",
            payment_type="External",
            monthly_deduction=Decimal("3000.00"),
            sales_amount=Decimal("36000.00"),
        )

        s.add_all([c1, c2, c3])
        await s.flush()

        m1 = date(2026, 7, 1)
        m2 = date(2026, 8, 1)
        m3 = date(2026, 9, 1)

        installments = [
            # Contract 1 (Salary / Thimphu)
            Installment(contract_id=c1.id, due_month=m1, due_amount=Decimal("1000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c1.id, due_month=m2, due_amount=Decimal("1000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c1.id, due_month=m3, due_amount=Decimal("1000.00"), received_amount=Decimal("500.00"), status=InstallmentStatus.PARTIAL),

            # Contract 2 (External / Phuentsholing)
            Installment(contract_id=c2.id, due_month=m1, due_amount=Decimal("2000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PARTIAL),
            Installment(contract_id=c2.id, due_month=m2, due_amount=Decimal("2000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.OVERDUE),
            Installment(contract_id=c2.id, due_month=m3, due_amount=Decimal("2000.00"), received_amount=Decimal("2000.00"), status=InstallmentStatus.PAID),

            # Contract 3 (External / Paro)
            Installment(contract_id=c3.id, due_month=m1, due_amount=Decimal("3000.00"), received_amount=Decimal("3000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c3.id, due_month=m2, due_amount=Decimal("3000.00"), received_amount=Decimal("1500.00"), status=InstallmentStatus.PARTIAL),
            Installment(contract_id=c3.id, due_month=m3, due_amount=Decimal("3000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.OVERDUE),
        ]

        s.add_all(installments)

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # -------------------------------------------------------------
            # 1. Assert Due, Collected, Overdue for "all"
            # -------------------------------------------------------------
            resp_all = await client.get("/api/v1/dashboard/?preset=all")
            assert resp_all.status_code == 200
            data_all = resp_all.json()
            summary_all = data_all["summary"]

            assert summary_all["due"] == 18000.0, f"Expected 18000 due, got {summary_all['due']}"
            assert summary_all["collected"] == 10000.0, f"Expected 10000 collected, got {summary_all['collected']}"
            assert summary_all["overdue"] == 8000.0, f"Expected 8000 overdue, got {summary_all['overdue']}"
            assert summary_all["outstanding"] == 8000.0
            assert summary_all["total_outstanding_all_time"] == 8000.0

            # Verify KPI cards structure
            kpis_all = {k["title"]: k for k in data_all["kpis"]}
            assert "Due" in kpis_all
            assert "Collected" in kpis_all
            assert "Overdue" in kpis_all
            assert "Outstanding in period" in kpis_all
            assert kpis_all["Due"]["rawValue"] == 18000.0
            assert kpis_all["Collected"]["rawValue"] == 10000.0
            assert kpis_all["Overdue"]["rawValue"] == 8000.0
            assert kpis_all["Outstanding in period"]["rawValue"] == 8000.0

            # -------------------------------------------------------------
            # 2. Assert Due, Collected, Overdue for one month (2026-08)
            # -------------------------------------------------------------
            resp_one = await client.get("/api/v1/dashboard/?preset=custom&from=2026-08&to=2026-08")
            assert resp_one.status_code == 200
            data_one = resp_one.json()
            summary_one = data_one["summary"]

            assert summary_one["due"] == 6000.0, f"Expected 6000 due, got {summary_one['due']}"
            assert summary_one["collected"] == 2500.0, f"Expected 2500 collected, got {summary_one['collected']}"
            assert summary_one["overdue"] == 3500.0, f"Expected 3500 overdue, got {summary_one['overdue']}"
            assert summary_one["outstanding"] == 3500.0
            # Total outstanding all time remains 8000.0
            assert summary_one["total_outstanding_all_time"] == 8000.0

            kpis_one = {k["title"]: k for k in data_one["kpis"]}
            assert kpis_one["Due"]["rawValue"] == 6000.0
            assert kpis_one["Collected"]["rawValue"] == 2500.0
            assert kpis_one["Overdue"]["rawValue"] == 3500.0
            assert kpis_one["Outstanding in period"]["rawValue"] == 3500.0
            # Secondary figure: Total outstanding (all time)
            assert kpis_one["Outstanding in period"]["secondaryValue"] is not None
            assert "8,000" in kpis_one["Outstanding in period"]["secondaryValue"] or "8000" in kpis_one["Outstanding in period"]["secondaryValue"]

            # -------------------------------------------------------------
            # 3. Assert Due, Collected, Overdue for 3-month range (2026-07 to 2026-09)
            # -------------------------------------------------------------
            resp_three = await client.get("/api/v1/dashboard/?preset=custom&from=2026-07&to=2026-09")
            assert resp_three.status_code == 200
            data_three = resp_three.json()
            summary_three = data_three["summary"]

            assert summary_three["due"] == 18000.0, f"Expected 18000 due, got {summary_three['due']}"
            assert summary_three["collected"] == 10000.0, f"Expected 10000 collected, got {summary_three['collected']}"
            assert summary_three["overdue"] == 8000.0, f"Expected 8000 overdue, got {summary_three['overdue']}"
            assert summary_three["outstanding"] == 8000.0
            assert summary_three["total_outstanding_all_time"] == 8000.0

            # -------------------------------------------------------------
            # 4. Optional region & channel filters
            # -------------------------------------------------------------
            resp_reg = await client.get("/api/v1/dashboard/?preset=all&region=Thimphu")
            assert resp_reg.status_code == 200
            summary_reg = resp_reg.json()["summary"]
            assert summary_reg["due"] == 3000.0
            assert summary_reg["collected"] == 2500.0
            assert summary_reg["overdue"] == 500.0

            resp_ch = await client.get("/api/v1/dashboard/?preset=all&channel=external")
            assert resp_ch.status_code == 200
            summary_ch = resp_ch.json()["summary"]
            assert summary_ch["due"] == 15000.0
            assert summary_ch["collected"] == 7500.0
            assert summary_ch["overdue"] == 7500.0

            # -------------------------------------------------------------
            # 5. Charts & Export with filters
            # -------------------------------------------------------------
            assert len(data_three["regions"]) > 0
            assert len(data_three["trend"]) > 0

            resp_export = await client.get("/api/v1/dashboard/export?preset=custom&from=2026-07&to=2026-09")
            assert resp_export.status_code == 200
            assert "text/csv" in resp_export.headers["content-type"]
            csv_text = resp_export.text
            assert "Reference,Region,Payment Type,Due Month" in csv_text
            assert "SYNTH-C1" in csv_text
            assert "SYNTH-C2" in csv_text
            assert "SYNTH-C3" in csv_text

    finally:
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
