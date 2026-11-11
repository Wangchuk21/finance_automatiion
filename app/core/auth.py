"""Authentication middleware and dependencies for FastAPI."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token, write_auth_audit
from app.db.session import get_session
from app.models import User, UserRole

# Cookie names
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

# HTTP Bearer for Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)


class AuthError(Exception):
    """Custom auth error with status code."""

    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def get_current_user_from_token(
    token: str,
    session: AsyncSession,
) -> Optional[User]:
    """Validate token and return user if valid."""
    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    token_version = payload.get("token_version")

    if not user_id:
        return None

    user = await session.get(User, int(user_id))
    if not user:
        return None

    if not user.is_active:
        return None

    # Check token version (invalidated on password change, logout, etc.)
    if user.token_version != token_version:
        return None

    return user


async def get_current_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Get current authenticated user from access token cookie.
    Raises 401 if not authenticated.
    """
    # Try cookie first
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)

    # Fallback to Authorization header (for Swagger UI)
    if not access_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header[7:]

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_current_user_from_token(access_token, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not access_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header[7:]

    if not access_token:
        return None

    return await get_current_user_from_token(access_token, session)


def require_auth(user: User = Depends(get_current_user)) -> User:
    """Require authenticated user (explicit dependency)."""
    return user


def require_role(*allowed_roles: UserRole):
    """Dependency that requires specific role(s)."""

    async def _check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check_role


def require_not_must_change_password(user: User = Depends(get_current_user)) -> User:
    """
    Require user to have changed their temporary password.
    Users with must_change_password=True can only access:
    - /auth/change-password
    - /auth/me
    - /auth/logout
    """
    # This will be enforced at the router level via a custom dependency
    # For now, just return the user; route-specific checks happen in the endpoints
    return user


async def verify_refresh_token(
    request: Request,
    session: AsyncSession,
) -> Optional[User]:
    """Verify refresh token and return user if valid."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        return None

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None

    user_id = payload.get("sub")
    token_version = payload.get("token_version")

    if not user_id:
        return None

    user = await session.get(User, int(user_id))
    if not user or not user.is_active:
        return None

    if user.token_version != token_version:
        return None

    return user


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    secure: bool = False,
    samesite: str = "lax",
) -> None:
    """Set authentication cookies on response."""
    is_production = settings.APP_ENV == "production"

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure or is_production,
        samesite=samesite,
        max_age=30 * 60,  # 30 minutes
        path="/",
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure or is_production,
        samesite=samesite,
        max_age=2 * 24 * 60 * 60,  # 2 days
        path="/auth/refresh",  # Scoped to refresh endpoint
    )


def clear_auth_cookies(response: Response, secure: bool = False, samesite: str = "lax") -> None:
    """Clear authentication cookies."""
    is_production = settings.APP_ENV == "production"
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=secure or is_production,
        samesite=samesite,
        path="/",
    )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        httponly=True,
        secure=secure or is_production,
        samesite=samesite,
        path="/auth/refresh",
    )


async def refresh_access_token(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Refresh access token using refresh token cookie."""
    user = await verify_refresh_token(request, session)
    if not user:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Create new token pair (rotate refresh token)
    access_token = create_access_token(
        user.id, user.username, user.role.value, user.token_version
    )
    refresh_token = create_refresh_token(
        user.id, user.username, user.token_version
    )

    set_auth_cookies(response, access_token, refresh_token)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "must_change_password": user.must_change_password,
        }
    }


# Re-export for convenience
from app.core.security import create_access_token, create_refresh_token