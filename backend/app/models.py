"""Database models.

Money rule for the whole codebase: a transaction always stores the amount in
the currency it actually occurred in. Reporting-currency equivalents are
derived at read time from a dated row in `fx_rates`, never stored as a guess.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

MONEY = Numeric(18, 4)
RATE = Numeric(18, 8)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    # Currency all dashboard/reporting figures are expressed in.
    base_currency: Mapped[str] = mapped_column(String(3), default="AED")
    home_country: Mapped[str] = mapped_column(String(64), default="United Arab Emirates")
    study_country: Mapped[str] = mapped_column(String(64), default="United Arab Emirates")
    # Free-text priorities the recommendation ranker boosts against.
    priorities: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")

    @property
    def priority_list(self) -> list[str]:
        return [p.strip() for p in self.priorities.split(",") if p.strip()]


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(32), default="checking")
    currency: Mapped[str] = mapped_column(String(3))
    current_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    # Every account in the MVP is clearly-labelled synthetic demo data.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)

    posted_date: Mapped[date] = mapped_column(Date, index=True)
    # Raw bank text. Treated as untrusted input everywhere, including the agent.
    description_raw: Mapped[str] = mapped_column(String(512))
    merchant_normalized: Mapped[str] = mapped_column(String(160), index=True, default="")
    category: Mapped[str] = mapped_column(String(64), default="uncategorized")

    # "debit" = money out, "credit" = money in.
    direction: Mapped[str] = mapped_column(String(8), default="debit")
    amount_original: Mapped[Decimal] = mapped_column(MONEY)
    currency_original: Mapped[str] = mapped_column(String(3))

    # Explicit cross-border cost, when the statement discloses one.
    fee_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    account: Mapped[Account] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_txn_user_merchant_date", "user_id", "merchant_normalized", "posted_date"),
    )


class FxRate(Base):
    """A dated, attributable exchange rate. Missing rows stay missing."""

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    # 1 unit of base_currency = `rate` units of quote_currency.
    rate: Mapped[Decimal] = mapped_column(RATE)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(64), default="simulated-demo-table")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency", "as_of_date", name="uq_fx_pair_date"
        ),
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    merchant_normalized: Mapped[str] = mapped_column(String(160), default="")
    category: Mapped[str] = mapped_column(String(64), default="uncategorized")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="upcoming")  # upcoming|paid|overdue
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(24), default="seed")  # seed|manual|detected
    notes: Mapped[str] = mapped_column(Text, default="")


class IncomeSource(Base):
    """Expected inflows (stipend, scholarship, part-time work, family transfer)."""

    __tablename__ = "income_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    cadence: Mapped[str] = mapped_column(String(16), default="monthly")
    day_of_month: Mapped[int] = mapped_column(default=1)
    next_expected_date: Mapped[date] = mapped_column(Date)
    confidence: Mapped[str] = mapped_column(String(16), default="high")
    notes: Mapped[str] = mapped_column(Text, default="")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    related_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by: Mapped[str] = mapped_column(String(24), default="user")  # user|assistant
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ActionPreview(Base):
    """A proposed state-changing action awaiting explicit human authorization.

    The MVP never executes a real cancellation; it records a reviewable preview.
    """

    __tablename__ = "action_previews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(48))  # cancel_subscription|...
    target_label: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    estimated_monthly_impact: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_review")
    requires_authorization: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    """Tool/authorization audit trail.

    Deliberately records *what* happened, not the underlying financial detail.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(48))
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="ok")
    detail: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
