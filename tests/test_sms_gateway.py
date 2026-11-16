"""Unit tests for the BTL Mail Studio SMS gateway client (no network, no DB)."""

import json

import httpx

from app.services.sms_gateway import (
    SmsGatewayClient,
    extract_token,
    normalize_phone,
)


class Recorder:
    """Mock transport that records requests and returns scripted responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")
        return self.responses.pop(0)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def make_client(recorder: Recorder) -> SmsGatewayClient:
    return SmsGatewayClient(
        base_url="https://sms.example.test",
        email="finance@example.bt",
        password="secret",
        sender_id="BTL-EMI",
        verify_tls=False,
        transport=recorder.transport,
    )


def test_normalize_phone():
    assert normalize_phone("17123456") == "97517123456"
    assert normalize_phone("+975 17 123 456") == "97517123456"
    assert normalize_phone("00975-17123456") == "97517123456"
    assert normalize_phone("97517123456") == "97517123456"
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("12345") is None
    assert normalize_phone("9751712345678") is None


def test_extract_token_shapes():
    assert extract_token({"token": "abc"}) == "abc"
    assert extract_token({"access_token": "abc"}) == "abc"
    assert extract_token({"data": {"token": "abc"}}) == "abc"
    assert extract_token({"data": "abc"}) == "abc"
    assert extract_token("abc") == "abc"
    assert extract_token({"message": "nope"}) is None


async def test_login_then_send_and_cache_token():
    recorder = Recorder(
        [
            httpx.Response(200, json={"token": "tok-1"}),
            httpx.Response(200, json={"message_id": "msg-1"}),
            httpx.Response(200, json={"message_id": "msg-2"}),
        ]
    )
    client = make_client(recorder)

    first = await client.send_sms("17123456", "Hello")
    second = await client.send_sms("+97577987654", "World")

    assert first.ok and first.message_id == "msg-1" and first.to == "97517123456"
    assert second.ok and second.message_id == "msg-2"

    # One login for both sends (token cached).
    assert [r.url.path for r in recorder.requests] == [
        "/api/login",
        "/api/send-sms",
        "/api/send-sms",
    ]

    login_body = json.loads(recorder.requests[0].content)
    assert login_body == {"email": "finance@example.bt", "password": "secret"}

    send_body = json.loads(recorder.requests[1].content)
    assert send_body == {"to": "97517123456", "from": "BTL-EMI", "message": "Hello"}
    assert recorder.requests[1].headers["Authorization"] == "Bearer tok-1"


async def test_relogin_on_401():
    recorder = Recorder(
        [
            httpx.Response(200, json={"access_token": "tok-old"}),
            httpx.Response(401, json={"message": "Unauthenticated."}),
            httpx.Response(200, json={"access_token": "tok-new"}),
            httpx.Response(200, json={"id": 99}),
        ]
    )
    client = make_client(recorder)

    result = await client.send_sms("17123456", "Hello")

    assert result.ok and result.message_id == "99"
    assert [r.url.path for r in recorder.requests] == [
        "/api/login",
        "/api/send-sms",
        "/api/login",
        "/api/send-sms",
    ]
    assert recorder.requests[3].headers["Authorization"] == "Bearer tok-new"


async def test_provider_error_is_returned_not_raised():
    recorder = Recorder(
        [
            httpx.Response(200, json={"token": "tok"}),
            httpx.Response(
                422,
                json={
                    "message": "The given data was invalid.",
                    "errors": {"to": ["The to field is required."]},
                },
            ),
        ]
    )
    client = make_client(recorder)

    result = await client.send_sms("17123456", "Hello")

    assert result.ok is False
    assert result.status_code == 422
    assert "The given data was invalid." in result.error
    assert "to: The to field is required." in result.error


async def test_login_failure_reported():
    recorder = Recorder(
        [httpx.Response(422, json={"message": "The provided credentials are incorrect."})]
    )
    client = make_client(recorder)

    result = await client.send_sms("17123456", "Hello")

    assert result.ok is False
    assert "Gateway login failed (422)" in result.error
    assert "credentials are incorrect" in result.error


async def test_invalid_number_skips_http():
    recorder = Recorder([])
    client = make_client(recorder)

    result = await client.send_sms("123", "Hello")

    assert result.ok is False
    assert "Invalid Bhutanese mobile number" in result.error
    assert recorder.requests == []


async def test_connection_error_is_returned():
    async def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = SmsGatewayClient(
        base_url="https://sms.example.test",
        email="finance@example.bt",
        password="secret",
        transport=httpx.MockTransport(boom),
    )

    result = await client.send_sms("17123456", "Hello")

    assert result.ok is False
    assert "Gateway unreachable" in result.error
