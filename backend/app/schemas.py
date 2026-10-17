"""Pydantic request/response models.

Input validation lives here so that bad or hostile input is rejected at the
edge, before it reaches a query or the agent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]
Horizon = Annotated[int, Field(ge=1, le=365)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# core reads
# --------------------------------------------------------------------------
class AccountOut(ORMModel):
    id: int
    name: str
    institution: str
    account_type: str
    currency: str
    current_balance: Decimal
    is_synthetic: bool


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    base_currency: str
    home_country: str
    study_country: str

    @property
    def priorities(self) -> list[str]:  # pragma: no cover - convenience only
        return []


class UserProfileOut(BaseModel):
    id: int
    email: str
    full_name: str
    base_currency: str
    home_country: str
    study_country: str
    priorities: list[str]
    accounts: list[AccountOut]
    is_demo_data: bool = True


class TransactionOut(ORMModel):
    id: int
    account_id: int
    posted_date: date
    description_raw: str
    merchant_normalized: str
    category: str
    direction: str
    amount_original: Decimal
    currency_original: str
    fee_amount: Decimal | None
    fee_currency: str | None
    is_synthetic: bool
    source: str


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class TransactionCreate(BaseModel):
    account_id: int = Field(ge=1)
    posted_date: date
    description: str = Field(min_length=1, max_length=512)
    amount: Decimal = Field(gt=0, le=Decimal("100000000"))
    currency: CurrencyCode
    direction: Literal["debit", "credit"] = "debit"
    category: str = Field(default="uncategorized", max_length=64)
    fee_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000"))
    fee_currency: CurrencyCode | None = None

    @field_validator("currency", "fee_currency")
    @classmethod
    def upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("posted_date")
    @classmethod
    def not_absurd(cls, value: date) -> date:
        if value.year < 2000 or value.year > 2100:
            raise ValueError("posted_date must be between 2000 and 2100")
        return value


class BillOut(ORMModel):
    id: int
    name: str
    merchant_normalized: str
    category: str
    due_date: date
    amount: Decimal
    currency: str
    status: str
    is_recurring: bool
    autopay: bool
    notes: str


class BillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    due_date: date
    amount: Decimal = Field(gt=0, le=Decimal("100000000"))
    currency: CurrencyCode
    category: str = Field(default="uncategorized", max_length=64)
    is_recurring: bool = False
    autopay: bool = False
    notes: str = Field(default="", max_length=1000)

    @field_validator("currency")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.upper()


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------
class ImportResult(BaseModel):
    imported: int
    skipped: int
    total_rows: int
    errors: list[dict[str, Any]]
    new_merchants: list[str]
    warning: str = (
        "Imported rows are treated as untrusted data. Descriptions are stored "
        "and displayed as text and are never interpreted as instructions."
    )


# --------------------------------------------------------------------------
# reminders & actions
# --------------------------------------------------------------------------
class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    note: str = Field(default="", max_length=1000)
    related_kind: Literal["bill", "subscription", "forecast", "other"] | None = None
    related_ref: str | None = Field(default=None, max_length=160)


class ReminderOut(ORMModel):
    id: int
    title: str
    due_date: date
    note: str
    related_kind: str | None
    related_ref: str | None
    created_by: str
    status: str


class ActionPreviewCreate(BaseModel):
    action_type: Literal["cancel_subscription", "pause_subscription", "switch_plan"]
    target_label: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="", max_length=1000)


class ActionPreviewOut(ORMModel):
    id: int
    action_type: str
    target_label: str
    summary: str
    estimated_monthly_impact: Decimal | None
    currency: str | None
    status: str
    requires_authorization: bool


class ActionDecision(BaseModel):
    """Explicit human authorization step for a previewed action."""

    decision: Literal["approve", "decline"]
    confirmation_text: str = Field(default="", max_length=200)


# --------------------------------------------------------------------------
# assistant
# --------------------------------------------------------------------------
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict[str, Any]
    status: str
    duration_ms: int
    summary: str
    error: str | None = None


class ChatResponse(BaseModel):
    answer: str
    mode: Literal["llm", "offline_deterministic"]
    model: str | None = None
    tool_calls: list[ToolCallRecord]
    facts: list[dict[str, Any]]
    iterations: int
    truncated: bool = False
    disclaimer: str
