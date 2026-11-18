"""
Tests for the global as-of month cutoff.

Runs strictly against finance_test (never finance_automation).
"""

import os
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.dashboard import resolve_bounds_with_as_of
from app.core.as_of import as_of_label, parse_as_of_month
from app.core.auth import require_not_must_change_password
from app.db.session import Base, get_session
from app.main import app
from app.models import (
    Contract,
    Installment,
    InstallmentStatus,
    Upload,
    UploadStatus,
    User,
    UserRole,
)

_mock_user = User(
    id=1,
    username="asofadmin",
    email="asofadmin@example.com",
    role=UserRole.ADMIN.value,
    is_active=True,
    must_change_password=False,
)

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test",
)

assert "finance_test" in TEST_DB_URL, f"Expected finance_test in URL, got {TEST_DB_URL}"
assert "finance_automation" not in TEST_DB_URL, "MUST NEVER RUN AGAINST finance_automation"


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_parse_as_of_month():
    assert parse_as_of_month("2026-08") == date(2026, 8, 1)
    assert parse_as_of_month("2026-08-31") == date(2026, 8, 1)
    assert parse_as_of_month(" 2026-08 ") == date(2026, 8, 1)
    assert parse_as_of_month("2026-13") is None
    assert parse_as_of_month("not-a-month") is None
    assert parse_as_of_month("") is None
    assert parse_as_of_month(None) is None


def test_as_of_label():
    assert as_of_label(date(2026, 8, 1)) == "Aug 2026"
    assert as_of_label(None) == "Latest"


