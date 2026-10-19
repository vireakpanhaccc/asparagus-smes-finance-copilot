"""Mock WeBank merchant-account connector (sandbox only)."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime

from app.models import Transaction


class MockWeBankAdapter:
    provider_name = "WeBank (mock)"

    def __init__(self, seed: int = 7, interval_seconds: float = 4.0) -> None:
        self._rng = random.Random(seed)
        self.interval = interval_seconds

    def fetch_transactions(self, account_id: str, since_days: int = 180) -> list[Transaction]:
        # The historical feed comes from scripts/seed_data.py, which writes straight
        # to the database. TODO(backend): move generation here if you want a
        # "first sync" animation in the demo.
        return []

    async def stream_new(self, account_id: str) -> AsyncIterator[Transaction]:
        """Emit a plausible café sale every few seconds for the live-sync demo."""
        while True:
            await asyncio.sleep(self.interval)
            yield Transaction(
                account_id=account_id,
                booked_at=datetime.utcnow(),
                amount_cents=self._rng.choice([250, 350, 450, 600, 1200]),
                counterparty="Walk-in customer (KHQR)",
                category="Sales",
                source="mock_webank",
            )
