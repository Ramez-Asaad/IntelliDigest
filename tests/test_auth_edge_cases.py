"""Login / register edge cases for JWT auth routes."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


def _reg(client: TestClient, email: str, password: str):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )


def _login(client: TestClient, email: str, password: str):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )


class TestRegisterValidation:
    def test_register_success_returns_token(self, client: TestClient):
        r = _reg(client, "alice@example.com", "correct-horse-battery")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == "alice@example.com"

    def test_register_short_password(self, client: TestClient):
        r = _reg(client, "bob@example.com", "short")
        assert r.status_code == 400
        assert "8" in r.json()["detail"].lower()

    def test_register_invalid_email(self, client: TestClient):
        r = _reg(client, "not-an-email", "correct-horse-battery")
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()

    def test_register_password_same_as_email(self, client: TestClient):
        r = _reg(client, "user@example.com", "user@example.com")
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()

    def test_register_password_same_as_local_part(self, client: TestClient):
        # Local part must be long enough to pass min length once it is the only issue.
        r = _reg(client, "twelveuser@example.com", "twelveuser")
        assert r.status_code == 400
        d = r.json()["detail"].lower()
        assert "before" in d or "@" in d

    def test_register_password_only_spaces(self, client: TestClient):
        r = _reg(client, "spaces@example.com", "        ")
        assert r.status_code == 400

    def test_register_duplicate_email(self, client: TestClient):
        _reg(client, "dup@example.com", "first-password-ok")
        r = _reg(client, "dup@example.com", "second-password-ok")
        assert r.status_code == 400
        assert "already" in r.json()["detail"].lower()


class TestGoogleOnlyVsEmail:
    def test_register_blocked_when_email_is_google_only(self, client: TestClient):
        import auth.users as users

        users.get_or_create_google_user("gonly@example.com", "google-sub-123")
        r = _reg(client, "gonly@example.com", "some-password-here")
        assert r.status_code == 400
        assert "google" in r.json()["detail"].lower()

    def test_login_google_only_account_gets_clear_message(self, client: TestClient):
        import auth.users as users

        users.get_or_create_google_user("oauth@example.com", "sub-oauth-456")
        r = _login(client, "oauth@example.com", "any-password-here")
        assert r.status_code == 401
        assert "google" in r.json()["detail"].lower()

    def test_email_user_then_google_link_password_still_works(self, client: TestClient):
        import auth.users as users

        _reg(client, "link@example.com", "email-password-123")
        users.get_or_create_google_user("link@example.com", "google-sub-link-789")
        r = _login(client, "link@example.com", "email-password-123")
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "link@example.com"


class TestLoginFailures:
    def test_wrong_password(self, client: TestClient):
        _reg(client, "u1@example.com", "right-password-99")
        r = _login(client, "u1@example.com", "wrong-password-99")
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password."

    def test_unknown_email(self, client: TestClient):
        r = _login(client, "nobody@example.com", "any-password-here")
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password."


class TestForgotPassword:
    def test_forgot_password_returns_generic_message(self, client: TestClient):
        r = client.post(
            "/api/auth/forgot-password",
            json={"email": "unknown@example.com"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "message" in data
        assert "account" in data["message"].lower()

    def test_reset_password_after_token_issue(self, client: TestClient):
        import auth.users as users
        from auth.password_reset import consume_reset_token, issue_reset_token

        users.register_user("resetme@example.com", "old-password-99")
        uid = users.get_user_for_password_reset("resetme@example.com")["id"]
        raw = issue_reset_token(uid)
        user = consume_reset_token(raw, "new-password-88")
        assert user["email"] == "resetme@example.com"
        # Old password invalid
        r = client.post(
            "/api/auth/login",
            json={"email": "resetme@example.com", "password": "old-password-99"},
        )
        assert r.status_code == 401
        r2 = client.post(
            "/api/auth/login",
            json={"email": "resetme@example.com", "password": "new-password-88"},
        )
        assert r2.status_code == 200


class TestPasswordHelpers:
    def test_validate_password_allows_normal_password(self):
        from auth.users import validate_password_for_registration

        validate_password_for_registration("a@b.com", "not-the-email-99")

    def test_validate_password_rejects_email_match(self):
        from auth.users import validate_password_for_registration

        with pytest.raises(ValueError, match="email"):
            validate_password_for_registration(
                "longuser@example.com", "longuser@example.com"
            )
