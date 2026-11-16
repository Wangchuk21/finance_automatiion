"""Shared test configuration.

Tests must never send real SMS or email, regardless of what the developer's
local ``.env`` contains. This autouse fixture forces notification channels into
simulation mode for every test.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_external_notifications(monkeypatch):
    monkeypatch.setattr(settings, "SMS_ENABLED", False)
    # A non-default password makes send_email() treat SMTP as unconfigured.
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "changeme")
