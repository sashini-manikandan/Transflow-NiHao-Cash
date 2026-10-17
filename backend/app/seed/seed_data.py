"""Deterministic synthetic demo data.

Everything produced here is fabricated for demonstration. No real bank is
connected, no real account numbers or credentials exist in this dataset, and
every FX rate is flagged `is_simulated=True`.

The data is shaped to exercise each analysis path end to end:
  * clean monthly subscriptions            -> high-confidence recurrence
  * Netflix billed on two cards            -> same-service duplicate
  * Netflix + Disney+                      -> video streaming overlap
  * Spotify + Apple Music                  -> music streaming overlap
  * Adobe and Netflix price rises          -> price-change detection
  * usage-varying telecom bill             -> recurring but low amount stability
  * random food/transport spend            -> must NOT be flagged recurring
  * an annual plan with 2 occurrences      -> low-confidence annual cadence
  * a TRY holiday charge with no TRY rate  -> "rate unavailable", not invented
  * a large tuition instalment             -> projected shortfall before stipend
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, Bill, FxRate, IncomeSource, Transaction, User
from ..services.merchants import normalize_merchant
from ..services.recurring import _add_months

DEMO_EMAIL_DEFAULT = "amina@demo.billwise.ai"
RNG_SEED = 20240914

# Three complete student personas for the demo switcher. Each is a full cash-flow
# story, not a half-built account: Amina = tuition crunch + remittance home;
# Jordan = local rent covered but remittance timing is the decision;
# Mei = cross-border / FX fee pressure without an immediate shortfall.
DEMO_PERSONAS: list[dict[str, str]] = [
    {
        "email": "amina@demo.billwise.ai",
        "full_name": "Amina Osei",
        "home_country": "Ghana",
        "study_country": "United Arab Emirates",
        "base_currency": "AED",
        "tagline": "Tuition shortfall + Accra remittance",
        "story": (
            "Domestic student cash flow is tight before tuition. Cutting duplicate "
            "streaming and timing the Accra transfer are one linked decision."
        ),
    },
    {
        "email": "jordan@demo.billwise.ai",
        "full_name": "Jordan Okonkwo",
        "home_country": "Nigeria",
        "study_country": "United Arab Emirates",
        "base_currency": "AED",
        "tagline": "Rent covered — remittance timing is the lever",
        "story": (
            "Local bills clear, but a large home remittance is due. The agent "
            "should connect spare capacity after subscription cuts with when "
            "to send money, not treat them as separate apps."
        ),
    },
    {
        "email": "mei@demo.billwise.ai",
        "full_name": "Mei Chen",
        "home_country": "China",
        "study_country": "United Arab Emirates",
        "base_currency": "AED",
        "tagline": "FX fees and foreign-currency spend dominate",
        "story": (
            "No immediate overdraft, but USD/INR spend and transfer fees eat "
            "the margin. Focus on currency costs and holding transfers when "
            "local near-term bills are already covered."
        ),
    },
]

# --------------------------------------------------------------------------
# FX rates: USD-quoted pairs. Cross rates (e.g. EUR->AED) are derived at read
# time through USD by FxService, with both legs reported. TRY is deliberately
# absent so the "no rate available" path is demonstrable.
# --------------------------------------------------------------------------
FX_SERIES: dict[str, tuple[float, float]] = {
    # quote currency: (rate 15 months ago, rate today)
    "AED": (3.6725, 3.6725),   # pegged
    "GHS": (11.80, 15.40),
    "EUR": (0.9250, 0.8600),
    "GBP": (0.7950, 0.7450),
    "INR": (82.50, 88.20),
}

FX_MONTHS_OF_HISTORY = 16


def seed_fx_rates(db: Session, today: date) -> int:
    """Monthly USD-based rates with a deterministic wobble."""
    rng = random.Random(RNG_SEED + 1)
    existing = db.execute(select(func.count()).select_from(FxRate)).scalar_one()
    if existing:
        return 0

    created = 0
    for quote, (start_rate, end_rate) in FX_SERIES.items():
        for month_offset in range(FX_MONTHS_OF_HISTORY):
            as_of = _add_months(today.replace(day=1), -(FX_MONTHS_OF_HISTORY - 1 - month_offset))
            progress = month_offset / max(FX_MONTHS_OF_HISTORY - 1, 1)
            base_value = start_rate + (end_rate - start_rate) * progress
            wobble = 0.0 if quote == "AED" else base_value * rng.uniform(-0.004, 0.004)
            db.add(
                FxRate(
                    base_currency="USD",
                    quote_currency=quote,
                    rate=Decimal(str(round(base_value + wobble, 6))),
                    as_of_date=as_of,
                    source="simulated-demo-table",
                    is_simulated=True,
                )
            )
            created += 1

    # A fresh rate dated yesterday so today's conversions are not stale.
    for quote, (_, end_rate) in FX_SERIES.items():
        db.add(
            FxRate(
                base_currency="USD",
                quote_currency=quote,
                rate=Decimal(str(round(end_rate, 6))),
                as_of_date=today - timedelta(days=1),
                source="simulated-demo-table",
                is_simulated=True,
            )
        )
        created += 1

    db.flush()
    return created


# --------------------------------------------------------------------------
# Recurring charge specifications
# --------------------------------------------------------------------------
class RecurringSpec:
    def __init__(
        self,
        description: str,
        amount: str,
        currency: str,
        account_key: str,
        day_of_month: int,
        category: str,
        months: int = 13,
        cadence_months: int = 1,
        jitter_days: int = 0,
        amount_jitter_pct: float = 0.0,
        price_change_to: str | None = None,
        price_change_trailing: int = 0,
        fee: str | None = None,
        stop_months_ago: int = 0,
    ):
        self.description = description
        self.amount = Decimal(amount)
        self.currency = currency
        self.account_key = account_key
        self.day_of_month = day_of_month
        self.category = category
        self.months = months
        self.cadence_months = cadence_months
        self.jitter_days = jitter_days
        self.amount_jitter_pct = amount_jitter_pct
        self.price_change_to = Decimal(price_change_to) if price_change_to else None
        self.price_change_trailing = price_change_trailing
        self.fee = Decimal(fee) if fee else None
        self.stop_months_ago = stop_months_ago


RECURRING_SPECS: list[RecurringSpec] = [
    # --- streaming / media -------------------------------------------------
    RecurringSpec(
        "NETFLIX.COM*4471 AMSTERDAM NL", "56.00", "AED", "aed_main", 14, "entertainment",
        months=13, price_change_to="61.75", price_change_trailing=3,
    ),
    # The same service, also billed on the USD card -> duplicate signal.
    RecurringSpec(
        "NETFLIX INTL BV SUBSCRIPTION", "15.49", "USD", "usd_card", 22, "entertainment",
        months=7,
    ),
    RecurringSpec(
        "DISNEY PLUS AE RECURRING PAYMENT", "29.99", "AED", "aed_main", 19, "entertainment",
        months=9,
    ),
    RecurringSpec(
        "SPOTIFY AB STOCKHOLM", "23.99", "AED", "aed_main", 5, "entertainment", months=13,
    ),
    RecurringSpec(
        "APPLE.COM/BILL APPLE MUSIC", "19.99", "AED", "aed_main", 12, "entertainment",
        months=6,
    ),
    # --- tools / study -----------------------------------------------------
    RecurringSpec(
        "OPENAI *CHATGPT SUBSCR", "20.00", "USD", "usd_card", 8, "software", months=11,
    ),
    RecurringSpec(
        "ADOBE CREATIVE CLOUD SUB", "19.99", "USD", "usd_card", 17, "software",
        months=12, price_change_to="22.99", price_change_trailing=2,
    ),
    RecurringSpec(
        "NOTION LABS INC SF US", "8.00", "USD", "usd_card", 9, "software", months=10,
    ),
    RecurringSpec(
        "GITHUB.COM PRO PLAN", "4.00", "USD", "usd_card", 23, "software", months=13,
    ),
    RecurringSpec(
        "COURSERA.ORG ONLINE COURSE", "49.00", "USD", "usd_card", 11, "education",
        months=5, stop_months_ago=3,  # cancelled: should read as dormant
    ),
    # Annual plan: only two occurrences exist -> annual cadence, low confidence.
    RecurringSpec(
        "DUOLINGO SUPER ANNUAL", "83.99", "USD", "usd_card", 6, "education",
        months=13, cadence_months=12,
    ),
    # --- living costs ------------------------------------------------------
    RecurringSpec(
        "APPLE.COM/BILL ICLOUD 50GB", "11.99", "AED", "aed_main", 2, "software", months=13,
    ),
    RecurringSpec(
        "GYMNATION ABU DHABI AE", "99.00", "AED", "aed_main", 1, "health", months=13,
    ),
    # Usage-based: regular timing, variable amount -> stability penalty.
    RecurringSpec(
        "DU TELECOM POSTPAID BILL", "125.00", "AED", "aed_main", 26, "utilities",
        months=13, jitter_days=2, amount_jitter_pct=0.14,
    ),
    RecurringSpec(
        "DEWA UTILITIES AUTOPAY", "210.00", "AED", "aed_main", 7, "utilities",
        months=13, jitter_days=3, amount_jitter_pct=0.22,
    ),
    # --- cross-border ------------------------------------------------------
    # Monthly remittance home, with a disclosed transfer fee.
    RecurringSpec(
        "WISE TRANSFER TO ACCRA", "1100.00", "AED", "aed_main", 29, "transfer",
        months=13, jitter_days=1, fee="18.50",
    ),
    # Home-country SIM, billed in GHS on the Ghana account.
    RecurringSpec(
        "MTN GHANA AIRTIME RECURRING", "90.00", "GHS", "ghs_home", 10, "utilities",
        months=12, amount_jitter_pct=0.05,
    ),
]

# Irregular spend. These must *not* be reported as subscriptions.
IRREGULAR_MERCHANTS: list[tuple[str, str, str, str, float, float]] = [
    # description, currency, account, category, min, max
    ("TALABAT FOOD DELIVERY DXB", "AED", "aed_main", "food", 28.0, 96.0),
    ("CAREEM RIDE ABU DHABI", "AED", "aed_main", "transport", 12.0, 58.0),
    ("CARREFOUR MARINA MALL", "AED", "aed_main", "groceries", 45.0, 310.0),
    ("LULU HYPERMARKET AE", "AED", "aed_main", "groceries", 30.0, 240.0),
    ("STARBUCKS CAMPUS AE", "AED", "aed_main", "food", 14.0, 36.0),
    ("AMZN MKTP AE*2K41LQ", "AED", "aed_main", "shopping", 25.0, 420.0),
    ("UBER *TRIP HELP.UBER.COM", "AED", "aed_main", "transport", 18.0, 72.0),
    ("BOOKSTORE CAMPUS PURCHASE", "AED", "aed_main", "education", 40.0, 180.0),
]


def _occurrence_dates(today: date, spec: RecurringSpec) -> list[date]:
    rng = random.Random(f"{RNG_SEED}:{spec.description}")
    dates: list[date] = []
    anchor = today.replace(day=1)
    total_steps = spec.months // spec.cadence_months
    for step in range(total_steps + 1):
        months_back = (total_steps - step) * spec.cadence_months + spec.stop_months_ago
        month_start = _add_months(anchor, -months_back)
        day = min(spec.day_of_month, 28)
        occurrence = month_start.replace(day=day)
        if spec.jitter_days:
            occurrence += timedelta(days=rng.randint(-spec.jitter_days, spec.jitter_days))
        if occurrence <= today:
            dates.append(occurrence)
    return sorted(set(dates))


def _occurrence_amounts(spec: RecurringSpec, count: int) -> list[Decimal]:
    rng = random.Random(f"{RNG_SEED}:amt:{spec.description}")
    amounts = [spec.amount for _ in range(count)]
    if spec.price_change_to and spec.price_change_trailing:
        start = max(count - spec.price_change_trailing, 0)
        for i in range(start, count):
            amounts[i] = spec.price_change_to
    if spec.amount_jitter_pct:
        amounts = [
            (a * Decimal(str(1 + rng.uniform(-spec.amount_jitter_pct, spec.amount_jitter_pct))))
            .quantize(Decimal("0.01"))
            for a in amounts
        ]
    return amounts


def _add_txn(
    db: Session,
    user: User,
    account: Account,
    posted: date,
    description: str,
    amount: Decimal,
    currency: str,
    category: str,
    direction: str = "debit",
    fee: Decimal | None = None,
) -> None:
    normalized = normalize_merchant(description)
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            posted_date=posted,
            description_raw=description,
            merchant_normalized=normalized.key,
            category=category,
            direction=direction,
            amount_original=amount,
            currency_original=currency,
            fee_amount=fee,
            fee_currency=currency if fee is not None else None,
            is_synthetic=True,
            source="seed",
        )
    )


def seed_demo_user(db: Session, today: date, email: str) -> User:
    user = User(
        email=email,
        full_name="Amina Osei",
        base_currency="AED",
        home_country="Ghana",
        study_country="United Arab Emirates",
        priorities="avoid overdraft,cut streaming costs,send money home cheaply",
    )
    db.add(user)
    db.flush()

    accounts = {
        # Balances are chosen so the tuition instalment cannot be covered from
        # the current position, making the shortfall warning demonstrable on
        # any day of the month.
        "aed_main": Account(
            user_id=user.id, name="Everyday Account", institution="ADCB (demo)",
            account_type="checking", currency="AED", current_balance=Decimal("3480.50"),
        ),
        "usd_card": Account(
            user_id=user.id, name="USD Study Card", institution="ADCB (demo)",
            account_type="card", currency="USD", current_balance=Decimal("612.40"),
        ),
        "ghs_home": Account(
            user_id=user.id, name="Home Account (Accra)", institution="GCB Bank (demo)",
            account_type="savings", currency="GHS", current_balance=Decimal("5240.00"),
        ),
    }
    for account in accounts.values():
        db.add(account)
    db.flush()

    # --- recurring charges -------------------------------------------------
    for spec in RECURRING_SPECS:
        dates = _occurrence_dates(today, spec)
        amounts = _occurrence_amounts(spec, len(dates))
        account = accounts[spec.account_key]
        for posted, amount in zip(dates, amounts):
            _add_txn(
                db, user, account, posted, spec.description, amount,
                spec.currency, spec.category, fee=spec.fee,
            )

    # --- irregular day-to-day spend ----------------------------------------
    rng = random.Random(RNG_SEED + 2)
    for description, currency, account_key, category, lo, hi in IRREGULAR_MERCHANTS:
        account = accounts[account_key]
        for _ in range(rng.randint(9, 22)):
            posted = today - timedelta(days=rng.randint(1, 390))
            amount = Decimal(str(round(rng.uniform(lo, hi), 2)))
            _add_txn(db, user, account, posted, description, amount, currency, category)

    # --- one charge in a currency we hold no rate for ----------------------
    _add_txn(
        db, user, accounts["aed_main"], today - timedelta(days=21),
        "ISTANBUL HOTEL BOOKING TR", Decimal("4250.00"), "TRY", "travel",
    )

    # --- inflows -----------------------------------------------------------
    for month_offset in range(13, -1, -1):
        stipend_date = _add_months(today.replace(day=1), -month_offset).replace(day=28)
        if stipend_date <= today:
            _add_txn(
                db, user, accounts["aed_main"], stipend_date,
                "NYUAD STUDENT STIPEND PAYMENT", Decimal("4000.00"), "AED",
                "income", direction="credit",
            )
        ra_date = _add_months(today.replace(day=1), -month_offset).replace(day=15)
        if ra_date <= today:
            _add_txn(
                db, user, accounts["aed_main"], ra_date,
                "CAMPUS RA STIPEND PAYROLL", Decimal("900.00"), "AED",
                "income", direction="credit",
            )

    db.add_all(
        [
            IncomeSource(
                user_id=user.id, name="NYUAD student stipend", amount=Decimal("4000.00"),
                currency="AED", cadence="monthly", day_of_month=28,
                next_expected_date=_next_on_day(today, 28), confidence="high",
                notes="Paid by the university on the 28th of each month.",
            ),
            IncomeSource(
                user_id=user.id, name="Campus RA pay", amount=Decimal("900.00"),
                currency="AED", cadence="monthly", day_of_month=15,
                next_expected_date=_next_on_day(today, 15), confidence="medium",
                notes="Hours vary by month, so the amount is approximate.",
            ),
            IncomeSource(
                user_id=user.id, name="Family transfer from Accra", amount=Decimal("300.00"),
                currency="USD", cadence="quarterly", day_of_month=5,
                next_expected_date=_next_on_day(today, 5, months_ahead=1),
                confidence="low", notes="Irregular; sent when family is able to.",
            ),
        ]
    )

    # --- upcoming bills ----------------------------------------------------
    db.add_all(
        [
            Bill(
                user_id=user.id, name="Tuition instalment 3 of 4",
                merchant_normalized="NYUAD Finance", category="education",
                due_date=today + timedelta(days=17), amount=Decimal("9800.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=False,
                source="seed", notes="Largest single obligation this term.",
            ),
            Bill(
                user_id=user.id, name="Student housing instalment",
                merchant_normalized="NYUAD Housing", category="housing",
                due_date=today + timedelta(days=9), amount=Decimal("1850.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=True,
                source="seed",
            ),
            Bill(
                user_id=user.id, name="Health insurance premium",
                merchant_normalized="Daman Insurance", category="insurance",
                due_date=today + timedelta(days=24), amount=Decimal("480.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=True,
                source="seed",
            ),
            Bill(
                user_id=user.id, name="Visa renewal fee",
                merchant_normalized="ICP UAE", category="government",
                due_date=today + timedelta(days=38), amount=Decimal("1200.00"),
                currency="AED", status="upcoming", is_recurring=False, autopay=False,
                source="seed",
            ),
            Bill(
                user_id=user.id, name="Conference travel deposit",
                merchant_normalized="Student Travel Desk", category="travel",
                due_date=today + timedelta(days=31), amount=Decimal("260.00"),
                currency="USD", status="upcoming", is_recurring=False, autopay=False,
                source="seed", notes="Billed in USD by the organiser.",
            ),
            Bill(
                user_id=user.id, name="Sibling school fees (Accra)",
                merchant_normalized="Accra Grammar School", category="family",
                due_date=today + timedelta(days=12), amount=Decimal("2400.00"),
                currency="GHS", status="upcoming", is_recurring=True, autopay=False,
                source="seed", notes="Paid from the Accra account.",
            ),
            Bill(
                user_id=user.id, name="Mobile postpaid bill",
                merchant_normalized="du Telecom", category="utilities",
                due_date=today - timedelta(days=4), amount=Decimal("131.20"),
                currency="AED", status="paid", is_recurring=True, autopay=True,
                source="seed",
            ),
        ]
    )

    db.flush()
    return user


def _next_on_day(today: date, day: int, months_ahead: int = 0) -> date:
    day = min(day, 28)
    candidate = today.replace(day=day)
    if candidate <= today:
        candidate = _add_months(candidate, 1)
    if months_ahead:
        candidate = _add_months(candidate, months_ahead)
    return candidate


def seed_jordan_user(db: Session, today: date, email: str = "jordan@demo.billwise.ai") -> User:
    """Persona 2: local obligations covered; remittance timing is the decision."""
    user = User(
        email=email,
        full_name="Jordan Okonkwo",
        base_currency="AED",
        home_country="Nigeria",
        study_country="United Arab Emirates",
        priorities="time remittances well,keep rent autopay safe,cut unused streaming",
    )
    db.add(user)
    db.flush()

    accounts = {
        "aed_main": Account(
            user_id=user.id, name="Campus Checking", institution="FAB (demo)",
            account_type="checking", currency="AED", current_balance=Decimal("9200.00"),
        ),
        "usd_card": Account(
            user_id=user.id, name="USD Debit", institution="FAB (demo)",
            account_type="card", currency="USD", current_balance=Decimal("840.00"),
        ),
        "ghs_home": Account(
            user_id=user.id, name="Family Support (Lagos mirror)", institution="GTBank (demo)",
            account_type="savings", currency="GHS", current_balance=Decimal("3100.00"),
        ),
    }
    for account in accounts.values():
        db.add(account)
    db.flush()

    # Leaner subscription set: one music overlap risk, one remittance with fees.
    lean_specs = [
        RecurringSpec(
            "SPOTIFY AB STOCKHOLM", "23.99", "AED", "aed_main", 5, "entertainment", months=10,
        ),
        RecurringSpec(
            "APPLE.COM/BILL APPLE MUSIC", "19.99", "AED", "aed_main", 12, "entertainment",
            months=8,
        ),
        RecurringSpec(
            "NETFLIX.COM SUBSCRIPTION AE", "56.00", "AED", "aed_main", 14, "entertainment",
            months=11,
        ),
        RecurringSpec(
            "GITHUB.COM PRO PLAN", "4.00", "USD", "usd_card", 23, "software", months=12,
        ),
        RecurringSpec(
            "WISE TRANSFER TO LAGOS", "1500.00", "AED", "aed_main", 27, "transfer",
            months=10, jitter_days=1, fee="24.00",
        ),
        RecurringSpec(
            "DU TELECOM POSTPAID BILL", "95.00", "AED", "aed_main", 26, "utilities",
            months=10, amount_jitter_pct=0.10,
        ),
    ]
    for spec in lean_specs:
        dates = _occurrence_dates(today, spec)
        amounts = _occurrence_amounts(spec, len(dates))
        account = accounts[spec.account_key]
        for posted, amount in zip(dates, amounts):
            _add_txn(
                db, user, account, posted, spec.description, amount,
                spec.currency, spec.category, fee=spec.fee,
            )

    rng = random.Random(RNG_SEED + 7)
    for description, currency, account_key, category, lo, hi in IRREGULAR_MERCHANTS[:5]:
        account = accounts[account_key]
        for _ in range(rng.randint(6, 12)):
            posted = today - timedelta(days=rng.randint(1, 280))
            amount = Decimal(str(round(rng.uniform(lo, hi), 2)))
            _add_txn(db, user, account, posted, description, amount, currency, category)

    for month_offset in range(10, -1, -1):
        stipend_date = _add_months(today.replace(day=1), -month_offset).replace(day=25)
        if stipend_date <= today:
            _add_txn(
                db, user, accounts["aed_main"], stipend_date,
                "GRADUATE RESEARCH STIPEND", Decimal("5500.00"), "AED",
                "income", direction="credit",
            )

    db.add(
        IncomeSource(
            user_id=user.id, name="Graduate research stipend", amount=Decimal("5500.00"),
            currency="AED", cadence="monthly", day_of_month=25,
            next_expected_date=_next_on_day(today, 25), confidence="high",
        )
    )
    db.add_all(
        [
            Bill(
                user_id=user.id, name="Off-campus rent",
                merchant_normalized="Bayut Leasing Demo", category="housing",
                due_date=today + timedelta(days=6), amount=Decimal("3200.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=True,
                source="seed", notes="Autopay — must clear before any remittance.",
            ),
            Bill(
                user_id=user.id, name="Family support remittance (Lagos)",
                merchant_normalized="Wise", category="family",
                due_date=today + timedelta(days=11), amount=Decimal("1500.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=False,
                source="seed",
                notes="Hold if FX/fees worsen; local rent is already covered.",
            ),
            Bill(
                user_id=user.id, name="Health insurance premium",
                merchant_normalized="Daman Insurance", category="insurance",
                due_date=today + timedelta(days=20), amount=Decimal("420.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=True,
                source="seed",
            ),
        ]
    )
    db.flush()
    return user


def seed_mei_user(db: Session, today: date, email: str = "mei@demo.billwise.ai") -> User:
    """Persona 3: comfortable locally; foreign-currency costs are the story."""
    user = User(
        email=email,
        full_name="Mei Chen",
        base_currency="AED",
        home_country="China",
        study_country="United Arab Emirates",
        priorities="reduce FX fees,track USD subscriptions,avoid unconvertible spend",
    )
    db.add(user)
    db.flush()

    accounts = {
        "aed_main": Account(
            user_id=user.id, name="AED Everyday", institution="HSBC (demo)",
            account_type="checking", currency="AED", current_balance=Decimal("12500.00"),
        ),
        "usd_card": Account(
            user_id=user.id, name="USD Study Card", institution="HSBC (demo)",
            account_type="card", currency="USD", current_balance=Decimal("210.00"),
        ),
        "ghs_home": Account(
            # Reused key so shared helpers stay simple; currency is INR for Mei.
            user_id=user.id, name="INR Family Pocket", institution="ICICI (demo)",
            account_type="savings", currency="INR", current_balance=Decimal("48000.00"),
        ),
    }
    for account in accounts.values():
        db.add(account)
    db.flush()

    mei_specs = [
        RecurringSpec(
            "NETFLIX INTL BV SUBSCRIPTION", "15.49", "USD", "usd_card", 22, "entertainment",
            months=9,
        ),
        RecurringSpec(
            "OPENAI *CHATGPT SUBSCR", "20.00", "USD", "usd_card", 8, "software", months=10,
        ),
        RecurringSpec(
            "ADOBE CREATIVE CLOUD SUB", "22.99", "USD", "usd_card", 17, "software", months=8,
        ),
        RecurringSpec(
            "WISE TRANSFER TO SHANGHAI", "800.00", "AED", "aed_main", 18, "transfer",
            months=9, fee="16.75",
        ),
        RecurringSpec(
            "APPLE.COM/BILL ICLOUD 50GB", "11.99", "AED", "aed_main", 2, "software", months=11,
        ),
    ]
    for spec in mei_specs:
        dates = _occurrence_dates(today, spec)
        amounts = _occurrence_amounts(spec, len(dates))
        account = accounts[spec.account_key]
        for posted, amount in zip(dates, amounts):
            _add_txn(
                db, user, account, posted, spec.description, amount,
                spec.currency, spec.category, fee=spec.fee,
            )

    # INR spend that converts via USD triangulation.
    rng = random.Random(RNG_SEED + 11)
    inr_account = accounts["ghs_home"]
    for _ in range(8):
        posted = today - timedelta(days=rng.randint(5, 200))
        _add_txn(
            db, user, inr_account, posted,
            "UPI FAMILY SUPPORT RECEIPT INR",
            Decimal(str(round(rng.uniform(2000, 9000), 2))),
            "INR", "family", direction="credit",
        )
    for _ in range(6):
        posted = today - timedelta(days=rng.randint(3, 180))
        _add_txn(
            db, user, inr_account, posted,
            "IRCTC RAIL BOOKING IN",
            Decimal(str(round(rng.uniform(400, 2500), 2))),
            "INR", "travel",
        )

    _add_txn(
        db, user, accounts["aed_main"], today - timedelta(days=18),
        "ISTANBUL HOTEL BOOKING TR", Decimal("3800.00"), "TRY", "travel",
    )

    for month_offset in range(9, -1, -1):
        pay_date = _add_months(today.replace(day=1), -month_offset).replace(day=1)
        if pay_date <= today:
            _add_txn(
                db, user, accounts["aed_main"], pay_date,
                "INTERNSHIP STIPEND PAYMENT", Decimal("7000.00"), "AED",
                "income", direction="credit",
            )

    db.add(
        IncomeSource(
            user_id=user.id, name="Internship stipend", amount=Decimal("7000.00"),
            currency="AED", cadence="monthly", day_of_month=1,
            next_expected_date=_next_on_day(today, 1), confidence="high",
        )
    )
    db.add_all(
        [
            Bill(
                user_id=user.id, name="Shared flat contribution",
                merchant_normalized="Roommate Split Demo", category="housing",
                due_date=today + timedelta(days=8), amount=Decimal("2100.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=False,
                source="seed",
            ),
            Bill(
                user_id=user.id, name="USD conference registration",
                merchant_normalized="IEEE Student", category="education",
                due_date=today + timedelta(days=16), amount=Decimal("185.00"),
                currency="USD", status="upcoming", is_recurring=False, autopay=False,
                source="seed",
            ),
            Bill(
                user_id=user.id, name="Home remittance window",
                merchant_normalized="Wise", category="family",
                due_date=today + timedelta(days=14), amount=Decimal("800.00"),
                currency="AED", status="upcoming", is_recurring=True, autopay=False,
                source="seed",
                notes="Local bills clear first; then compare fee vs waiting.",
            ),
        ]
    )
    db.flush()
    return user


def list_demo_personas() -> list[dict[str, str]]:
    """Public catalogue for the demo switcher (no financial detail)."""
    return [
        {
            "email": p["email"],
            "full_name": p["full_name"],
            "home_country": p["home_country"],
            "study_country": p["study_country"],
            "base_currency": p["base_currency"],
            "tagline": p["tagline"],
            "story": p["story"],
        }
        for p in DEMO_PERSONAS
    ]


def seed_if_empty(db: Session, email: str | None = None, today: date | None = None) -> bool:
    """Ensure FX rates and all demo personas exist. Returns True if anything was created.

    `email` is kept for call-site compatibility; every listed persona is seeded
    if missing so the switcher always has three complete stories.
    """
    _ = email or DEMO_EMAIL_DEFAULT
    today = today or date.today()

    seed_fx_rates(db, today)
    created = False

    amina = db.execute(
        select(User).where(User.email == "amina@demo.billwise.ai")
    ).scalar_one_or_none()
    if amina is None:
        seed_demo_user(db, today, "amina@demo.billwise.ai")
        created = True

    jordan = db.execute(
        select(User).where(User.email == "jordan@demo.billwise.ai")
    ).scalar_one_or_none()
    if jordan is None:
        seed_jordan_user(db, today)
        created = True

    mei = db.execute(
        select(User).where(User.email == "mei@demo.billwise.ai")
    ).scalar_one_or_none()
    if mei is None:
        seed_mei_user(db, today)
        created = True

    db.commit()
    return created
