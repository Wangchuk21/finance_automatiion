"""Pydantic schemas for authentication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Login request."""
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=1, description="User password")


class LoginResponse(BaseModel):
    """Login response."""
    token: str
    user_id: int
    email: str
    full_name: Optional[str]
    role: str
    password_change_required: bool


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)


class ChangePasswordResponse(BaseModel):
    """Change password response."""
    message: str


class UserMeResponse(BaseModel):
    """Current user response."""
    id: int
    email: str
    full_name: Optional[str]
    role: str
    password_change_required: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
