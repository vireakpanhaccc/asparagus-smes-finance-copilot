"""Untrusted-text handling (prompt-injection defence, layer 1 of 2).

Free text from customers, suppliers or bank memos is DATA, never instructions. So are
names (counterparty, customer, payee, supplier, category): anyone who can add a row
controls them. Before it reaches the LLM it is:
  1. scanned for instruction-like patterns (flagged + logged if found),
  2. escaped so it cannot close the wrapper tag,
  3. wrapped in <untrusted_data source="..."> tags the system prompt tells the model to
     treat as data only.

Layer 2 is the policy engine: even if the model is fooled, it cannot send or submit
anything without the owner's approval. Detection is heuristic, so list it as a
known risk in the security report.
"""

import re
import unicodedata
from typing import Any

from sqlmodel import Session

from app.security import audit
from app.security.masking import mask_pii

_PATTERNS = [
    r"ignore (all|any|the|your|previous|prior) .{0,20}(instructions|rules)",
    r"disregard .{0,30}(instructions|rules|above)",
    r"you are now",
    r"new instructions",
    r"system prompt",
    r"<\s*/?\s*(system|assistant|tool|untrusted_data)",
    r"\b(approve|transfer|send|pay|submit)\b.{0,40}\b(immediately|right now|without)\b",
    r"\bact as\b",
    # Chinese (simplified and traditional): "ignore previous instructions", "you are now",
    # "new instructions", "system prompt", "transfer/pay immediately", "transfer to account"
    r"(忽略|无视|無視|不要理会|不要理會).{0,8}(指令|指示|规则|規則|提示|说明|說明)",
    r"你现在是|你現在是|新的?指令|系统提示|系統提示",
    r"(立即|马上|馬上|立刻|现在就|現在就).{0,10}(转账|轉賬|轉帳|汇款|匯款|付款|支付|批准)",
    r"(转账|轉賬|轉帳|汇款|匯款).{0,20}(账户|帳戶|账号|帳號)",
]
_SUSPICIOUS = re.compile("|".join(_PATTERNS), re.IGNORECASE)
# Invisible characters used to split words so a pattern no longer matches ("ig​nore")
_INVISIBLE = re.compile("[­᠎​-‏⁠-⁤﻿]")


def _normalize(text: str) -> str:
    """Undo common disguises before scanning: fullwidth or styled letters (ｉｇｎｏｒｅ),
    invisible characters and unusual spacing."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    return re.sub(r"\s+", " ", text)
# Written for the owner: the model passes it on (system rule 2) and often quotes it as is.
INJECTION_WARNING = (
    "Warning for the owner: this text contains instructions (for example to transfer or "
    "approve something). They were ignored and nothing was done."
)


def looks_like_instructions(text: str) -> bool:
    return bool(text and _SUSPICIOUS.search(_normalize(text)))


def wrap_untrusted(source: str, text: str) -> str:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<untrusted_data source="{source}">{safe}</untrusted_data>'


def scan_and_wrap(session: Session, source: str, text: str) -> str:
    """Wrap text for the LLM; log an audit entry if it looks like an injection attempt.

    The scan runs on the original text; what the model receives is masked, so phone
    numbers, emails and account numbers in a note never reach the third-party model.
    """
    if looks_like_instructions(text):
        audit.append(
            session,
            actor=source,
            action="untrusted_text_detected",
            tier="read_only",
            result="ignored",
            detail="Instruction-like text found in data. Treated as data, not followed.",
        )
    return wrap_untrusted(source, mask_pii(text))


# Names typed by the owner, synced from a bank or uploaded in a CSV. Anyone who can add a
# row (or a bank-feed counterparty) controls them, so they are untrusted like notes.
NAME_FIELDS = {"counterparty", "customer", "payee", "supplier", "category"}
_WRAPPED = re.compile(r'<untrusted_data source="[^"]*">(.*?)</untrusted_data>', re.S)


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def unwrap_untrusted(text: str) -> str:
    """Remove wrapper tags, e.g. when the model copies a wrapped name into a tool argument."""
    return _WRAPPED.sub(lambda m: _unescape(m.group(1)), text)


def wrap_names(value: Any) -> Any:
    """Wrap (and mask) every name field, at any depth, before a tool result reaches the model.

    `next_actions` is left as is: it holds exact tool arguments the model must copy
    (the actions are held for the owner anyway, and their text is still scanned).
    """
    if isinstance(value, list):
        return [wrap_names(v) for v in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, v in value.items():
        if key == "next_actions":
            out[key] = v
        elif key in NAME_FIELDS and isinstance(v, str) and v and not _WRAPPED.fullmatch(v):
            out[key] = wrap_untrusted(key, mask_pii(v))
        else:
            out[key] = wrap_names(v)
    return out


def contains_instructions(value: Any) -> bool:
    """True if any string (or dict key) in a tool result looks like an injection attempt.

    Text a tool already wrapped was scanned (and logged) by that tool, so it is skipped.
    """
    if isinstance(value, str):
        return not _WRAPPED.fullmatch(value) and looks_like_instructions(value)
    if isinstance(value, list):
        return any(contains_instructions(v) for v in value)
    if isinstance(value, dict):
        return any(contains_instructions(k) or contains_instructions(v)
                   for k, v in value.items())
    return False


def untrusted_fields(session: Session, source: str, field: str, text: str) -> dict[str, str]:
    """{field: wrapped text}, plus a "warning" the model must pass on if it was flagged.

    The warning sits outside the untrusted wrapper, so the model surfaces the attempt
    instead of silently dropping it.
    """
    if not text:
        return {field: ""}
    out = {field: scan_and_wrap(session, source, text)}
    if looks_like_instructions(text):
        out["warning"] = INJECTION_WARNING
    return out
