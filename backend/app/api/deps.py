import hmac

from fastapi import Header, HTTPException, Query

from app.config import settings


def require_owner(x_owner_token: str = Header(default="")) -> str:
    """Demo auth: one owner, one shared token from .env.

    Known risk (security report): single-user demo auth. Production would use real
    identity verification (OAuth/OIDC + MFA) and per-user sessions.
    """
    # An unset token must never match an empty header: fail closed.
    if not settings.owner_demo_token or not hmac.compare_digest(
        x_owner_token, settings.owner_demo_token
    ):
        raise HTTPException(status_code=401, detail="owner authentication required")
    return "owner"


def require_owner_stream(token: str = Query(default="")) -> str:
    """Same check for the live-sync stream: browsers' EventSource cannot send headers.

    Known risk (security report): a token in the URL can end up in server logs.
    """
    return require_owner(token)
