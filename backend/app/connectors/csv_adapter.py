"""CSV upload connector (fallback when no bank link exists).

Expected columns: date, amount, counterparty, category, memo
(amount in dollars; positive = in, negative = out).
"""

import csv
import io
from datetime import datetime

from app.models import Transaction


class CsvAdapter:
    provider_name = "CSV upload"

    def parse(
        self, account_id: str, content: str, source_ref: str | None = None
    ) -> list[Transaction]:
        rows = []
        for i, row in enumerate(csv.DictReader(io.StringIO(content)), start=2):
            try:
                rows.append(
                    Transaction(
                        account_id=account_id,
                        booked_at=datetime.fromisoformat(row["date"]),
                        amount_cents=round(float(row["amount"]) * 100),
                        counterparty=row["counterparty"].strip()[:120],
                        category=(row.get("category") or "Uncategorized").strip()[:60],
                        memo=(row.get("memo") or "")[:500],
                        source="file",
                        source_ref=source_ref,
                        created_by="owner",
                    )
                )
            except (KeyError, ValueError, TypeError, AttributeError) as err:  # short rows too
                raise ValueError(f"line {i}: {err}") from err
        return rows
