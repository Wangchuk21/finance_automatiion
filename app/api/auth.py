"""Authentication API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    get_current_user,
    refresh_access_token,
    set_auth_cookies,
)
from app.core.config import settings
from app.core.email import send_password_reset_email, send_welcome_email
from app.core.security import (
    PasswordPolicy,
    generate_temp_password,
    hash_password,
    rate_limiter,
    verify_password,
    verify_password_dummy,
    write_auth_audit,
)
from app.db.session import get_session
from app.models import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    user: dict
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)
    confirm_password: str = Field(..., min_length=12, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str
    user: dict


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=200)
    role: UserRole = UserRole.VIEWER


class UserCreateResponse(BaseModel):
    user: dict
    temporary_password: str
    expires_at: datetime


class UserResetPasswordResponse(BaseModel):
    message: str
    temporary_password: str
    expires_at: datetime


class UserDeactivateResponse(BaseModel):
    message: str


class UserListResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    must_change_password: bool
    last_login: Optional[datetime]
    created_at: datetime


class MeResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    must_change_password: bool
    password_changed_at: Optional[datetime]
    last_login: Optional[datetime]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _create_user_tokens(user: User, response: Response) -> tuple[str, str]:
    """Create and set auth tokens for a user."""
    access_token = create_access_token(
        user.id, user.username, user.role, user.token_version
    )
    refresh_token = create_refresh_token(
        user.id, user.username, user.token_version
    )
    set_auth_cookies(response, access_token, refresh_token)
    return access_token, refresh_token


def _user_to_dict(user: User) -> dict:
    """Convert User model to dict for response."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticate user with username/email and password.
    Returns tokens in cookies and user info.
    """
    ip = _get_client_ip(request)
    identifier = credentials.username.strip().lower()

    # Rate limiting check (per username + IP)
    if rate_limiter.is_locked(identifier, ip):
        retry_after = rate_limiter.get_lockout_remaining(identifier, ip)
        await write_auth_audit(
            session,
            "login_failed_locked",
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
            details={"username": identifier, "reason": "rate_limited"},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {retry_after} seconds.",
        )

    # Find user by username or email (constant-time lookup to prevent enumeration)
    stmt = select(User).where(
        (User.username == identifier) | (User.email == identifier)
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # Timing-safe verification: always verify against a hash
    if user:
        password_valid = verify_password(credentials.password, user.password_hash)
    else:
        # Dummy verification to maintain constant timing
        verify_password_dummy(credentials.password)
        password_valid = False

    if not password_valid or not user:
        # Record failed attempt
        rate_limiter.record_attempt(identifier, ip)
        await write_auth_audit(
            session,
            "login_failed",
            user_id=user.id if user else None,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
            details={"username": identifier, "reason": "invalid_credentials"},
        )

        # Generic error message (no username enumeration)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        await write_auth_audit(
            session,
            "login_failed_locked",
            user_id=user.id,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
            details={"reason": "account_locked"},
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked. Please try again later.",
        )

    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Check temporary password expiry
    if user.temp_password_expires_at and user.temp_password_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Temporary password has expired. Contact administrator.",
        )

    # Successful login - clear rate limit
    rate_limiter.clear_attempts(identifier, ip)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await session.commit()

    # Create tokens
    await _create_user_tokens(user, response)

    await write_auth_audit(
        session,
        "login_success",
        user_id=user.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={"must_change_password": user.must_change_password},
    )

    return LoginResponse(
        user=_user_to_dict(user),
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Change user password. Requires current password.
    Clears must_change_password flag, rotates tokens.
    """
    ip = _get_client_ip(request)

    # Verify current password
    if not verify_password(payload.current_password, user.password_hash):
        await write_auth_audit(
            session,
            "change_password_failed",
            user_id=user.id,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
            details={"reason": "invalid_current_password"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Validate new password against policy
    is_valid, error = PasswordPolicy.validate(
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        current_password_hash=user.password_hash,
        temp_password=None,  # We don't have the plain temp password here
        password_history=user.password_history_list,
    )

    if not is_valid:
        await write_auth_audit(
            session,
            "change_password_failed",
            user_id=user.id,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
            details={"reason": "policy_violation", "error": error},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Hash new password and add current to history
    new_hash = hash_password(payload.new_password)
    user.add_password_to_history(new_hash)
    user.password_hash = new_hash
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    user.temp_password_expires_at = None  # Clear temp password expiry
    user.token_version += 1  # Invalidate all existing tokens
    user.failed_login_count = 0
    user.locked_until = None

    await session.commit()

    # Create new tokens with incremented token_version
    await _create_user_tokens(user, response)

    await write_auth_audit(
        session,
        "change_password_success",
        user_id=user.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={},
    )

    return ChangePasswordResponse(
        message="Password changed successfully",
        user=_user_to_dict(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Logout user and invalidate tokens."""
    ip = _get_client_ip(request)

    # Increment token version to invalidate all tokens
    user.token_version += 1
    await session.commit()

    # Clear cookies
    clear_auth_cookies(response)

    await write_auth_audit(
        session,
        "logout",
        user_id=user.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={},
    )

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return MeResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        password_changed_at=user.password_changed_at,
        last_login=user.last_login,
    )


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Refresh access token using refresh token cookie."""
    return await refresh_access_token(request, response, session)


# ---------------------------------------------------------------------------
# Admin-only endpoints
# ---------------------------------------------------------------------------

def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


@router.post("/users", response_model=UserCreateResponse)
async def create_user(
    request: Request,
    response: Response,
    payload: UserCreateRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    """
    Create a new user with a temporary password.
    Only admins can create users.
    """
    ip = _get_client_ip(request)

    # Check if username or email already exists
    existing = await session.execute(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        )

    # Generate temporary password
    temp_password = generate_temp_password()
    temp_password_hash = hash_password(temp_password)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    # Create user
    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=temp_password_hash,
        role=payload.role,
        must_change_password=True,
        temp_password_expires_at=expires_at,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    await write_auth_audit(
        session,
        "user_created",
        user_id=admin.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={
            "created_user_id": user.id,
            "created_username": user.username,
            "role": user.role,
        },
    )

    # Send welcome email with temporary password
    send_welcome_email(
        to_email=user.email,
        username=user.username,
        temp_password=temp_password,
        expires_at_hours=48,
    )

    # Return temp password ONLY ONCE
    return UserCreateResponse(
        user=_user_to_dict(user),
        temporary_password=temp_password,
        expires_at=expires_at,
    )


@router.post("/users/{user_id}/reset-password", response_model=UserResetPasswordResponse)
async def reset_user_password(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    """
    Reset a user's password (generates new temporary password).
    Only admins can reset passwords.
    """
    ip = _get_client_ip(request)

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset your own password via admin endpoint",
        )

    # Generate new temporary password
    temp_password = generate_temp_password()
    temp_password_hash = hash_password(temp_password)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    # Update user
    user.password_hash = temp_password_hash
    user.must_change_password = True
    user.temp_password_expires_at = expires_at
    user.token_version += 1  # Invalidate all tokens
    user.failed_login_count = 0
    user.locked_until = None

    await session.commit()

    await write_auth_audit(
        session,
        "password_reset_by_admin",
        user_id=admin.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={"target_user_id": user.id, "target_username": user.username},
    )

    # Send password reset email
    send_password_reset_email(
        to_email=user.email,
        username=user.username,
        temp_password=temp_password,
        expires_at_hours=48,
    )

    return UserResetPasswordResponse(
        message="Password reset successfully",
        temporary_password=temp_password,
        expires_at=expires_at,
    )


@router.post("/users/{user_id}/deactivate", response_model=UserDeactivateResponse)
async def deactivate_user(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    """
    Deactivate a user (soft delete).
    Only admins can deactivate users.
    """
    ip = _get_client_ip(request)

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    user.is_active = False
    user.token_version += 1  # Invalidate all tokens
    await session.commit()

    await write_auth_audit(
        session,
        "user_deactivated",
        user_id=admin.id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        details={"target_user_id": user.id, "target_username": user.username},
    )

    return UserDeactivateResponse(
        message=f"User {user.username} deactivated successfully",
    )


@router.get("/users", response_model=list[UserListResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    """List all users (admin only)."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        UserListResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            must_change_password=u.must_change_password,
            last_login=u.last_login,
            created_at=u.created_at,
        )
        for u in users
    ]