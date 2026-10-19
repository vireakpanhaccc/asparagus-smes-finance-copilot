import os

# Test-only secrets, set before app.config is imported, so the suite never depends on a
# developer's .env and runs the same in CI.
os.environ["APPROVAL_SECRET"] = "test-approval-secret-" + "0" * 32
os.environ["OWNER_DEMO_TOKEN"] = "test-owner-token-0123456789"

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from sqlmodel.pool import StaticPool  # noqa: E402

import app.tools  # noqa: E402, F401  (registers tools)
from scripts.seed_data import seed  # noqa: E402

TODAY = date(2026, 10, 18)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded(session):
    seed(session, today=TODAY)
    return session


class FakeClock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return FakeClock()
