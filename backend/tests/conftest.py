from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep tests off any real key and off the developer's .env database.
os.environ["OPENAI_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_ON_STARTUP"] = "false"

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401
from app.seed.seed_data import seed_if_empty  # noqa: E402

# Every date-sensitive assertion is anchored here so results are reproducible.
FIXED_TODAY = date(2025, 6, 15)
DEMO_EMAIL = "amina@demo.billwise.ai"


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def today() -> date:
    return FIXED_TODAY


@pytest.fixture()
def seeded(db: Session, today: date):
    seed_if_empty(db, email=DEMO_EMAIL, today=today)
    from app.models import User

    user = db.query(User).filter(User.email == DEMO_EMAIL).one()
    return user


@pytest.fixture()
def second_user(db: Session):
    """A second account used to prove record isolation."""
    from datetime import timedelta

    from app.models import Account, Bill, Transaction, User

    user = User(email="other@demo.billwise.ai", full_name="Other Student", base_currency="AED")
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id, name="Other Account", institution="Demo",
        currency="AED", current_balance=99999,
    )
    db.add(account)
    db.flush()
    db.add(
        Transaction(
            user_id=user.id, account_id=account.id, posted_date=date.today(),
            description_raw="SECRET OTHER USER PAYMENT", merchant_normalized="Secret Other",
            direction="debit", amount_original=777, currency_original="AED",
        )
    )
    db.add(
        Bill(
            user_id=user.id, name="Other user private bill",
            due_date=date.today() + timedelta(days=10),
            amount=5555, currency="AED", status="upcoming",
        )
    )
    db.commit()
    return user


@pytest.fixture()
def live_seeded(db: Session):
    """Seeded against the real current date.

    The API reads `date.today()`, so HTTP tests need data anchored to now
    rather than to the fixed date the engine tests use.
    """
    seed_if_empty(db, email=DEMO_EMAIL, today=date.today())
    from app.models import User

    return db.query(User).filter(User.email == DEMO_EMAIL).one()


@pytest.fixture()
def client(db: Session, live_seeded):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.deps import ai_rate_limiter
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    ai_rate_limiter.reset()
    try:
        with TestClient(app) as test_client:
            test_client.headers.update({"X-Demo-User": DEMO_EMAIL})
            yield test_client
    finally:
        app.dependency_overrides.clear()
        ai_rate_limiter.reset()
