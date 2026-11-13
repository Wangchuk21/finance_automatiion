"""
Tests for the contracts list/detail/installments API.
Runs strictly against finance_test (never finance_automation).
"""

import os
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user as get_current_user_dep
from app.db.session import Base, get_session
from app.main import app
from app.models import Contract, Installment, InstallmentStatus, UserRole

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
                "receivable": 13500.0,
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
            assert alice["receivable"] == 6000.0
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

            # -------------------------------------------------------------
            # Admin update (PATCH) — installments must be untouched
            # -------------------------------------------------------------
            admin = SimpleNamespace(role=UserRole.ADMIN)
            app.dependency_overrides[get_current_user_dep] = lambda: admin

            resp = await client.patch(
                f"/api/v1/contracts/{c1_id}",
                json={
                    "customer": "  Alicia  ",
                    "cid": "CID-NEW",
                    "mobile": "17999999",
                    "item": "Phone B",
                    "brand": "Apple",
                    "region": "Central Region",
                    "cost_center": "Phuentsholing",
                    "ministry_agency": "MOF",
                    "payment_type": "External Installment",
                    "emi_months": 8,
                    "monthly_deduction": "1250.50",
                    "sales_amount": "8000.00",
                    "gst": "200.00",
                    "start_date": TWO_MONTHS_AGO.isoformat(),
                    "end_date": IN_TWO_MONTHS.isoformat(),
                },
            )
            assert resp.status_code == 200, resp.text
            updated = resp.json()
            assert updated["customer"] == "Alicia"
            assert updated["cid"] == "CID-NEW"
            assert updated["mobile"] == "17999999"
            assert updated["item"] == "Phone B"
            assert updated["brand"] == "Apple"
            assert updated["region"] == "Central Region"
            assert updated["cost_center"] == "Phuentsholing"
            assert updated["ministry_agency"] == "MOF"
            assert updated["emi_months"] == 8
            assert updated["monthly_deduction"] == 1250.5
            assert updated["sales_amount"] == 8000.0
            assert updated["gst"] == 200.0
            assert updated["start_date"] == TWO_MONTHS_AGO.isoformat()
            assert updated["end_date"] == IN_TWO_MONTHS.isoformat()
            # Collected comes from installments and is unchanged (2000).
            assert updated["collected"] == 2000.0
            # Receivable is the edited Sales + GST: 8000 + 200.
            assert updated["receivable"] == 8200.0
            # Outstanding recalculated: 8000 + 200 - 2000.
            assert updated["outstanding"] == 6200.0
            # Balance due still comes from the original installment schedule.
            assert updated["balance_due"] == 1000.0

            resp = await client.get(f"/api/v1/contracts/{c1_id}/installments")
            assert resp.status_code == 200
            schedule = resp.json()
            assert len(schedule) == 3
            assert sum(row["due_amount"] for row in schedule) == 3000.0
            assert sum(row["received_amount"] for row in schedule) == 2000.0

            # Blank text fields are stored as null/empty, not the literal "".
            resp = await client.patch(
                f"/api/v1/contracts/{c1_id}", json={"cid": "   ", "mobile": ""}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["cid"] == ""
            assert resp.json()["mobile"] == ""

            # Invalid payloads are rejected.
            resp = await client.patch(
                f"/api/v1/contracts/{c1_id}", json={"customer": "   "}
            )
            assert resp.status_code == 422

            resp = await client.patch(
                f"/api/v1/contracts/{c1_id}",
                json={
                    "start_date": IN_TWO_MONTHS.isoformat(),
                    "end_date": TWO_MONTHS_AGO.isoformat(),
                },
            )
            assert resp.status_code == 422

            resp = await client.patch(
                f"/api/v1/contracts/{c1_id}", json={"references": "nope"}
            )
            assert resp.status_code == 422

            resp = await client.patch(
                "/api/v1/contracts/999999", json={"customer": "Nobody"}
            )
            assert resp.status_code == 404

            # Non-admins are forbidden and cannot change anything.
            for role in (UserRole.FINANCE_UPLOADER, UserRole.VIEWER):
                app.dependency_overrides[get_current_user_dep] = lambda role=role: SimpleNamespace(role=role)
                resp = await client.patch(
                    f"/api/v1/contracts/{c1_id}", json={"customer": "Hacked"}
                )
                assert resp.status_code == 403

            app.dependency_overrides.pop(get_current_user_dep, None)
            resp = await client.get(f"/api/v1/contracts/{c1_id}")
            assert resp.json()["customer"] == "Alicia"
    finally:
        app.dependency_overrides.pop(get_current_user_dep, None)
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_installments_report_past_unpaid_month_as_overdue():
    """An unpaid month is overdue even if its stored status is still pending.

    This mirrors uploading October while September stayed unpaid: the row was
    stored as ``PENDING`` at import time and must be recomputed on read.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as s, s.begin():
        contract = Contract(
            reference="OVERDUE-1",
            customer="Dawa",
            emi_months=3,
            monthly_deduction=Decimal("4660.00"),
            sales_amount=Decimal("13980.00"),
            gst=Decimal("0.00"),
            start_date=TWO_MONTHS_AGO,
            end_date=THIS_MONTH,
        )
        s.add(contract)
        await s.flush()
        s.add_all(
            [
                # Past month, nothing received, but stored as PENDING.
                Installment(
                    contract_id=contract.id,
                    due_month=LAST_MONTH,
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("0.00"),
                    status=InstallmentStatus.PENDING,
                    cell_status="not_received",
                ),
                # Current month has been paid.
                Installment(
                    contract_id=contract.id,
                    due_month=THIS_MONTH,
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("4660.00"),
                    status=InstallmentStatus.PAID,
                ),
                # Partly received in a past month.
                Installment(
                    contract_id=contract.id,
                    due_month=TWO_MONTHS_AGO,
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("1000.00"),
                    status=InstallmentStatus.PARTIAL,
                ),
            ]
        )
        contract_id = contract.id

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/contracts/{contract_id}/installments")
            assert resp.status_code == 200, resp.text
            statuses = {row["due_month"]: row["status"] for row in resp.json()}

        assert statuses[LAST_MONTH.isoformat()] == "overdue"
        assert statuses[THIS_MONTH.isoformat()] == "paid"
        assert statuses[TWO_MONTHS_AGO.isoformat()] == "partial"
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_balance_due_does_not_hide_unpaid_months_behind_overpayment():
    """An overpaid month must not cancel an unpaid month's due.

    Mirrors BT250503000007: August received double, September unpaid, and the
    October payment landed on a row with no due. Balance Due used to come out
    as zero because totals were netted; it must equal the schedule's balances.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as s, s.begin():
        contract = Contract(
            reference="OVERPAID-1",
            customer="Sonam",
            emi_months=4,
            monthly_deduction=Decimal("4660.00"),
            sales_amount=Decimal("18640.00"),
            gst=Decimal("0.00"),
            start_date=date(2025, 6, 1),
            end_date=date(2026, 10, 1),
        )
        s.add(contract)
        await s.flush()
        s.add_all(
            [
                Installment(
                    contract_id=contract.id,
                    due_month=date(2025, 6, 1),
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("0.00"),
                    status=InstallmentStatus.PENDING,
                ),
                Installment(
                    contract_id=contract.id,
                    due_month=date(2025, 8, 1),
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("9320.00"),
                    status=InstallmentStatus.PAID,
                ),
                Installment(
                    contract_id=contract.id,
                    due_month=date(2026, 9, 1),
                    due_amount=Decimal("4660.00"),
                    received_amount=Decimal("0.00"),
                    status=InstallmentStatus.PENDING,
                ),
                Installment(
                    contract_id=contract.id,
                    due_month=date(2026, 10, 1),
                    due_amount=None,
                    received_amount=Decimal("4660.00"),
                    status=InstallmentStatus.PAID,
                ),
            ]
        )
        contract_id = contract.id

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/contracts/{contract_id}")
            assert resp.status_code == 200, resp.text
            detail = resp.json()
            assert detail["collected"] == 13980.0
            # June + September are unpaid; August's extra 4,660 does not offset them.
            assert detail["balance_due"] == 9320.0

            resp = await client.get("/api/v1/contracts?search=OVERPAID-1")
            assert resp.status_code == 200
            assert resp.json()["items"][0]["balance_due"] == 9320.0
            assert resp.json()["summary"]["balance_due"] == 9320.0
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
