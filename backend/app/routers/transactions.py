"""Transaction listing, manual entry and CSV import."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession, record_audit
from ..models import Account, Transaction
from ..schemas import ImportResult, TransactionCreate, TransactionOut, TransactionPage
from ..services.importer import ImportError_, import_transactions_csv
from ..services.merchants import normalize_merchant

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

SAMPLE_CSV = """date,description,amount,currency,direction,category,fee_amount,fee_currency
2025-05-03,NETFLIX.COM*4471 AMSTERDAM NL,-61.75,AED,debit,entertainment,,
2025-05-05,SPOTIFY AB STOCKHOLM,-23.99,AED,debit,entertainment,,
2025-05-08,OPENAI *CHATGPT SUBSCR,-20.00,USD,debit,software,,
2025-05-11,CARREFOUR MARINA MALL,-184.30,AED,debit,groceries,,
2025-05-14,WISE TRANSFER TO ACCRA,-1100.00,AED,debit,transfer,18.50,AED
2025-05-15,CAMPUS RA STIPEND PAYROLL,900.00,AED,credit,income,,
2025-05-17,ADOBE CREATIVE CLOUD SUB,-22.99,USD,debit,software,,
2025-05-19,DISNEY PLUS AE RECURRING PAYMENT,-29.99,AED,debit,entertainment,,
2025-05-21,TALABAT FOOD DELIVERY DXB,-64.00,AED,debit,food,,
2025-05-26,DU TELECOM POSTPAID BILL,-131.20,AED,debit,utilities,,
"""


@router.get("", response_model=TransactionPage)
def list_transactions(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    merchant: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=64),
    direction: str | None = Query(default=None, pattern="^(debit|credit)$"),
    start_date: date | None = None,
    end_date: date | None = None,
) -> TransactionPage:
    conditions = [Transaction.user_id == user.id]
    if merchant:
        conditions.append(Transaction.merchant_normalized.ilike(f"%{merchant}%"))
    if category:
        conditions.append(Transaction.category == category)
    if direction:
        conditions.append(Transaction.direction == direction)
    if start_date:
        conditions.append(Transaction.posted_date >= start_date)
    if end_date:
        conditions.append(Transaction.posted_date <= end_date)

    total = db.execute(
        select(func.count()).select_from(Transaction).where(*conditions)
    ).scalar_one()
    rows = (
        db.execute(
            select(Transaction)
            .where(*conditions)
            .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return TransactionPage(
        items=[TransactionOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate, user: CurrentUser, db: DbSession
) -> TransactionOut:
    account = db.execute(
        select(Account).where(
            Account.id == payload.account_id, Account.user_id == user.id
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That account does not belong to this user."
        )
    if payload.fee_amount is not None and payload.fee_currency is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "fee_currency is required when fee_amount is provided.",
        )

    merchant = normalize_merchant(payload.description)
    row = Transaction(
        user_id=user.id,
        account_id=account.id,
        posted_date=payload.posted_date,
        description_raw=payload.description,
        merchant_normalized=merchant.key,
        category=payload.category,
        direction=payload.direction,
        amount_original=payload.amount,
        currency_original=payload.currency,
        fee_amount=payload.fee_amount,
        fee_currency=payload.fee_currency,
        is_synthetic=True,
        source="manual",
    )
    db.add(row)
    record_audit(
        db, user_id=user.id, event="transaction_created", outcome="ok",
        detail=f"source=manual currency={payload.currency}",
    )
    db.commit()
    db.refresh(row)
    return TransactionOut.model_validate(row)


@router.get("/sample-csv", response_class=PlainTextResponse)
def sample_csv() -> str:
    """A ready-made file so the import flow can be demoed in one click."""
    return SAMPLE_CSV


@router.post("/import", response_model=ImportResult)
async def import_csv(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    account_id: int | None = Query(default=None, ge=1),
) -> ImportResult:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only .csv files can be imported."
        )
    content = await file.read()
    try:
        result = import_transactions_csv(db, user, content, default_account_id=account_id)
    except ImportError_ as exc:
        record_audit(
            db, user_id=user.id, event="csv_import", outcome="rejected",
            detail="file-level validation failed",
        )
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    record_audit(
        db, user_id=user.id, event="csv_import", outcome="ok",
        detail=f"imported={result['imported']} skipped={result['skipped']}",
    )
    db.commit()
    return ImportResult(**result)


@router.get("/categories")
def categories(user: CurrentUser, db: DbSession) -> dict:
    rows = db.execute(
        select(Transaction.category)
        .where(Transaction.user_id == user.id)
        .distinct()
        .order_by(Transaction.category)
    ).all()
    return {"categories": [r[0] for r in rows]}