def test_resolve_bounds_with_as_of():
    # No as-of leaves the requested bounds untouched.
    assert resolve_bounds_with_as_of("all", None, None, None) == (None, None, None)

    # "all" + as-of becomes an upper bound only.
    assert resolve_bounds_with_as_of("all", None, None, "2026-08") == (
        None,
        date(2026, 8, 1),
        date(2026, 8, 1),
    )

    # An explicit range is clamped to the as-of month.
    assert resolve_bounds_with_as_of("custom", "2026-07", "2026-09", "2026-08") == (
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 8, 1),
    )

    # A range entirely after the as-of month collapses onto it.
    assert resolve_bounds_with_as_of("custom", "2026-09", "2026-10", "2026-08") == (
        date(2026, 8, 1),
        date(2026, 8, 1),
        date(2026, 8, 1),
    )


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_as_of_cutoff_across_dashboard_reports_and_contracts():
    """The same cutoff must cap figures on Dashboard, Reports and Contracts."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    jul = date(2026, 7, 1)
    aug = date(2026, 8, 1)
    sep = date(2026, 9, 1)

    async with async_session() as s, s.begin():
        user = User(
            username="asofadmin",
            email="asofadmin@example.com",
            password_hash="unused",
            role=UserRole.ADMIN.value,
            must_change_password=False,
        )
        s.add(user)
        await s.flush()

        c1 = Contract(
            reference="ASOF-C1",
            region="Thimphu",
            cost_center="CC-A",
            brand="BrandA",
            payment_type="Salary",
            monthly_deduction=Decimal("1000.00"),
            sales_amount=Decimal("12000.00"),
            gst=Decimal("120.00"),
        )
        c2 = Contract(
            reference="ASOF-C2",
            region="Paro",
            cost_center="CC-B",
            brand="BrandB",
            payment_type="External",
            monthly_deduction=Decimal("2000.00"),
            sales_amount=Decimal("24000.00"),
            gst=Decimal("240.00"),
        )
        s.add_all([c1, c2])
        await s.flush()

        s.add_all(
            [
                # C1: Jul PAID, Aug PARTIAL, Sep UNPAID
                Installment(contract_id=c1.id, due_month=jul, due_amount=Decimal("1000"), received_amount=Decimal("1000"), status=InstallmentStatus.PAID),
                Installment(contract_id=c1.id, due_month=aug, due_amount=Decimal("1000"), received_amount=Decimal("500"), status=InstallmentStatus.PARTIAL),
                Installment(contract_id=c1.id, due_month=sep, due_amount=Decimal("1000"), received_amount=Decimal("0"), status=InstallmentStatus.PENDING),
                # C2: Jul UNPAID, Aug PAID, Sep PARTIAL
                Installment(contract_id=c2.id, due_month=jul, due_amount=Decimal("2000"), received_amount=Decimal("0"), status=InstallmentStatus.PENDING),
                Installment(contract_id=c2.id, due_month=aug, due_amount=Decimal("2000"), received_amount=Decimal("2000"), status=InstallmentStatus.PAID),
                Installment(contract_id=c2.id, due_month=sep, due_amount=Decimal("2000"), received_amount=Decimal("1000"), status=InstallmentStatus.PARTIAL),
            ]
        )
        s.add_all(
            [
                Upload(file_name="jul.xlsx", checksum="c1", uploaded_by=user.id, as_of_date=jul, status=UploadStatus.CONFIRMED),
                Upload(file_name="aug.xlsx", checksum="c2", uploaded_by=user.id, as_of_date=aug, status=UploadStatus.CONFIRMED),
                Upload(file_name="sep.xlsx", checksum="c3", uploaded_by=user.id, as_of_date=sep, status=UploadStatus.CONFIRMED),
                Upload(file_name="pending.xlsx", checksum="c4", uploaded_by=user.id, as_of_date=date(2026, 6, 1), status=UploadStatus.PENDING),
            ]
        )

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_not_must_change_password] = lambda: _mock_user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # -- available as-of dates: distinct confirmed uploads, newest first
            resp = await client.get("/api/v1/dashboard/as-of-dates")
            assert resp.status_code == 200
            assert resp.json()["dates"] == ["2026-09-01", "2026-08-01", "2026-07-01"]

            # -- dashboard as of Aug: only Jul + Aug instalments
            resp = await client.get("/api/v1/dashboard/?preset=all&as_of=2026-08")
            assert resp.status_code == 200
            data = resp.json()
            summary = data["summary"]
            # Due: C1(1000+1000) + C2(2000+2000) = 6000
            assert summary["due"] == 6000.0
            # Collected: C1(1000+500) + C2(0+2000) = 3500
            assert summary["collected"] == 3500.0
            # Balance due: C1(0+500) + C2(2000+0) = 2500
            assert summary["balance_due"] == 2500.0
            # Outstanding: C1(12120-1500) + C2(24240-2000) = 32860
            assert summary["outstanding"] == 32860.0
            assert data["selectedAsOf"] == "2026-08-01"
            assert data["asOfDate"] == "2026-08-01"

            # -- all time (no cutoff) includes Sep instalments
            resp = await client.get("/api/v1/dashboard/?preset=all")
            all_summary = resp.json()["summary"]
            assert all_summary["due"] == 9000.0
            assert all_summary["collected"] == 4500.0
            assert all_summary["balance_due"] == 4500.0
            assert all_summary["outstanding"] == 31860.0
            assert resp.json()["selectedAsOf"] is None

            # -- selecting the latest upload month matches all-time figures
            resp = await client.get("/api/v1/dashboard/?preset=all&as_of=2026-09")
            latest_summary = resp.json()["summary"]
            assert latest_summary["due"] == all_summary["due"]
            assert latest_summary["collected"] == all_summary["collected"]
            assert latest_summary["balance_due"] == all_summary["balance_due"]
            assert latest_summary["outstanding"] == all_summary["outstanding"]

            # -- dues report must not contain September rows
            resp = await client.get("/api/v1/dashboard/reports/dues?as_of=2026-08&limit=10000")
            assert resp.status_code == 200
            dues = resp.json()["items"]
            assert dues
            assert all(item["due_month"] <= "2026-08-01" for item in dues)
            assert sum(item["due_amount"] for item in dues) == 6000.0

            # -- by-region and by-brand summaries are capped too
            resp = await client.get("/api/v1/dashboard/reports/by-region?as_of=2026-08")
            assert resp.status_code == 200
            region_items = resp.json()["items"]
            assert sum(i["collected"] for i in region_items) == 3500.0
            resp = await client.get("/api/v1/dashboard/reports/by-brand?as_of=2026-08")
            assert sum(i["balance_due"] for i in resp.json()["items"]) == 2500.0

            # -- overdue report excludes September-only balances
            resp = await client.get("/api/v1/dashboard/reports/overdue?as_of=2026-08&limit=10000")
            assert resp.status_code == 200
            assert resp.json()["total"] >= 1
            assert all(item["overdue_amount"] > 0 for item in resp.json()["items"])

            # -- contracts list summary is capped
            resp = await client.get("/api/v1/contracts?as_of=2026-08&limit=10000")
            assert resp.status_code == 200
            summary = resp.json()["summary"]
            assert summary["collected"] == 3500.0
            assert summary["balance_due"] == 2500.0

            # -- contract detail / installments honour the same cutoff
            resp = await client.get("/api/v1/contracts/1?as_of=2026-08")
            assert resp.status_code == 200
            assert resp.json()["collected"] == 1500.0
            resp = await client.get("/api/v1/contracts/1/installments?as_of=2026-08")
            assert resp.status_code == 200
            assert [row["due_month"] for row in resp.json()] == ["2026-07-01", "2026-08-01"]
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_not_must_change_password, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
