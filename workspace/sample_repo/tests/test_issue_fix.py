"""
tests/test_issue_fix.py
Tests for GitHub Issue fix: email regex validation on UserBase.
"""
import pytest
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import UserBase, UserCreate, UserResponse


class TestEmailValidation:
    """Tests for email field validation on UserBase."""

    # --- Valid emails ---
    @pytest.mark.parametrize("email", [
        "alice@example.com",
        "user.name+tag@sub.domain.org",
        "user123@mail.co.uk",
        "a@b.io",
    ])
    def test_valid_email_accepted(self, email):
        user = UserBase(name="Test", email=email)
        assert user.email == email

    # --- Invalid emails ---
    @pytest.mark.parametrize("bad_email", [
        "not-an-email",
        "missing@tld",
        "@nodomain.com",
        "spaces in@email.com",
        "",
        "plainstring",
    ])
    def test_invalid_email_rejected(self, bad_email):
        with pytest.raises(ValidationError):
            UserBase(name="Test", email=bad_email)

    def test_usercreate_inherits_validation(self):
        """UserCreate extends UserBase — validation must propagate."""
        with pytest.raises(ValidationError):
            UserCreate(name="Bob", email="bad-email", password="secret")

    def test_userresponse_inherits_validation(self):
        """UserResponse extends UserBase — validation must propagate."""
        with pytest.raises(ValidationError):
            UserResponse(id=1, name="Bob", email="bad-email", active=True)

    def test_valid_usercreate(self):
        u = UserCreate(name="Bob", email="bob@example.com", password="s3cr3t")
        assert u.email == "bob@example.com"
