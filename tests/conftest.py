"""Shared fixtures: isolated auth DB + JWT before importing the app."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

# Ensure jwt_tokens sees a secret when auth.config is first imported.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long!")


@pytest.fixture
def client(monkeypatch, tmp_path):
    db = tmp_path / "auth.db"
    path = str(db)
    # users, password_reset, and config each bind AUTH_DB_PATH — keep one file for tests.
    monkeypatch.setattr("auth.config.AUTH_DB_PATH", path)
    monkeypatch.setattr("auth.users.AUTH_DB_PATH", path)
    monkeypatch.setattr("auth.password_reset.AUTH_DB_PATH", path)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long!")
    # Skip heavy LangChain init (load_dotenv does not override an already-set empty key).
    monkeypatch.setenv("GROQ_API_KEY", "")
    # Import after patching DB path so tables are created on the temp file.
    import server

    app = server.app
    with TestClient(app) as c:
        yield c
