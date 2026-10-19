"""Every endpoint that returns business data, logs or pending actions needs the owner."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
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
