"""PII masking for logs, outbox records and (where possible) LLM context.

Order matters: emails, then phone numbers, then long digit runs (account numbers).
Known limitation (list it in the security report): an 8+ digit run that is not an
account number (for example 20261016) is also masked. That errs on the safe side.
"""

import re

EMAIL = re.compile(r"\b([\w.+-])[\w.+-]*@([\w-]+\.[\w.-]+)\b")
# Cambodian numbers: +855 12 345 678, 855-12-345-678, 012 345 678, 0123456789
PHONE_KH = re.compile(r"(?<!\d)(?:\+?855|0)[\s-]?\d{1,2}[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)")
ACCOUNT = re.compile(r"(?<!\d)\d{8,19}(?!\d)")


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"***-***-{digits[-3:]}"


def mask_pii(text: str) -> str:
    if not text:
        return text
    text = EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    text = PHONE_KH.sub(_mask_phone, text)
    text = ACCOUNT.sub(lambda m: f"****{m.group()[-4:]}", text)
    return text
