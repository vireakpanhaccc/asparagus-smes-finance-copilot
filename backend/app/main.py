from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import tools  # noqa: F401  (registers all tools)
from app.api import approvals, audit, chat, connect, data, data_records
from app.config import settings
from app.db import init_db
from app.rate_limit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    problems = settings.insecure_settings()
    if problems:
        raise RuntimeError(
            "Refusing to start: " + "; ".join(problems) + ". Set them in .env; generate "
            "with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    init_db()
    yield


app = FastAPI(
    title="SME Finance Copilot API",
    description="SME finance agent with permission tiers, payload-bound approvals and a "
    "hash-chained audit log. Sandbox only.",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Owner-Token"],
)

for r in (chat.router, approvals.router, data.router, audit.router, connect.router,
          data_records.router):
    app.include_router(r, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "sandbox": settings.sandbox_mode}
