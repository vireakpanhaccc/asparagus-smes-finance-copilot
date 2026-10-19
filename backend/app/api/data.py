"""Read-only endpoints that feed the dashboard and financing screens.

They call the same analytics functions the agent's tools use, so the UI and the
agent always show identical numbers.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.analytics import analysis, financing, forecast, invoices
from app.api.deps import require_owner
from app.config import settings
from app.db import get_session

router = APIRouter(tags=["data"], dependencies=[Depends(require_owner)])
ACC = settings.demo_account_id


@router.get("/forecast")
def get_forecast(weeks: int = Query(12, ge=1, le=26), session: Session = Depends(get_session)):
    return forecast.forecast_weekly(session, ACC, weeks=weeks)


@router.get("/analysis")
def get_analysis(session: Session = Depends(get_session)):
    return analysis.business_summary(session, ACC)


@router.get("/invoices/overdue")
def get_overdue(session: Session = Depends(get_session)):
    rows = invoices.find_overdue(session, ACC, today=date.today())
    return [
        {"id": i.id, "customer": i.customer, "amount_cents": i.amount_cents,
         "days_late": (date.today() - i.due_on).days}
        for i in rows
    ]


@router.get("/financing")
def get_financing(
    gap_cents: int = Query(..., ge=0),
    months: int = Query(2, ge=1, le=36),
    session: Session = Depends(get_session),
):
    return financing.rank_options(session, ACC, gap_cents, months)
