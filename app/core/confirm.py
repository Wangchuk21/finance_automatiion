"""
Temporary confirmation-code verification.

# TEMPORARY - replace with real TOTP in M3

Usage: await verify_confirm_code(code, action, entity_id, entity_type, session)
  - Works when TEMP_CONFIRM_CODE is set.
  - Raises HTTP 503 if not configured, 429 after 5 wrong attempts in 5 min,
    400 for a wrong code.
  - Writes an AuditLog row for every attempt (never stores the code itself).
"""

import hmac
import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory rate-limit store
# Deque of attempt timestamps (wrong attempts only).
# ---------------------------------------------------------------------------
_WRONG_ATTEMPTS: deque = deque()
_WINDOW = timedelta(minutes=5)
_MAX_WRONG = 5


def _prune_window() -> None:
    cutoff = datetime.now(tz=timezone.utc) - _WINDOW
    while _WRONG_ATTEMPTS and _WRONG_ATTEMPTS[0] < cutoff:
        _WRONG_ATTEMPTS.popleft()


def _is_rate_limited() -> bool:
    _prune_window()
    return len(_WRONG_ATTEMPTS) >= _MAX_WRONG


def _record_wrong_attempt() -> None:
    _prune_window()
    _WRONG_ATTEMPTS.append(datetime.now(tz=timezone.utc))


def reset_confirm_attempts() -> None:
    """Reset rate limiter state (useful for tests)."""
    _WRONG_ATTEMPTS.clear()


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

async def _write_audit(
    session,
    action: str,
    result: str,
    entity_type: str = "upload",
    entity_id: str = "0",
) -> None:
    """Write one AuditLog row. Never stores the submitted code."""
    if session is None:
        return
    try:
        from app.models import AuditLog

        entry = AuditLog(
            action=action,
            entity_type=entity_type or "system",
            entity_id=str(entity_id or "0"),
            new_values=json.dumps({
                "result": result,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }),
        )
        session.add(entry)
        await session.flush()
    except Exception:
        logger.warning("Could not flush audit log entry", exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# TEMPORARY - replace with real TOTP in M3
# ---------------------------------------------------------------------------

async def verify_confirm_code(
    code: str,
    action: str = "confirm",
    entity_id: str = "0",
    entity_type: str = "upload",
    session=None,
) -> None:
    """
    # TEMPORARY - replace with real TOTP in M3

    Verify the temporary confirmation code.

    Raises:
        HTTP 503  – APP_ENV != "dev" or TEMP_CONFIRM_CODE unset
        HTTP 429  – after 5 wrong attempts in 5 minutes (triggered on 6th attempt)
        HTTP 400  – wrong code (no hints, never echo code)
    Writes one AuditLog entry per call (action + result ok/denied, no code).
    """
    from app.core.config import settings

    # Guard: active whenever TEMP_CONFIRM_CODE is configured
    if not settings.TEMP_CONFIRM_CODE:
        await _write_audit(session, action, "denied", entity_type, entity_id)
        raise HTTPException(
            status_code=503,
            detail="Confirmation is not configured",
        )

    # Rate-limit check
    if _is_rate_limited():
        await _write_audit(session, action, "denied", entity_type, entity_id)
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Try again in 5 minutes.",
        )

    # Constant-time comparison
    ok = bool(code) and hmac.compare_digest(
        code.strip().encode(),
        settings.TEMP_CONFIRM_CODE.strip().encode(),
    )

    if not ok:
        _record_wrong_attempt()
        await _write_audit(session, action, "denied", entity_type, entity_id)
        raise HTTPException(
            status_code=400,
            detail="Invalid confirmation code",
        )

    # Success
    _WRONG_ATTEMPTS.clear()
    await _write_audit(session, action, "ok", entity_type, entity_id)
