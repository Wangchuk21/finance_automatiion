"""Send a single test SMS through the BTL Mail Studio gateway.

Usage:
    python -m app.scripts.test_sms --to 17123456 --message "Test from Finance Automation"

This verifies configuration (credentials, TLS, network reachability) without
touching the database or sending a customer batch.
"""

import argparse
import asyncio
import sys

from app.core.config import settings
from app.services.sms_gateway import SmsGatewayClient, normalize_phone


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test SMS via BTL Mail Studio")
    parser.add_argument("--to", required=True, help="Recipient number (8-digit local or +975...)")
    parser.add_argument(
        "--message",
        default="Test message from Finance Automation.",
        help="Message text",
    )
    parser.add_argument("--sender", default=settings.SMS_SENDER_ID, help="Sender ID")
    args = parser.parse_args()

    phone = normalize_phone(args.to)
    if not phone:
        print(f"Invalid Bhutanese mobile number: {args.to!r}", file=sys.stderr)
        return 2

    client = SmsGatewayClient()

    print("Configuration")
    print(f"  gateway     : {client.base_url or '(unset)'}")
    print(f"  account     : {client.email or '(unset)'}")
    print(f"  password    : {'set' if client.password else '(unset)'}")
    print(f"  sender id   : {args.sender}")
    print(f"  verify TLS  : {client.verify_tls}")
    print(f"  SMS_ENABLED : {settings.SMS_ENABLED}")
    print()

    if not client.is_configured():
        print(
            "Gateway is not configured. Set SMS_GATEWAY_URL, SMS_GATEWAY_EMAIL and "
            "SMS_GATEWAY_PASSWORD in .env.",
            file=sys.stderr,
        )
        return 2

    print(f"Sending to {phone} ...")
    result = await client.send_sms(args.to, args.message, sender_id=args.sender)

    if result.ok:
        print(f"OK ({result.status_code}) message_id={result.message_id or 'n/a'}")
        return 0

    print(f"FAILED ({result.status_code or 'no response'}): {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
