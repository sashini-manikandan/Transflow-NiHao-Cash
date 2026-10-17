"""CSV transaction import.

Treats the uploaded file as untrusted input: bounded size, bounded row count,
strict per-field validation, and per-row error reporting instead of a partial
mystery failure. Descriptions are stored verbatim as *data* and are never
interpreted as instructions anywhere downstream.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Transaction, User
from .merchants import normalize_merchant

MAX_ROWS = 2000
MAX_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_DESCRIPTION = 512

REQUIRED_COLUMNS = {"date", "description", "amount", "currency"}
OPTIONAL_COLUMNS = {"direction", "category", "account", "fee_amount", "fee_currency"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d")


class ImportError_(ValueError):
    """Raised for problems with the file as a whole, not an individual row."""


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{raw}' (expected e.g. 2025-03-14)")


def _parse_amount(raw: str) -> tuple[Decimal, str]:
    """Return (magnitude, direction). A leading '-' means money out."""
    cleaned = raw.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        raise ValueError("amount is empty")
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("+-")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"amount '{raw}' is not a number") from exc
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    if value > Decimal("100000000"):
        raise ValueError("amount is implausibly large")
    return value, ("debit" if negative else "credit")


def _parse_currency(raw: str) -> str:
    code = raw.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"currency '{raw}' must be a 3-letter code")
    return code


def import_transactions_csv(
    db: Session,
    user: User,
    content: bytes,
    default_account_id: int | None = None,
) -> dict:
    if len(content) > MAX_BYTES:
        raise ImportError_(f"File is larger than {MAX_BYTES // 1024 // 1024} MB.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_("File must be UTF-8 encoded CSV.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ImportError_("CSV appears to be empty.")

    headers = {(h or "").strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise ImportError_(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            f"Required: {', '.join(sorted(REQUIRED_COLUMNS))}."
        )

    accounts = (
        db.execute(select(Account).where(Account.user_id == user.id)).scalars().all()
    )
    if not accounts:
        raise ImportError_("This user has no account to import into.")
    by_name = {a.name.strip().lower(): a for a in accounts}
    by_currency: dict[str, Account] = {}
    for account in accounts:
        by_currency.setdefault(account.currency, account)

    default_account = accounts[0]
    if default_account_id is not None:
        match = next((a for a in accounts if a.id == default_account_id), None)
        if match is None:
            raise ImportError_("The requested account does not belong to this user.")
        default_account = match

    known_merchants = {
        m
        for (m,) in db.execute(
            select(Transaction.merchant_normalized).where(Transaction.user_id == user.id).distinct()
        ).all()
    }

    imported = 0
    errors: list[dict] = []
    new_merchants: set[str] = set()
    total_rows = 0

    for line_number, row in enumerate(reader, start=2):
        total_rows += 1
        if total_rows > MAX_ROWS:
            errors.append(
                {"row": line_number, "error": f"File exceeds the {MAX_ROWS}-row limit; stopped here."}
            )
            break

        normalized_row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
        try:
            posted = _parse_date(normalized_row.get("date", ""))
            description = normalized_row.get("description", "").strip()
            if not description:
                raise ValueError("description is empty")
            description = description[:MAX_DESCRIPTION]

            amount, inferred_direction = _parse_amount(normalized_row.get("amount", ""))
            currency = _parse_currency(normalized_row.get("currency", ""))

            direction_raw = normalized_row.get("direction", "").strip().lower()
            if direction_raw in {"debit", "credit"}:
                direction = direction_raw
            elif direction_raw:
                raise ValueError(f"direction '{direction_raw}' must be 'debit' or 'credit'")
            else:
                direction = inferred_direction

            fee_amount: Decimal | None = None
            fee_currency: str | None = None
            fee_raw = normalized_row.get("fee_amount", "").strip()
            if fee_raw:
                fee_amount, _ = _parse_amount(fee_raw)
                fee_currency = (
                    _parse_currency(normalized_row["fee_currency"])
                    if normalized_row.get("fee_currency", "").strip()
                    else currency
                )

            account_hint = normalized_row.get("account", "").strip().lower()
            account = (
                by_name.get(account_hint)
                or by_currency.get(currency)
                or default_account
            )

            category = (normalized_row.get("category", "").strip() or "uncategorized")[:64]
            merchant = normalize_merchant(description)

            db.add(
                Transaction(
                    user_id=user.id,
                    account_id=account.id,
                    posted_date=posted,
                    description_raw=description,
                    merchant_normalized=merchant.key,
                    category=category,
                    direction=direction,
                    amount_original=amount,
                    currency_original=currency,
                    fee_amount=fee_amount,
                    fee_currency=fee_currency,
                    is_synthetic=True,
                    source="csv_import",
                )
            )
            if merchant.key not in known_merchants:
                new_merchants.add(merchant.key)
            imported += 1

        except ValueError as exc:
            errors.append({"row": line_number, "error": str(exc)})

    if imported:
        db.commit()
    else:
        db.rollback()

    return {
        "imported": imported,
        "skipped": len(errors),
        "total_rows": total_rows,
        "errors": errors[:50],
        "new_merchants": sorted(new_merchants),
    }
