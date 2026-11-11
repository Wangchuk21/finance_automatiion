"""
Tests for the contracts list/detail/installments API.
Runs strictly against finance_test (never finance_automation).
"""

import os
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_session
from app.main import app
from app.models import Contract, Installment, InstallmentStatus

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test",
)

assert "finance_test" in TEST_DB_URL, f"Expected finance_test in URL, got {TEST_DB_URL}"
assert "finance_automation" not in TEST_DB_URL, "MUST NEVER RUN AGAINST finance_automation"


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _month_end(value: date) -> date:
    return _add_months(value, 1) - timedelta(days=1)


TODAY = date.today()
THIS_MONTH = _month_start(TODAY)
LAST_MONTH = _add_months(THIS_MONTH, -1)
TWO_MONTHS_AGO = _add_months(THIS_MONTH, -2)
IN_TWO_MONTHS = _add_months(THIS_MONTH, 2)


@pytest.mark.asyncio
async def test_contracts_api_e2e():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as s, s.begin():
        c1 = Contract(
            reference="CON-1",
            customer="Alice",
            cid="CID1",
            mobile="17123456",
            item="Phone A",
            brand="Samsung",
            region="Western Region",
            cost_center="Thimphu",
            ministry_agency="MOESD",
            payment_type="External Installment",
            emi_months=6,
            monthly_deduction=Decimal("1000.00"),
            sales_amount=Decimal("6000.00"),
            gst=Decimal("0.00"),
            start_date=TWO_MONTHS_AGO,
            end_date=_month_end(THIS_MONTH),
        )
        c2 = Contract(
            reference="CON-2",
            customer="Bob",
            region="Western Region",
            cost_center="Wangdue",
            payment_type="Employee Installment",
            emi_months=3,
            monthly_deduction=Decimal("500.00"),
            sales_amount=Decimal("1500.00"),
            gst=Decimal("0.00"),
            start_date=TWO_MONTHS_AGO,
            end_date=_month_end(THIS_MONTH),
        )
        c3 = Contract(
            reference="CON-3",
            customer="Carol",
            region="Eastern Region",
            cost_center="Trashigang",
            payment_type="External Installment",
            emi_months=3,
            monthly_deduction=Decimal("2000.00"),
            sales_amount=Decimal("6000.00"),
            gst=Decimal("0.00"),
            start_date=THIS_MONTH,
            end_date=_month_end(IN_TWO_MONTHS),
        )
        s.add_all([c1, c2, c3])
        await s.flush()

        s.add_all(
            [
                Installment(
                    contract_id=c1.id,
                    due_month=TWO_MONTHS_AGO,
                    due_amount=Decimal("1000.00"),
                    received_amount=Decimal("1000.00"),
                    status=InstallmentStatus.PAID,
                ),
                Installment(
                    contract_id=c1.id,
                    due_month=LAST_MONTH,
                    due_amount=Decimal("1000.00"),
                    received_amount=Decimal("1000.00"),
                    status=InstallmentStatus.PAID,
                ),
                Installment(
                    contract_id=c1.id,
                    due_month=THIS_MONTH,
                    due_amount=Decimal("1000.00"),
                    received_amount=Decimal("0.00"),
                    status=InstallmentStatus.PENDING,
                ),
                Installment(
                    contract_id=c2.id,
                    due_month=TWO_MONTHS_AGO,
                    due_amount=Decimal("500.00"),
                    received_amount=Decimal("500.00"),
                    status=InstallmentStatus.PAID,
                ),
                Installment(
                    contract_id=c2.id,
                    due_month=LAST_MONTH,
                    due_amount=Decimal("500.00"),
                    received_amount=Decimal("500.00"),
                    status=InstallmentStatus.PAID,
                ),
                Installment(
                    contract_id=c2.id,
                    due_month=THIS_MONTH,
                    due_amount=Decimal("500.00"),
                    received_amount=Decimal("500.00"),
                    status=InstallmentStatus.PAID,
                ),
            ]
        )

    c1_id = c1.id
    c3_id = c3.id

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # -------------------------------------------------------------
            # List + summary
            # -------------------------------------------------------------
            resp = await client.get("/api/v1/contracts")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 3
            assert body["summary"] == {
                "contracts": 3,
                "monthly_deduction": 3500.0,
                "outstanding": 10000.0,
                "collected": 3500.0,
                "balance_due": 1000.0,
            }
            # Default sort: outstanding desc
            assert [item["reference"] for item in body["items"]] == [
                "CON-3",
                "CON-1",
                "CON-2",
            ]

            alice = next(item for item in body["items"] if item["reference"] == "CON-1")
            assert alice["customer"] == "Alice"
            assert alice["months_left"] == 4
            assert alice["outstanding"] == 4000.0
            assert alice["collected"] == 2000.0
            assert alice["balance_due"] == 1000.0
            assert alice["total_due"] == 3000.0

            bob = next(item for item in body["items"] if item["reference"] == "CON-2")
            assert bob["months_left"] == 0
            assert bob["outstanding"] == 0.0
            assert bob["balance_due"] == 0.0

            # -------------------------------------------------------------
            # Filters
            # -------------------------------------------------------------
            resp = await client.get("/api/v1/contracts?search=alice")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-1"]

            resp = await client.get("/api/v1/contracts?search=17123456")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-1"]

            resp = await client.get("/api/v1/contracts?channel=internal")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-2"]

            resp = await client.get("/api/v1/contracts?channel=external")
            assert resp.json()["total"] == 2

            resp = await client.get("/api/v1/contracts?region=Western%20Region")
            assert resp.json()["total"] == 2

            resp = await client.get("/api/v1/contracts?cost_center=Thimphu")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-1"]

            resp = await client.get("/api/v1/contracts?brand=Samsung")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-1"]

            resp = await client.get("/api/v1/contracts?brand=iPhone")
            assert resp.json()["total"] == 0

            resp = await client.get("/api/v1/contracts?emi_left=zero")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-2"]

            resp = await client.get("/api/v1/contracts?emi_left=3-6")
            assert resp.json()["total"] == 2

            resp = await client.get("/api/v1/contracts?emi_left=7%2B")
            assert resp.json()["total"] == 0

            resp = await client.get("/api/v1/contracts?overdue=true")
            assert [item["reference"] for item in resp.json()["items"]] == ["CON-1"]

            resp = await client.get("/api/v1/contracts?ending=this_month")
            assert resp.json()["total"] == 2

            resp = await client.get("/api/v1/contracts?ending=next_3_months")
            assert resp.json()["total"] == 3

            resp = await client.get("/api/v1/contracts?state=missing_review")
            assert resp.json()["total"] == 0

            resp = await client.get("/api/v1/contracts?state=invalid")
            assert resp.status_code == 400

            resp = await client.get("/api/v1/contracts?emi_left=bogus")
            assert resp.status_code == 400

            # -------------------------------------------------------------
            # Sorting + pagination
            # -------------------------------------------------------------
            resp = await client.get("/api/v1/contracts?sort=outstanding&order=asc")
            assert [item["reference"] for item in resp.json()["items"]] == [
                "CON-2",
                "CON-1",
                "CON-3",
            ]

            resp = await client.get("/api/v1/contracts?sort=emi_left&order=desc")
            assert [item["reference"] for item in resp.json()["items"]] == [
                "CON-1",
                "CON-3",
                "CON-2",
            ]

            resp = await client.get("/api/v1/contracts?skip=1&limit=1")
            assert resp.json()["total"] == 3
            assert len(resp.json()["items"]) == 1
            assert resp.json()["items"][0]["reference"] == "CON-1"

            # -------------------------------------------------------------
            # Facets
            # -------------------------------------------------------------
            resp = await client.get("/api/v1/contracts/facets")
            assert resp.status_code == 200
            facets = resp.json()
            assert facets["regions"] == ["Eastern Region", "Western Region"]
            assert {"region": "Western Region", "name": "Thimphu"} in facets["cost_centers"]
            assert {"region": "Western Region", "name": "Wangdue"} in facets["cost_centers"]
            assert facets["brands"] == ["Samsung"]

            # -------------------------------------------------------------
            # Detail + installments
            # -------------------------------------------------------------
            resp = await client.get(f"/api/v1/contracts/{c1_id}")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["reference"] == "CON-1"
            assert detail["months_left"] == 4
            assert detail["outstanding"] == 4000.0
            assert detail["collected"] == 2000.0
            assert detail["balance_due"] == 1000.0

            resp = await client.get(f"/api/v1/contracts/{c1_id}/installments")
            assert resp.status_code == 200
            schedule = resp.json()
            assert len(schedule) == 3
            assert schedule[0]["due_month"] == TWO_MONTHS_AGO.isoformat()
            assert schedule[-1]["balance"] == 1000.0
            assert schedule[-1]["status"] == "pending"

            resp = await client.get(f"/api/v1/contracts/{c3_id}/installments")
            assert resp.status_code == 200
            assert resp.json() == []

            resp = await client.get("/api/v1/contracts/999999")
            assert resp.status_code == 404

            resp = await client.get("/api/v1/contracts/999999/installments")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
