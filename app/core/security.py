"""Security utilities: password hashing, JWT tokens, rate limiting, CSRF."""

import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from passlib.context import CryptContext
from passlib.hash import argon2

from app.core.config import settings


# ---------------------------------------------------------------------------
# Password hashing (Argon2)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type=argon2.type)


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash (timing-safe)."""
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def verify_password_dummy(password: str) -> bool:
    """Dummy verification for unknown usernames (timing-safe)."""
    # Hash a dummy password to match timing - use a valid argon2 hash
    try:
        _ = pwd_context.verify(password, "$argon2id$v=19$m=65536,t=3,p=4$aaaaaaaaaaaaaaaaaaaaaa$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------

class PasswordPolicy:
    MIN_LENGTH = 12
    MAX_LENGTH = 128
    HISTORY_LIMIT = 4  # Current + last 3

    @staticmethod
    def validate(
        new_password: str,
        confirm_password: str,
        current_password_hash: Optional[str] = None,
        temp_password: Optional[str] = None,
        password_history: Optional[list] = None,
    ) -> Tuple[bool, str]:
        """
        Validate password against policy.
        Returns (is_valid, error_message).
        """
        if not new_password:
            return False, "Password is required"

        if len(new_password) < PasswordPolicy.MIN_LENGTH:
            return False, f"Password must be at least {PasswordPolicy.MIN_LENGTH} characters"

        if len(new_password) > PasswordPolicy.MAX_LENGTH:
            return False, f"Password must not exceed {PasswordPolicy.MAX_LENGTH} characters"

        if new_password != confirm_password:
            return False, "Passwords do not match"

        # Check against temporary password
        if temp_password and new_password == temp_password:
            return False, "New password must differ from the temporary password"

        # Check against current password hash
        if current_password_hash and verify_password(new_password, current_password_hash):
            return False, "New password must differ from the current password"

        # Check against password history
        if password_history:
            for old_hash in password_history:
                if verify_password(new_password, old_hash):
                    return False, "Password was recently used. Choose a different one."

        # Complexity: at least one upper, lower, digit, special
        has_upper = any(c.isupper() for c in new_password)
        has_lower = any(c.islower() for c in new_password)
        has_digit = any(c.isdigit() for c in new_password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in new_password)

        if not (has_upper and has_lower and has_digit and has_special):
            return False, (
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one digit, and one special character"
            )

        return True, ""


# ---------------------------------------------------------------------------
# JWT Token handling
# ---------------------------------------------------------------------------

import jwt
from jwt import PyJWTError


def create_access_token(
    user_id: int,
    username: str,
    role: str,
    token_version: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a short-lived access token (JWT)."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "token_version": token_version,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: int,
    username: str,
    token_version: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a refresh token (JWT)."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=2))
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "token_version": token_version,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except PyJWTError:
        return None


def decode_token_unsafe(token: str) -> Optional[dict]:
    """Decode token without signature verification (for debugging)."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-process)
# ---------------------------------------------------------------------------

class RateLimiter:
    """In-memory rate limiter with sliding window."""

    def __init__(self):
        self._attempts: defaultdict[str, deque] = defaultdict(deque)
        self._window = timedelta(minutes=15)
        self._max_attempts = 5

    def _get_key(self, identifier: str, ip: str) -> str:
        return f"{identifier}:{ip}"

    def _prune(self, key: str) -> None:
        cutoff = datetime.now(timezone.utc) - self._window
        while self._attempts[key] and self._attempts[key][0] < cutoff:
            self._attempts[key].popleft()

    def record_attempt(self, identifier: str, ip: str) -> None:
        """Record a failed login attempt."""
        key = self._get_key(identifier, ip)
        self._prune(key)
        self._attempts[key].append(datetime.now(timezone.utc))

    def is_locked(self, identifier: str, ip: str) -> bool:
        """Check if the identifier/IP is locked out."""
        key = self._get_key(identifier, ip)
        self._prune(key)
        return len(self._attempts[key]) >= self._max_attempts

    def get_remaining_attempts(self, identifier: str, ip: str) -> int:
        key = self._get_key(identifier, ip)
        self._prune(key)
        return max(0, self._max_attempts - len(self._attempts[key]))

    def clear_attempts(self, identifier: str, ip: str) -> None:
        """Clear attempts on successful login."""
        key = self._get_key(identifier, ip)
        if key in self._attempts:
            self._attempts[key].clear()

    def get_lockout_remaining(self, identifier: str, ip: str) -> Optional[int]:
        """Get seconds until lockout expires."""
        key = self._get_key(identifier, ip)
        if not self._attempts[key]:
            return None
        oldest = self._attempts[key][0]
        expiry = oldest + self._window
        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds())
        return max(0, remaining)


rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# CSRF Protection (Double-submit cookie pattern)
# ---------------------------------------------------------------------------

CSRF_TOKEN_KEY = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "csrf_token"


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(cookie_token: Optional[str], header_token: Optional[str]) -> bool:
    """Verify CSRF token from cookie matches header (timing-safe)."""
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token.encode(), header_token.encode())


# ---------------------------------------------------------------------------
# Temporary password generation
# ---------------------------------------------------------------------------

def generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Audit logging helper
# ---------------------------------------------------------------------------

async def write_auth_audit(
    session,
    action: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Write an authentication audit log entry."""
    try:
        from app.models import AuditLog

        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type="user",
            entity_id=str(user_id) if user_id else "unknown",
            new_values=json.dumps({
                "details": details or {},
                "ip": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(entry)
        await session.flush()
    except Exception:
        # Don't fail the request if audit logging fails
        pass