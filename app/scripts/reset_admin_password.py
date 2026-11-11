"""Reset a user's password (e.g. lockout / forgotten password recovery).

Usage:
    python -m app.scripts.reset_admin_password                 # reset 'admin'
    python -m app.scripts.reset_admin_password --username bob
    python -m app.scripts.reset_admin_password --password 'MyNewPass123!'

If --password is omitted, a secure temporary password is generated and printed.
The account is unlocked, must_change_password is set, and existing tokens are
invalidated (token_version is bumped).
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import generate_temp_password, hash_password
from app.db.session import async_session_maker, close_db
from app.models import User


async def reset_password(username: str, new_password: str | None) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None:
            print(f"ERROR: no user found with username '{username}'")
            return

        temp_password = new_password or generate_temp_password()
        now = datetime.now(timezone.utc)

        # Keep the old hash in history so it can't be reused immediately.
        user.add_password_to_history(user.password_hash)

        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        user.password_changed_at = None
        user.temp_password_expires_at = now + timedelta(hours=48)
        user.failed_login_count = 0
        user.locked_until = None
        user.token_version = (user.token_version or 1) + 1

        await session.commit()

        print("=" * 60)
        print("PASSWORD RESET")
        print("=" * 60)
        print(f"Username: {user.username}")
        print(f"Password: {temp_password}")
        print(f"Expires:  {user.temp_password_expires_at.isoformat()}")
        print("You will be asked to change it after logging in.")
        print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a user's password.")
    parser.add_argument("--username", default="admin", help="username to reset (default: admin)")
    parser.add_argument("--password", default=None, help="explicit new password (default: generate)")
    args = parser.parse_args()

    async def run() -> None:
        try:
            await reset_password(args.username, args.password)
        finally:
            await close_db()

    asyncio.run(run())


if __name__ == "__main__":
    main()
