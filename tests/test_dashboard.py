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
from app.core.auth import require_not_must_change_password
from app.db.session import Base, get_session
from app.main import app
from app.models import Contract, Installment, InstallmentStatus, User

_mock_user = User(
    id=1,
    username="testadmin",
    email="testadmin@example.com",
    role="admin",
    is_active=True,
    must_change_password=False,
)

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
            gst=Decimal("120.00"),
        )
        c2 = Contract(
            reference="SYNTH-C2",
            region="Phuentsholing",
            payment_type="External",
            monthly_deduction=Decimal("2000.00"),
            sales_amount=Decimal("24000.00"),
            gst=Decimal("240.00"),
        )
        c3 = Contract(
            reference="SYNTH-C3",
            region="Paro",
            payment_type="External",
            monthly_deduction=Decimal("3000.00"),
            sales_amount=Decimal("36000.00"),
            gst=Decimal("360.00"),
        )

        s.add_all([c1, c2, c3])
        await s.flush()

        m1 = date(2026, 7, 1)
        m2 = date(2026, 8, 1)
        m3 = date(2026, 9, 1)

        installments = [
            # Contract 1 (Salary / Thimphu): 1000/month, sales=12000, gst=120
            Installment(contract_id=c1.id, due_month=m1, due_amount=Decimal("1000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c1.id, due_month=m2, due_amount=Decimal("1000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PAID),
            # m3: explicitly marked not_received in sheet -> Balance Due
            Installment(contract_id=c1.id, due_month=m3, due_amount=Decimal("1000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING, cell_status="not_received"),

            # Contract 2 (External / Phuentsholing): 2000/month, sales=24000, gst=240
            Installment(contract_id=c2.id, due_month=m1, due_amount=Decimal("2000.00"), received_amount=Decimal("1000.00"), status=InstallmentStatus.PARTIAL),
            # m2: explicitly marked not_received -> Balance Due
            Installment(contract_id=c2.id, due_month=m2, due_amount=Decimal("2000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING, cell_status="not_received"),
            Installment(contract_id=c2.id, due_month=m3, due_amount=Decimal("2000.00"), received_amount=Decimal("2000.00"), status=InstallmentStatus.PAID),

            # Contract 3 (External / Paro): 3000/month, sales=36000, gst=360
            Installment(contract_id=c3.id, due_month=m1, due_amount=Decimal("3000.00"), received_amount=Decimal("3000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c3.id, due_month=m2, due_amount=Decimal("3000.00"), received_amount=Decimal("1500.00"), status=InstallmentStatus.PARTIAL),
            # m3: explicitly marked not_received -> Balance Due
            Installment(contract_id=c3.id, due_month=m3, due_amount=Decimal("3000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING, cell_status="not_received"),
        ]

        s.add_all(installments)

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_not_must_change_password] = lambda: _mock_user

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

            # Totals (all 3 contracts, all 3 months):
            # Due = 18000
            # Collected: C1(1000+1000+0)+C2(1000+0+2000)+C3(3000+1500+0) = 2000+3000+4500 = 9500
            # Balance Due (Excel formula: sum per contract of max(0, due - rec)):
            #   C1(3000-2000=1000) + C2(6000-3000=3000) + C3(9000-4500=4500) = 8500
            # Overall Outstanding = (12000+120-2000) + (24000+240-3000) + (36000+360-4500)
            #   = 10120 + 21240 + 31860 = 63220
            assert summary_all["due"] == 18000.0, f"Expected 18000 due, got {summary_all['due']}"
            assert summary_all["collected"] == 9500.0, f"Expected 9500 collected, got {summary_all['collected']}"
            assert summary_all["balance_due"] == 8500.0, f"Expected 8500 balance_due, got {summary_all['balance_due']}"
            assert summary_all["outstanding"] == 63220.0, f"Expected 63220 outstanding, got {summary_all['outstanding']}"
            assert summary_all["total_outstanding_all_time"] == 63220.0

            # Verify KPI cards structure (Due removed, Balance Due is the primary unpaid metric)
            kpis_all = {k["title"]: k for k in data_all["kpis"]}
            assert "Due" not in kpis_all
            assert "Collected" in kpis_all
            assert "Balance Due" in kpis_all
            assert "Overall Outstanding" in kpis_all
            assert kpis_all["Collected"]["rawValue"] == 9500.0
            assert kpis_all["Balance Due"]["rawValue"] == 8500.0
            assert kpis_all["Overall Outstanding"]["rawValue"] == 63220.0

            # -------------------------------------------------------------
            # 2. One month (2026-08)
            # Due: C1(1000)+C2(2000)+C3(3000) = 6000
            # Collected: C1(1000)+C2(0)+C3(1500) = 2500
            # Balance Due in period: C1(1000-1000=0) + C2(2000-0=2000) + C3(3000-1500=1500) = 3500
            # Overall Outstanding (contract-level, not date-filtered): same 63220
            # -------------------------------------------------------------
            resp_one = await client.get("/api/v1/dashboard/?preset=custom&from=2026-08&to=2026-08")
            assert resp_one.status_code == 200
            data_one = resp_one.json()
            summary_one = data_one["summary"]

            assert summary_one["due"] == 6000.0, f"Expected 6000 due, got {summary_one['due']}"
            assert summary_one["collected"] == 2500.0, f"Expected 2500 collected, got {summary_one['collected']}"
            assert summary_one["balance_due"] == 3500.0, f"Expected 3500 balance_due, got {summary_one['balance_due']}"
            # Outstanding is contract-level (all time), not filtered by date
            assert summary_one["total_outstanding_all_time"] == 63220.0

            kpis_one = {k["title"]: k for k in data_one["kpis"]}
            assert "Due" not in kpis_one
            assert kpis_one["Collected"]["rawValue"] == 2500.0
            assert kpis_one["Balance Due"]["rawValue"] == 3500.0
            # Secondary figure: Total outstanding (all time)
            assert kpis_one["Overall Outstanding"]["secondaryValue"] is not None

            # -------------------------------------------------------------
            # 3. 3-month range (2026-07 to 2026-09) — same as "all" for this dataset
            # -------------------------------------------------------------
            resp_three = await client.get("/api/v1/dashboard/?preset=custom&from=2026-07&to=2026-09")
            assert resp_three.status_code == 200
            data_three = resp_three.json()
            summary_three = data_three["summary"]

            assert summary_three["due"] == 18000.0
            assert summary_three["collected"] == 9500.0
            assert summary_three["balance_due"] == 8500.0
            assert summary_three["total_outstanding_all_time"] == 63220.0

            # -------------------------------------------------------------
            # 4. Region & channel filters (filter balance_due by region/channel)
            # -------------------------------------------------------------
            resp_reg = await client.get("/api/v1/dashboard/?preset=all&region=Thimphu")
            assert resp_reg.status_code == 200
            summary_reg = resp_reg.json()["summary"]
            assert summary_reg["due"] == 3000.0
            # C1: received = 1000+1000+0 = 2000
            assert summary_reg["collected"] == 2000.0
            # Balance Due for Thimphu: C1 due(3000) - rec(2000) = 1000
            assert summary_reg["balance_due"] == 1000.0

            resp_ch = await client.get("/api/v1/dashboard/?preset=all&channel=external")
            assert resp_ch.status_code == 200
            summary_ch = resp_ch.json()["summary"]
            assert summary_ch["due"] == 15000.0
            # C2: 1000+0+2000=3000, C3: 3000+1500+0=4500 -> total 7500
            assert summary_ch["collected"] == 7500.0
            # Balance Due for external: C2(6000-3000=3000) + C3(9000-4500=4500) = 7500
            assert summary_ch["balance_due"] == 7500.0

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


@pytest.mark.asyncio
async def test_cost_centers_by_region():
    """Cost-centre drill-down groups by region and computes per-CC totals."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as s, s.begin():
        c1 = Contract(
            reference="CC-WR-1", region="Western Region", cost_center="Thimphu",
            payment_type="External", monthly_deduction=Decimal("1000"),
            sales_amount=Decimal("8000"), gst=Decimal("0"), emi_months=10,
            customer="Karma Dorji", cid="11501001234", mobile="17123456",
            item="Dell Laptop", brand="Dell", ministry_agency="MOESD",
            start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        )
        c2 = Contract(
            reference="CC-WR-2", region="Western Region", cost_center="Wangdue",
            payment_type="External", monthly_deduction=Decimal("1000"),
            sales_amount=Decimal("5000"), gst=Decimal("0"),
            customer="Sonam Choden", cid="11501005678", mobile="17654321",
            item="HP Printer", ministry_agency="BTL",
            start_date=date(2026, 2, 1), end_date=date(2026, 12, 1),
        )
        c3 = Contract(
            reference="CC-ER-1", region="Eastern Region", cost_center="Trashigang",
            payment_type="External", monthly_deduction=Decimal("1000"),
            sales_amount=Decimal("9000"), gst=Decimal("0"),
        )
        s.add_all([c1, c2, c3])
        await s.flush()

        m = date(2026, 8, 1)
        s.add_all([
            Installment(contract_id=c1.id, due_month=m, due_amount=Decimal("5000"),
                        received_amount=Decimal("3000"), status=InstallmentStatus.PARTIAL),
            Installment(contract_id=c2.id, due_month=m, due_amount=Decimal("5000"),
                        received_amount=Decimal("5000"), status=InstallmentStatus.PAID),
            Installment(contract_id=c3.id, due_month=m, due_amount=Decimal("3000"),
                        received_amount=Decimal("0"), status=InstallmentStatus.PENDING),
        ])

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_not_must_change_password] = lambda: _mock_user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/dashboard/cost-centers?preset=all&region=Western%20Region"
            )
            assert resp.status_code == 200
            rows = resp.json()
            assert [r["cost_center"] for r in rows] == ["Thimphu", "Wangdue"]
            assert rows[0] == {
                "cost_center": "Thimphu",
                "contracts": 1,
                "receivable": 5000.0,
                "collected": 3000.0,
                "balance_due": 2000.0,
            }
            assert rows[1] == {
                "cost_center": "Wangdue",
                "contracts": 1,
                "receivable": 0.0,
                "collected": 5000.0,
                "balance_due": 0.0,
            }

            resp_all = await client.get("/api/v1/dashboard/cost-centers?preset=all")
            assert resp_all.status_code == 200
            assert {r["cost_center"] for r in resp_all.json()} == {
                "Thimphu", "Wangdue", "Trashigang"
            }

            # Individual customers/contracts under a cost center
            resp_contracts = await client.get(
                "/api/v1/dashboard/cost-centers/contracts"
                "?preset=all&region=Western%20Region&cost_center=Thimphu"
            )
            assert resp_contracts.status_code == 200
            contracts = resp_contracts.json()
            assert len(contracts) == 1
            c = contracts[0]
            assert c["reference"] == "CC-WR-1"
            assert c["customer"] == "Karma Dorji"
            assert c["cid"] == "11501001234"
            assert c["mobile"] == "17123456"
            assert c["item"] == "Dell Laptop"
            assert c["ministry_agency"] == "MOESD"
            assert c["cost_center"] == "Thimphu"
            assert c["status"] == "active"
            assert c["start_date"] == "2026-01-01"
            assert c["received"] == 3000.0
            assert c["outstanding"] == 5000.0
            assert c["months_left"] == 5
            assert c["collected"] == 3000.0
            assert c["balance_due"] == 2000.0

            resp_paid = await client.get(
                "/api/v1/dashboard/cost-centers/contracts"
                "?preset=all&region=Western%20Region&cost_center=Wangdue"
            )
            assert resp_paid.status_code == 200
            assert resp_paid.json()[0]["months_left"] == 0

            # Period filter only affects collected/balance, not all-time outstanding
            resp_period = await client.get(
                "/api/v1/dashboard/cost-centers/contracts"
                "?preset=custom&from=2026-09&to=2026-09"
                "&region=Western%20Region&cost_center=Thimphu"
            )
            assert resp_period.status_code == 200
            p = resp_period.json()[0]
            assert p["outstanding"] == 5000.0
            assert p["collected"] == 0.0
            assert p["balance_due"] == 0.0

            # Region must match
            resp_wrong = await client.get(
                "/api/v1/dashboard/cost-centers/contracts"
                "?preset=all&region=Eastern%20Region&cost_center=Thimphu"
            )
            assert resp_wrong.status_code == 200
            assert resp_wrong.json() == []
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
