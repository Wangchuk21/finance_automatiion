"""
Tests for temporary confirmation code (M2/M3 security).

# TEMPORARY - replace with real TOTP in M3
"""

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.uploads import get_current_user
from app.core.config import settings
from app.core.confirm import reset_confirm_attempts, verify_confirm_code
from app.core.auth import get_current_user as get_current_user_dep
from app.core.security import hash_password
from app.db.session import get_session
from app.main import app
from app.models import Contract, ContractState, User


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Reset rate limiter state before each test."""
    reset_confirm_attempts()
    yield
    reset_confirm_attempts()


@pytest.fixture
def auth_client(monkeypatch):
    """Create test client with authenticated admin user."""
    # Create mock admin user
    mock_user = User(
        id=1,
        username="admin",
        email="admin@example.com",
        full_name="Admin User",
        password_hash=hash_password("TempPass123!@#"),
        is_active=True,
        role="admin",
        must_change_password=False,
        token_version=1,
        failed_login_count=0,
        locked_until=None,
        temp_password_expires_at=None,
    )
    
    # Mock session
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    
    # Override dependencies
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user_dep] = lambda: mock_user
    
    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()


def test_1_503_when_not_dev_or_code_unset(monkeypatch, auth_client):
    """1. 503 when not dev or code unset."""
    # Sub-case A: prod environment
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "test-secret-123")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_confirm_code("test-secret-123"))
    assert exc_info.value.status_code == 503
    assert "Confirmation is not configured" in exc_info.value.detail

    # Test via API endpoint
    resp = auth_client.post("/api/v1/contracts/1/close", json={"code": "test-secret-123"})
    assert resp.status_code == 503
    assert "Confirmation is not configured" in resp.json()["detail"]

    resp = auth_client.post("/api/v1/uploads/1/confirm", json={"code": "test-secret-123"})
    assert resp.status_code == 503

    resp = auth_client.post("/api/v1/uploads/1/rollback", json={"code": "test-secret-123"})
    assert resp.status_code == 503

    # Sub-case B: dev environment but empty code
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_confirm_code("test-secret-123"))
    assert exc_info.value.status_code == 503
    assert "Confirmation is not configured" in exc_info.value.detail


def test_2_400_on_wrong_code(monkeypatch, auth_client):
    """2. 400 on wrong code."""
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "correct-secret-123")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_confirm_code("bad-code-999"))
    assert exc_info.value.status_code == 400
    assert "Invalid confirmation code" in exc_info.value.detail

    # Test via API endpoint
    resp = auth_client.post("/api/v1/contracts/1/close", json={"code": "bad-code-999"})
    assert resp.status_code == 400
    assert "Invalid confirmation code" in resp.json()["detail"]

    resp = auth_client.post("/api/v1/uploads/1/confirm", json={"code": "bad-code-999"})
    assert resp.status_code == 400
    assert "Invalid confirmation code" in resp.json()["detail"]

    resp = auth_client.post("/api/v1/uploads/1/rollback", json={"code": "bad-code-999"})
    assert resp.status_code == 400
    assert "Invalid confirmation code" in resp.json()["detail"]


def test_3_429_on_6th_wrong_attempt(monkeypatch, auth_client):
    """3. 429 on 6th wrong attempt."""
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "correct-secret-123")

    # First 5 wrong attempts raise 400
    for i in range(5):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verify_confirm_code(f"wrong-{i}"))
        assert exc_info.value.status_code == 400

    # 6th attempt must trigger 429
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_confirm_code("wrong-6"))
    assert exc_info.value.status_code == 429
    assert "Too many incorrect attempts" in exc_info.value.detail

    # Endpoint must also return 429 while locked
    resp = auth_client.post("/api/v1/contracts/1/close", json={"code": "wrong-7"})
    assert resp.status_code == 429


def test_4_200_on_correct_code(monkeypatch, auth_client):
    """4. 200 on correct code."""
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "correct-secret-123")

    # verify direct function passes without exception
    asyncio.run(verify_confirm_code("correct-secret-123"))

    # Test via API endpoint
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    test_contract = Contract(
        id=1,
        reference="REF-001",
        customer="Customer",
        state=ContractState.ACTIVE,
    )
    mock_session.get.return_value = test_contract

    app.dependency_overrides[get_session] = lambda: mock_session

    try:
        resp = auth_client.post("/api/v1/contracts/1/close", json={"code": "correct-secret-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["contract_id"] == 1
        assert data["status"] == "closed"
    finally:
        app.dependency_overrides.clear()


def test_5_audit_log_has_result_but_never_the_code(monkeypatch):
    """5. audit_log has result but NEVER the code."""
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "TEMP_CONFIRM_CODE", "super-secret-code-xyz")

    session = AsyncMock()
    added_logs = []
    session.add = MagicMock(side_effect=lambda entry: added_logs.append(entry))
    session.flush = AsyncMock()

    # Wrong attempt
    bad_code = "my-secret-attempt-code-123"
    with pytest.raises(HTTPException):
        asyncio.run(
            verify_confirm_code(
                code=bad_code,
                action="confirm_upload",
                entity_id="42",
                entity_type="upload",
                session=session,
            )
        )

    assert len(added_logs) == 1
    log1 = added_logs[0]
    assert log1.action == "confirm_upload"
    assert log1.entity_type == "upload"
    assert log1.entity_id == "42"

    payload1 = json.loads(log1.new_values)
    assert "result" in payload1
    assert payload1["result"] == "denied"
    assert "timestamp" in payload1

    # Verify submitted code never appears anywhere in log
    assert bad_code not in (log1.new_values or "")
    assert bad_code not in (log1.old_values or "")
    assert bad_code not in log1.action
    assert bad_code not in log1.entity_type
    assert bad_code not in log1.entity_id

    # Correct attempt
    good_code = "super-secret-code-xyz"
    asyncio.run(
        verify_confirm_code(
            code=good_code,
            action="close_contract",
            entity_id="100",
            entity_type="contract",
            session=session,
        )
    )

    assert len(added_logs) == 2
    log2 = added_logs[1]
    assert log2.action == "close_contract"
    assert log2.entity_type == "contract"
    assert log2.entity_id == "100"

    payload2 = json.loads(log2.new_values)
    assert "result" in payload2
    assert payload2["result"] == "ok"
    assert "timestamp" in payload2

    # Verify code never appears anywhere in log
    assert good_code not in (log2.new_values or "")
    assert good_code not in (log2.old_values or "")
    assert good_code not in log2.action
    assert good_code not in log2.entity_type
    assert good_code not in log2.entity_id