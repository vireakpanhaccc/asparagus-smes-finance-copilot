from datetime import date

from sqlmodel import Session, select

from app.models import Invoice


def find_overdue(session: Session, account_id: str, today: date) -> list[Invoice]:
    return list(
        session.exec(
            select(Invoice)
            .where(Invoice.account_id == account_id)
            .where(Invoice.paid == False)  # noqa: E712 (SQL expression)
            .where(Invoice.due_on < today)
            .order_by(Invoice.due_on)
        ).all()
    )
