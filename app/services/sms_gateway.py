"""Client for the Bhutan Telecom SMS gateway (BTL Mail Studio).

The gateway exposes a small JSON API:

    POST /api/login       {"email": ..., "password": ...}   -> token
    POST /api/send-sms    {"to": ..., "from": ..., "message": ...}

Authentication uses a bearer token obtained from ``/api/login``. The token is
cached in-process and refreshed automatically when it expires or rejects.

The service is deliberately fail-soft: callers get an ``SmsSendResult`` instead
of an exception, so one bad number never aborts a reminder batch.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Token keys used by common Laravel auth packages. The exact key returned by
# BTL Mail Studio is not documented, so accept any of the usual spellings.
_TOKEN_KEYS = ("token", "access_token", "api_token", "plainTextToken", "plain_text_token")


class SmsGatewayError(Exception):
    """Raised when the gateway is misconfigured or unreachable."""


@dataclass
class SmsSendResult:
    """Outcome of a single SMS dispatch."""

    ok: bool
    to: str
    message_id: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


def normalize_phone(raw: Any, country_code: Optional[str] = None) -> Optional[str]:
    """
    Normalise a Bhutanese mobile number to the gateway's ``975XXXXXXXX`` form.

    Accepts 8-digit local numbers, ``+975``/``00975`` prefixes, and numbers
    with spaces or dashes. Returns ``None`` when the value cannot be a valid
    Bhutanese mobile number (8 digits after the country code).
    """
    cc = country_code or settings.SMS_COUNTRY_CODE
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 8:
        return f"{cc}{digits}"

    if digits.startswith(cc) and len(digits) == len(cc) + 8:
        return digits

    return None


def extract_token(payload: Any) -> Optional[str]:
    """Pull a bearer token out of common login response shapes."""
    if isinstance(payload, str):
        return payload.strip() or None

    if isinstance(payload, dict):
        for key in _TOKEN_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        # Sanctum-style {"data": {...}} or {"data": "token"}
        data = payload.get("data")
        if data is not None:
            token = extract_token(data)
            if token:
                return token

    return None


def _join_api_url(base_url: str, path: str) -> str:
    """Build an API URL from a base that may or may not already end in /api."""
    base = base_url.rstrip("/")
    if base.endswith("/api"):
        return f"{base}{path}"
    return f"{base}/api{path}"


def _extract_message_id(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("message_id", "id", "sms_id", "sid"):
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value)
        data = payload.get("data")
        if isinstance(data, (dict, str, int)):
            return _extract_message_id(data)
    if isinstance(payload, (str, int)) and str(payload).strip():
        return str(payload)
    return None


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return text[:300] or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        errors = payload.get("errors")
        if isinstance(errors, dict) and errors:
            details = "; ".join(
                f"{field}: {', '.join(str(v) for v in vals)}"
                for field, vals in errors.items()
                if isinstance(vals, (list, tuple))
            )
            if details:
                return f"{message} ({details})" if message else details
        if message:
            return str(message)
    return str(payload)[:300]


class SmsGatewayClient:
    """Thin async client with token caching and one automatic re-login."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        sender_id: Optional[str] = None,
        verify_tls: Optional[bool] = None,
        timeout: Optional[float] = None,
        token_ttl: Optional[int] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = (base_url or settings.SMS_GATEWAY_URL or "").rstrip("/")
        self.email = email if email is not None else settings.SMS_GATEWAY_EMAIL
        self.password = password if password is not None else settings.SMS_GATEWAY_PASSWORD
        self.sender_id = sender_id or settings.SMS_SENDER_ID
        self.verify_tls = settings.SMS_VERIFY_TLS if verify_tls is None else verify_tls
        self.timeout = timeout or settings.SMS_TIMEOUT_SECONDS
        self.token_ttl = token_ttl or settings.SMS_TOKEN_TTL_SECONDS
        self._transport = transport

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._login_lock = asyncio.Lock()

    # -- configuration -----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.base_url and self.email and self.password)

    # -- HTTP plumbing -----------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=self.verify_tls,
            headers={"Accept": "application/json"},
            transport=self._transport,
        )

    async def _login(self, client: httpx.AsyncClient) -> str:
        if not self.is_configured():
            raise SmsGatewayError(
                "SMS gateway is not configured (SMS_GATEWAY_URL, "
                "SMS_GATEWAY_EMAIL and SMS_GATEWAY_PASSWORD are required)."
            )

        response = await client.post(
            _join_api_url(self.base_url, "/login"),
            json={"email": self.email, "password": self.password},
        )
        if response.status_code >= 400:
            raise SmsGatewayError(
                f"Gateway login failed ({response.status_code}): {_extract_error(response)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SmsGatewayError("Gateway login returned a non-JSON response") from exc

        token = extract_token(payload)
        if not token:
            raise SmsGatewayError("Gateway login response did not contain a token")

        self._token = token
        self._token_expires_at = time.monotonic() + self.token_ttl
        logger.info("Authenticated with SMS gateway as %s", self.email)
        return token

    async def _get_token(self, client: httpx.AsyncClient, force: bool = False) -> str:
        if not force and self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._login_lock:
            # Another coroutine may have refreshed the token while we waited.
            if not force and self._token and time.monotonic() < self._token_expires_at:
                return self._token
            return await self._login(client)

    # -- public API --------------------------------------------------------

    async def send_sms(
        self,
        to: str,
        message: str,
        sender_id: Optional[str] = None,
    ) -> SmsSendResult:
        """Send one SMS. Never raises for transport/provider errors."""
        phone = normalize_phone(to)
        if not phone:
            return SmsSendResult(
                ok=False,
                to=str(to or ""),
                error="Invalid Bhutanese mobile number",
            )

        body = {
            "to": phone,
            "from": sender_id or self.sender_id,
            "message": message,
        }

        try:
            async with self._client() as client:
                token = await self._get_token(client)
                response = await self._post_sms(client, token, body)

                if response.status_code in (401, 403, 419):
                    logger.info("SMS gateway token rejected; re-authenticating")
                    token = await self._get_token(client, force=True)
                    response = await self._post_sms(client, token, body)

                if response.status_code >= 400:
                    return SmsSendResult(
                        ok=False,
                        to=phone,
                        status_code=response.status_code,
                        error=_extract_error(response),
                    )

                try:
                    payload: Any = response.json()
                except ValueError:
                    payload = None

                return SmsSendResult(
                    ok=True,
                    to=phone,
                    status_code=response.status_code,
                    message_id=_extract_message_id(payload),
                )

        except SmsGatewayError as exc:
            logger.error("SMS gateway error for %s: %s", phone, exc)
            return SmsSendResult(ok=False, to=phone, error=str(exc))
        except httpx.HTTPError as exc:
            logger.error("SMS gateway request failed for %s: %s", phone, exc)
            return SmsSendResult(ok=False, to=phone, error=f"Gateway unreachable: {exc}")
        except Exception as exc:  # defensive: never break a reminder batch
            logger.exception("Unexpected SMS gateway error for %s", phone)
            return SmsSendResult(ok=False, to=phone, error=str(exc))

    async def _post_sms(
        self,
        client: httpx.AsyncClient,
        token: str,
        body: dict,
    ) -> httpx.Response:
        return await client.post(
            _join_api_url(self.base_url, "/send-sms"),
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def send_many(
        self,
        messages: Sequence[tuple[str, str]],
        concurrency: Optional[int] = None,
    ) -> list[SmsSendResult]:
        """Send several ``(to, message)`` pairs with bounded concurrency."""
        limit = max(1, concurrency or settings.SMS_MAX_CONCURRENCY)
        semaphore = asyncio.Semaphore(limit)

        async def _one(to: str, message: str) -> SmsSendResult:
            async with semaphore:
                return await self.send_sms(to, message)

        return list(await asyncio.gather(*(_one(to, msg) for to, msg in messages)))


_default_client: Optional[SmsGatewayClient] = None


def get_sms_client() -> SmsGatewayClient:
    """Return the process-wide gateway client (built from settings)."""
    global _default_client
    if _default_client is None:
        _default_client = SmsGatewayClient()
    return _default_client


def reset_sms_client() -> None:
    """Drop the cached client. Intended for tests and config reloads."""
    global _default_client
    _default_client = None
