"""Payload-bound approval tokens.

A token is an HMAC over (action_id, payload_hash, expiry). It proves the owner
approved THIS exact action with THIS exact payload, and only until it expires.
If anyone changes a recipient, amount or message after approval, the recomputed
payload hash differs and verification fails. Single use is enforced by the
PendingAction status in the policy engine.
"""

import hashlib
import hmac
import json
import time
from typing import Any


class ApprovalError(Exception):
    """Raised when an approval token is missing, forged, mismatched or expired."""


def canonical_payload(tool_name: str, args: dict[str, Any]) -> str:
    return json.dumps(
        {"tool": tool_name, "args": args}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def payload_hash(tool_name: str, args: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(tool_name, args).encode("utf-8")).hexdigest()


def _sign(secret: str, action_id: str, p_hash: str, exp: int) -> str:
    msg = f"{action_id}.{p_hash}.{exp}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def issue_token(
    *, action_id: str, p_hash: str, secret: str, ttl_seconds: int, now: float | None = None
) -> str:
    exp = int((time.time() if now is None else now) + ttl_seconds)
    return f"{action_id}.{exp}.{_sign(secret, action_id, p_hash, exp)}"


def verify_token(
    token: str, *, action_id: str, p_hash: str, secret: str, now: float | None = None
) -> None:
    try:
        tok_action, exp_str, sig = token.split(".")
        exp = int(exp_str)
    except (AttributeError, ValueError) as err:
        raise ApprovalError("malformed approval token") from err
    if not hmac.compare_digest(tok_action, action_id):
        raise ApprovalError("token belongs to a different action")
    if not hmac.compare_digest(sig, _sign(secret, action_id, p_hash, exp)):
        raise ApprovalError("signature mismatch: payload changed after approval, or token forged")
    if (time.time() if now is None else now) > exp:
        raise ApprovalError("approval expired")
