"""Data connector interface.

The agent and analytics never know which connector is behind the data. Present the
WeBank link as "assumed partner integration, simulated in the sandbox". Real
adapters (a Cambodian bank, a KHQR provider, a wallet) would implement the same
interface.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from app.models import Transaction


class BankConnector(Protocol):
    provider_name: str

    def fetch_transactions(self, account_id: str, since_days: int = 180) -> list[Transaction]:
        """Return transactions; the caller stores them."""
        ...

    def stream_new(self, account_id: str) -> AsyncIterator[Transaction]:
        """Yield new transactions as they happen (the demo's 'live sync')."""
        ...
