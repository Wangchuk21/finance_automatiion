"""Tests for authentication endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from passlib.hash import argon2

from app.core.security import PasswordPolicy, hash_password, verify_password, verify_password_dummy
from app.models import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession


class TestPasswordPolicy:
    """Test password validation policy."""

    def test_valid_password(self):
        """Test a valid password passes all checks."""
        is_valid, error = PasswordPolicy.validate(
            new_password="ValidPass123!@#",
            confirm_password="ValidPass123!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert is_valid
        assert error == ""

    def test_too_short(self):
        """Test password too short is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="Short1!",
            confirm_password="Short1!",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "at least" in error.lower()

    def test_mismatch(self):
        """Test mismatched passwords are rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="ValidPass123!@#",
            confirm_password="DifferentPass123!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "match" in error.lower()

    def test_matches_temp_password(self):
        """Test password matching temp password is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="TempPass123!@#",
            confirm_password="TempPass123!@#",
            current_password_hash=None,
            temp_password="TempPass123!@#",
            password_history=[],
        )
        assert not is_valid
        assert "temporary" in error.lower()

    def test_matches_current(self):
        """Test password matching current password is rejected."""
        pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type=argon2.type)
        current_hash = pwd_context.hash("CurrentPass123!@#")
        
        is_valid, error = PasswordPolicy.validate(
            new_password="CurrentPass123!@#",
            confirm_password="CurrentPass123!@#",
            current_password_hash=current_hash,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "current" in error.lower()

    def test_matches_history(self):
        """Test password in history is rejected."""
        pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type=argon2.type)
        old_hash = pwd_context.hash("OldPass123!@#")
        
        is_valid, error = PasswordPolicy.validate(
            new_password="OldPass123!@#",
            confirm_password="OldPass123!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[old_hash],
        )
        assert not is_valid
        assert "recently used" in error.lower()

    def test_no_uppercase(self):
        """Test password without uppercase is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="validpass123!@#",
            confirm_password="validpass123!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "uppercase" in error.lower()

    def test_no_lowercase(self):
        """Test password without lowercase is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="VALIDPASS123!@#",
            confirm_password="VALIDPASS123!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "lowercase" in error.lower()

    def test_no_digit(self):
        """Test password without digit is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="ValidPass!@#",
            confirm_password="ValidPass!@#",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "digit" in error.lower()

    def test_no_special(self):
        """Test password without special char is rejected."""
        is_valid, error = PasswordPolicy.validate(
            new_password="ValidPass123",
            confirm_password="ValidPass123",
            current_password_hash=None,
            temp_password=None,
            password_history=[],
        )
        assert not is_valid
        assert "special" in error.lower()


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_and_verify(self):
        """Test password can be hashed and verified."""
        password = "TestPass123!@#"
        hash_val = hash_password(password)
        assert verify_password(password, hash_val)
        assert not verify_password("WrongPass123!@#", hash_val)

    def test_dummy_verification_timing(self):
        """Test dummy verification runs without error."""
        # The dummy function just ensures timing-safe comparison by hashing a dummy password
        result = verify_password_dummy("any_password")
        assert result is False

    def test_verify_wrong_password(self):
        """Test verifying wrong password returns False."""
        password = "TestPass123!@#"
        hash_val = hash_password(password)
        assert not verify_password("WrongPass456!@#", hash_val)


class TestUserModel:
    """Test User model password history."""

    def test_password_history_list_empty(self):
        """Test empty password history returns empty list."""
        user = User(password_hash="hash1", password_history=None)
        assert user.password_history_list == []

    def test_password_history_list_with_data(self):
        """Test password history list parsing."""
        user = User(password_hash="hash1", password_history='["hash2", "hash3"]')
        assert user.password_history_list == ["hash2", "hash3"]

    def test_password_history_invalid_json(self):
        """Test invalid JSON in password history returns empty list."""
        user = User(password_hash="hash1", password_history="invalid")
        assert user.password_history_list == []

    def test_add_password_to_history(self):
        """Test adding password to history keeps last 3."""
        user = User(password_hash="current_hash", password_history='["old1", "old2", "old3", "old4"]')
        user.add_password_to_history("new_hash")
        history = user.password_history_list
        # Should have current + new + last 2 old = 4 total
        assert len(history) == 4
        assert history[0] == "new_hash"
        assert history[1] == "current_hash"
        assert history[2] == "old1"
        assert history[3] == "old2"