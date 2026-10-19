"""Checks on text that leaves the business (payment reminders, supplier messages).

The model writes these messages, so a fooled model could slip in a payment account, a
link or someone's contact details and send it to a customer or supplier. A message like
that is refused before an approval card is even created, and checked again just before
it is sent. Dates (2026-10-05) and amounts ($1,250.00) are allowed.
"""

import re

from app.security.masking import EMAIL

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_CHECKS = [
    ("a link", re.compile(
        r"(https?://|www\.)\S+"
        r"|\b[\w-]+\.(com|net|org|io|co|cn|hk|sg|kh|me|ly|link|xyz|top|app|pay)\b", re.I)),
    ("an email address", EMAIL),
    # 8+ digits, optionally split by spaces or dashes: account, card or phone numbers
    ("an account or phone number", re.compile(r"(?<!\d)\d(?:[\s-]?\d){7,}(?!\d)")),
]


def outbound_problems(text: str) -> list[str]:
    text = _DATE.sub("", text)
    return [label for label, pattern in _CHECKS if pattern.search(text)]


def check_outbound(text: str) -> None:
    """Raise ValueError (the policy engine then blocks and logs) if the text is unsafe."""
    problems = outbound_problems(text)
    if problems:
        raise ValueError(
            f"Message refused: it contains {', '.join(problems)}. Messages to customers and "
            "suppliers may not include links, contact details or account numbers."
        )
