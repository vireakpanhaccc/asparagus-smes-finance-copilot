"""Every endpoint that returns business data, logs or pending actions needs the owner."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import Settings, settings
from app.db import get_session
from app.main import app

OWNER = {"X-Owner-Token": settings.owner_demo_token}
DATA_ENDPOINTS = [
    "/api/audit",
    "/api/audit/verify",
    "/api/audit/export.csv",
    "/api/forecast",
    "/api/analysis",
    "/api/invoices/overdue",
    "/api/financing?gap_cents=20000",
    "/api/approvals/pending",
]


@pytest.fixture
def client(seeded):
    app.dependency_overrides[get_session] = lambda: seeded
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", DATA_ENDPOINTS)
def test_data_endpoints_refuse_missing_or_wrong_token(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Owner-Token": "guess"}).status_code == 401


@pytest.mark.parametrize("path", DATA_ENDPOINTS)
def test_data_endpoints_work_for_the_owner(client, path):
    assert client.get(path, headers=OWNER).status_code == 200


def test_live_stream_refuses_missing_or_wrong_token(client):
    assert client.get("/api/connect/live").status_code == 401
    assert client.get("/api/connect/live?token=guess").status_code == 401


def test_health_check_stays_public_and_leaks_nothing(client):
    r = client.get("/health")
    assert r.status_code == 200 and set(r.json()) == {"status", "sandbox"}


@pytest.mark.parametrize("secret, token", [
    ("", ""),
    ("change-me", "demo-owner-token"),
    ("change-me-in-dotenv", "x" * 20),
    ("too-short", "short"),
])
def test_default_or_weak_secrets_are_refused(secret, token):
    weak = Settings(_env_file=None, approval_secret=secret, owner_demo_token=token)
    assert weak.insecure_settings()
    with pytest.raises(RuntimeError, match="Refusing to start"):
        with patch.object(main_module, "settings", weak), TestClient(app):
            pass


def test_strong_secrets_are_accepted():
    strong = Settings(_env_file=None, approval_secret="a" * 64, owner_demo_token="b" * 32)
    assert strong.insecure_settings() == []


def test_unset_owner_token_refuses_everyone(client, monkeypatch):
    monkeypatch.setattr(settings, "owner_demo_token", "")
    assert client.get("/api/audit").status_code == 401
    assert client.get("/api/audit", headers={"X-Owner-Token": ""}).status_code == 401
