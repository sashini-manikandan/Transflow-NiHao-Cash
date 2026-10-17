"""Merchant-name normalization.

Bank descriptions are noisy ("NETFLIX.COM*4471 AMSTERDAM NL 25/03"). We strip
payment-processor noise, reference numbers and locale suffixes so that the same
service lands on one stable key for recurrence detection.

This module is pure string processing on untrusted input: it never executes or
interprets the description, it only canonicalises it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Noise tokens that payment networks prepend/append to the real merchant name.
_PROCESSOR_PREFIXES = (
    "sq *", "sq*", "tst*", "pp*", "paypal *", "paypal*", "pos ", "pos-",
    "visa purchase", "mastercard purchase", "card purchase", "debit card",
    "recurring payment", "direct debit", "dd ", "aci*", "stripe*", "stripe ",
    "amzn mktp", "apl*", "apple.com/bill", "google *", "google*",
)

_NOISE_WORDS = {
    "com", "co", "inc", "ltd", "llc", "plc", "bv", "nv", "gmbh", "sarl",
    "intl", "international", "online", "payment", "payments", "purchase",
    "subscription", "subscr", "sub", "autopay", "auto", "pay", "bill",
    "www", "http", "https", "the",
}

# Two-letter country codes commonly tacked onto the tail of a descriptor.
_COUNTRY_SUFFIXES = {
    "nl", "us", "usa", "uk", "gb", "ae", "in", "de", "fr", "ie", "sg", "lu",
    "cn", "hk", "ca", "au", "jp", "es", "it", "se", "ch",
}

# Known aliases -> canonical display name. Keeps "netflix.com" and
# "netflix intl bv" on the same series.
_ALIASES = {
    "netflix": "Netflix",
    "spotify": "Spotify",
    "spotify ab": "Spotify",
    "amazon prime": "Amazon Prime",
    "prime video": "Amazon Prime Video",
    "amazon prime video": "Amazon Prime Video",
    "disney plus": "Disney+",
    "disneyplus": "Disney+",
    "disney": "Disney+",
    "youtube premium": "YouTube Premium",
    "youtubepremium": "YouTube Premium",
    "apple icloud": "Apple iCloud",
    "icloud": "Apple iCloud",
    "apple music": "Apple Music",
    "adobe": "Adobe Creative Cloud",
    "adobe creative cloud": "Adobe Creative Cloud",
    "adobe creative": "Adobe Creative Cloud",
    "notion labs": "Notion",
    "notion": "Notion",
    "github": "GitHub",
    "openai chatgpt": "ChatGPT Plus",
    "chatgpt": "ChatGPT Plus",
    "openai": "ChatGPT Plus",
    "du telecom": "du Telecom",
    "etisalat": "Etisalat",
    "dewa": "DEWA Utilities",
    "careem": "Careem",
    "talabat": "Talabat",
    "wise": "Wise",
    "transferwise": "Wise",
    "revolut": "Revolut",
    "nyuad housing": "NYUAD Housing",
    "coursera": "Coursera",
    "duolingo": "Duolingo",
    "anytime fitness": "Anytime Fitness",
    "gymnation": "GymNation",
}

# Service families let us spot *overlapping* spend even when the merchants
# differ (two video services, two cloud-storage plans, two VPNs...).
_SERVICE_FAMILIES = {
    "Netflix": "video_streaming",
    "Disney+": "video_streaming",
    "Amazon Prime Video": "video_streaming",
    "YouTube Premium": "video_streaming",
    "Spotify": "music_streaming",
    "Apple Music": "music_streaming",
    "Apple iCloud": "cloud_storage",
    "Google One": "cloud_storage",
    "Dropbox": "cloud_storage",
    "Adobe Creative Cloud": "creative_tools",
    "Notion": "productivity",
    "ChatGPT Plus": "ai_tools",
    "GitHub": "developer_tools",
    "Anytime Fitness": "fitness",
    "GymNation": "fitness",
    "Coursera": "education",
    "Duolingo": "education",
    "du Telecom": "telecom",
    "Etisalat": "telecom",
    "DEWA Utilities": "utilities",
    "NYUAD Housing": "housing",
    "Careem": "transport",
    "Talabat": "food_delivery",
    "Wise": "money_transfer",
    "Revolut": "money_transfer",
}

_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_NUMBERISH_RE = re.compile(r"^[0-9]{2,}$|^[a-z]?[0-9]{3,}[a-z]?$")
_DATEISH_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedMerchant:
    key: str           # canonical display name, e.g. "Netflix"
    slug: str          # lowercase, underscore form for grouping
    family: str | None  # service family, when recognised
    raw: str


def normalize_merchant(description: str) -> NormalizedMerchant:
    """Canonicalise a raw bank description into a stable merchant key."""
    raw = (description or "").strip()
    text = raw.lower()

    text = _DATEISH_RE.sub(" ", text)
    for prefix in _PROCESSOR_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = text.replace("*", " ")
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    tokens = [t for t in text.split(" ") if t]
    kept: list[str] = []
    for token in tokens:
        if _NUMBERISH_RE.match(token):
            continue
        if token in _NOISE_WORDS:
            continue
        if len(token) == 1:
            continue
        kept.append(token)

    # Trailing country codes only; a leading "us" could be part of a name.
    while kept and kept[-1] in _COUNTRY_SUFFIXES:
        kept.pop()

    cleaned = " ".join(kept).strip()
    if not cleaned:
        cleaned = text or raw.lower() or "unknown"

    canonical = _match_alias(cleaned)
    slug = _WS_RE.sub("_", canonical.lower().replace("+", "plus")).strip("_")
    return NormalizedMerchant(
        key=canonical,
        slug=slug,
        family=_SERVICE_FAMILIES.get(canonical),
        raw=raw,
    )


def _match_alias(cleaned: str) -> str:
    """Resolve a cleaned string to a known brand, else title-case it."""
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]

    # Longest alias that appears as a whole-word prefix/substring wins, so
    # "amazon prime video rental" beats "amazon prime".
    best: str | None = None
    for alias, canonical in _ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", cleaned):
            if best is None or len(alias) > len(best):
                best = alias
    if best is not None:
        return _ALIASES[best]

    return " ".join(word.capitalize() for word in cleaned.split(" "))


def service_family(merchant_key: str) -> str | None:
    return _SERVICE_FAMILIES.get(merchant_key)
