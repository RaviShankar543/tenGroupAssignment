"""Shared pytest fixtures.

The key idea: every test runs against a FRESH, ISOLATED SQLite database created in
a temporary directory. Tests never touch the developer's real `booking.db`, never
depend on each other, and never require wall-clock sleeps.

We achieve isolation by pointing SQLAlchemy at a throwaway file-based SQLite
database and overriding FastAPI's `get_db` dependency so both the app and the
tests use the SAME session factory bound to that temporary database.
"""

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session(tmp_path):
    """Provide a Session bound to a brand-new SQLite file for a single test.

    `tmp_path` is a pytest built-in giving a unique temp directory per test, so
    each test gets its own database file and cannot see another test's data.
    """
    # Build a dedicated engine for this test's temporary database file.
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Create the schema in the fresh database.
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()

    # Stash the factory on the session so the client fixture can reuse it, ensuring
    # the app and the test share exactly one database.
    session._testing_factory = TestingSessionLocal  # type: ignore[attr-defined]

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """A TestClient whose `get_db` dependency uses the same temporary database.

    Overriding `get_db` is the standard FastAPI pattern for swapping in a test
    database without changing application code.
    """
    TestingSessionLocal = db_session._testing_factory  # type: ignore[attr-defined]

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Always clear overrides so tests stay independent.
        app.dependency_overrides.clear()


@pytest.fixture()
def seed_basic(db_session):
    """Insert a small, predictable dataset and return the created rows.

    Members:
      - available_member   : booking_count 0 (can book).
      - at_limit_member    : booking_count 2 (== MAX_BOOKINGS, blocked).
      - over_limit_member  : booking_count 3 (> MAX_BOOKINGS, blocked).
    Items:
      - available_item     : remaining_count 5, expires 2030 (bookable).
      - sold_out_item      : remaining_count 0, expires 2030 (not bookable — sold out).
      - expired_item       : remaining_count 5, expires 2020 (not bookable — expired,
                              despite having plenty of stock; proves expiration is
                              checked independently of remaining_count).
    """
    from datetime import datetime, timedelta

    from app.models import InventoryItem, Member

    available_member = Member(
        name="Available", surname="Member", booking_count=0, date_joined=datetime(2024, 1, 1)
    )
    at_limit_member = Member(
        name="AtLimit", surname="Member", booking_count=2, date_joined=datetime(2024, 1, 1)
    )
    over_limit_member = Member(
        name="OverLimit", surname="Member", booking_count=3, date_joined=datetime(2024, 1, 1)
    )
    available_item = InventoryItem(
        title="Bali", description="A trip", remaining_count=5, expiration_date=datetime(2030, 11, 19)
    )
    sold_out_item = InventoryItem(
        title="Route 66", description="Sold out", remaining_count=0, expiration_date=datetime(2030, 1, 1)
    )
    # A fixed past date would eventually become "not past" only in ~2020, which is
    # already behind us, but using `now - 1 day` keeps this fixture correct forever
    # regardless of when the test suite runs.
    expired_item = InventoryItem(
        title="Expired Trip",
        description="Past its expiration date",
        remaining_count=5,
        expiration_date=datetime.now() - timedelta(days=1),
    )

    db_session.add_all(
        [
            available_member,
            at_limit_member,
            over_limit_member,
            available_item,
            sold_out_item,
            expired_item,
        ]
    )
    db_session.commit()
    for row in (
        available_member,
        at_limit_member,
        over_limit_member,
        available_item,
        sold_out_item,
        expired_item,
    ):
        db_session.refresh(row)

    return {
        "available_member": available_member,
        "at_limit_member": at_limit_member,
        "over_limit_member": over_limit_member,
        "available_item": available_item,
        "sold_out_item": sold_out_item,
        "expired_item": expired_item,
    }
