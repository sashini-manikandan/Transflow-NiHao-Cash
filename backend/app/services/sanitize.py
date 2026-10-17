"""Strip or mask personal identifiers before text reaches an LLM context.

Transaction descriptions and merchant strings are untrusted bank-statement
text. They must not carry full account numbers or email-like identifiers into
the model window. The UI and REST APIs still see the original stored values;
only agent-bound payloads are scrubbed.
"""

from __future__ import annotations

import re
from typing import Any

# Long digit runs (card / account fragments) and email-like tokens.
_ACCOUNT_DIGITS = re.compile(r"\b\d{6,}\b")
_CARD_MASKED = re.compile(r"\b(\d{4})[*\-xX]{2,}\d{2,4}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IBANISH = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")


def mask_pii_text(value: str) -> str:
    """Replace account-like and email-like substrings with stable placeholders."""
    if not value:
        return value
    text = _EMAIL.sub("[email]", value)
    text = _IBANISH.sub("[account]", text)
    text = _CARD_MASKED.sub(r"****\1", text)
    text = _ACCOUNT_DIGITS.sub("[account]", text)
    return text


def sanitize_for_llm(value: Any) -> Any:
    """Recursively scrub strings in a JSON-serialisable structure."""
    if isinstance(value, str):
        return mask_pii_text(value)
    if isinstance(value, list):
        return [sanitize_for_llm(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_for_llm(item) for key, item in value.items()}
    return value
