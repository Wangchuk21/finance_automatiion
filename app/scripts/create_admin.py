"""Create initial admin user with temporary password."""

import asyncio
import secrets
import string
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

from app.core.config import settings
from app.core.security import argon2
from app.db.session import async_session_maker, init_db
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type="id")


def generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_admin_user() -> None:
    """Create the initial admin user."""
    await init_db()

    async with async_session_maker() as session:
        # Check if admin already exists
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "admin"))
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin user already exists")
            return

        # Generate temporary password
        temp_password = generate_temp_password()
        temp_password_hash = pwd_context.hash(temp_password)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

        # Create admin user
        admin = User(
            username="admin",
            email="admin@finance-automation.local",
            full_name="System Administrator",
            password_hash=temp_password_hash,
            is_active=True,
            role=UserRole.ADMIN.value,
            must_change_password=True,
            temp_password_expires_at=expires_at,
            token_version=1,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        print("=" * 60)
        print("INITIAL ADMIN USER CREATED")
        print("=" * 60)
        print(f"Username: admin")
        print(f"Email: admin@finance-automation.local")
        print(f"Temporary Password: {temp_password}")
        print(f"Expires: {expires_at.isoformat()}")
        print(f"Role: {UserRole.ADMIN.value}")
        print("=" * 60)
        print("IMPORTANT: Save this password. It will not be shown again.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(create_admin_user())