"""Tests for notifications, staff in-app alerts, and customer SMS payment reminders."""

import os
from datetime import date, datetime
from decimal import Decimal
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user, require_not_must_change_password, require_role
from app.db.session import Base, get_session
from app.main import app
from app.models import Contract, Installment, InstallmentStatus, Notification, NotificationTemplate, User

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_test",
)

assert "finance_test" in TEST_DB_URL, f"Expected finance_test in URL, got {TEST_DB_URL}"
assert "finance_automation" not in TEST_DB_URL, "MUST NEVER RUN AGAINST finance_automation"

_mock_admin = User(
    id=1,
    username="admin",
    email="admin@example.com",
    role="admin",
    is_active=True,
    must_change_password=False,
)


@pytest.fixture
def override_auth():
    app.dependency_overrides[require_not_must_change_password] = lambda: _mock_admin
    # require_role returns a dependency function
    for role_dep in [
        require_role("admin", "finance_uploader"),
        require_role("admin", "finance_uploader", "finance_viewer"),
    ]:
        pass
    yield
    app.dependency_overrides.pop(require_not_must_change_password, None)


@pytest.mark.asyncio
async def test_notifications_full_flow():
    """Test templates, in-app alerts, candidate generation, and sending SMS reminders."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed contracts and overdue installments
    async with async_session() as s, s.begin():
        c1 = Contract(
            reference="BT25010001",
            customer="Karma Wangchuk",
            cid="11501001111",
            mobile="17123456",
            region="Western Region",
            cost_center="Thimphu",
            item="Samsung Galaxy S24",
            brand="Samsung",
            payment_type="External Installment",
            monthly_deduction=Decimal("2000.00"),
            sales_amount=Decimal("24000.00"),
            gst=Decimal("240.00"),
        )
        c2 = Contract(
            reference="BT25010002",
            customer="Dechen Dema",
            cid="11502002222",
            mobile="77987654",
            region="Western Region",
            cost_center="Paro",
            item="iPhone 16 Pro",
            brand="iPhone",
            payment_type="External Installment",
            monthly_deduction=Decimal("5000.00"),
            sales_amount=Decimal("60000.00"),
            gst=Decimal("600.00"),
        )
        c3_no_mobile = Contract(
            reference="BT25010003",
            customer="Sonam Dorji",
            cid="11503003333",
            mobile="",  # No mobile
            region="Eastern Region",
            cost_center="Trashigang",
            item="Dell Laptop",
            brand="Dell",
            payment_type="Salary Deduction",
            monthly_deduction=Decimal("3000.00"),
            sales_amount=Decimal("36000.00"),
            gst=Decimal("360.00"),
        )
        s.add_all([c1, c2, c3_no_mobile])
        await s.flush()

        # Add overdue installments (due in the past, e.g. 2026-07-01 and 2026-08-01)
        m1 = date(2026, 7, 1)
        m2 = date(2026, 8, 1)

        s.add_all([
            # c1: Due 4000, paid 2000 => balance due = 2000
            Installment(contract_id=c1.id, due_month=m1, due_amount=Decimal("2000.00"), received_amount=Decimal("2000.00"), status=InstallmentStatus.PAID),
            Installment(contract_id=c1.id, due_month=m2, due_amount=Decimal("2000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING),

            # c2: Due 10000, paid 0 => balance due = 10000
            Installment(contract_id=c2.id, due_month=m1, due_amount=Decimal("5000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING),
            Installment(contract_id=c2.id, due_month=m2, due_amount=Decimal("5000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING),

            # c3: Due 3000, paid 0 => balance due = 3000
            Installment(contract_id=c3_no_mobile.id, due_month=m1, due_amount=Decimal("3000.00"), received_amount=Decimal("0.00"), status=InstallmentStatus.PENDING),
        ])

    async def override_get_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _mock_admin
    app.dependency_overrides[require_not_must_change_password] = lambda: _mock_admin

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Test Templates
            resp_templates = await client.get("/api/v1/notifications/templates")
            assert resp_templates.status_code == 200
            templates = resp_templates.json()
            assert len(templates) >= 3
            assert any(t["channel"] == "sms" for t in templates)

            # 2. Test In-App Notifications
            resp_in_app = await client.get("/api/v1/notifications/in-app")
            assert resp_in_app.status_code == 200
            in_app_data = resp_in_app.json()
            assert "items" in in_app_data
            assert "unread_count" in in_app_data
            assert in_app_data["unread_count"] >= 1  # Due to overdue alert

            # 3. Test Mark In-App Read
            resp_read = await client.post(
                "/api/v1/notifications/in-app/mark-read",
                json={"notification_ids": None},
            )
            assert resp_read.status_code == 200

            # 4. Test Reminder Candidates (Preview)
            resp_candidates = await client.get("/api/v1/notifications/reminders/candidates?aging_bucket=all")
            assert resp_candidates.status_code == 200
            cand_data = resp_candidates.json()
            assert cand_data["total_eligible"] == 3
            assert cand_data["with_mobile_count"] == 2
            assert cand_data["missing_mobile_count"] == 1
            assert cand_data["total_balance_due"] == 15000.0

            candidates = cand_data["candidates"]
            c2_cand = next(c for c in candidates if c["reference"] == "BT25010002")
            assert c2_cand["customer"] == "Dechen Dema"
            assert c2_cand["mobile"] == "77987654"
            assert c2_cand["balance_due"] == 10000.0
            assert "Nu. 10,000.00" in c2_cand["rendered_message"]
            assert "iPhone 16 Pro" in c2_cand["rendered_message"]

            # Filter by region
            resp_par = await client.get("/api/v1/notifications/reminders/candidates?region=Paro")
            assert resp_par.status_code == 200
            assert resp_par.json()["total_eligible"] == 1
            assert resp_par.json()["candidates"][0]["reference"] == "BT25010002"

            # 5. Test Send Reminders
            c1_id = candidates[0]["contract_id"]
            c2_id = candidates[1]["contract_id"]
            c3_id = candidates[2]["contract_id"]

            resp_send = await client.post(
                "/api/v1/notifications/reminders/send",
                json={
                    "contract_ids": [c1_id, c2_id, c3_id],
                },
            )
            assert resp_send.status_code == 200
            send_res = resp_send.json()
            assert send_res["total_targeted"] == 3
            assert send_res["sent_count"] == 2
            assert send_res["skipped_no_phone"] == 1

            # 6. Test Notification History
            resp_history = await client.get("/api/v1/notifications/history")
            assert resp_history.status_code == 200
            history_data = resp_history.json()
            assert history_data["total"] >= 3
            items = history_data["items"]
            sent_items = [i for i in items if i["status"] == "sent"]
            failed_items = [i for i in items if i["status"] == "failed"]
            assert len(sent_items) == 2
            assert len(failed_items) == 1

    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_not_must_change_password, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
