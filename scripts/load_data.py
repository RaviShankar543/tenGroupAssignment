"""Create the database schema and load the CSV data into SQLite.

Run from the project root as a module so the `app` package imports cleanly:

    python -m scripts.load_data            # load into existing (possibly empty) tables
    python -m scripts.load_data --reset    # drop + recreate tables first (idempotent)

Why the quirks below matter (they are deliberate talking points):
  * encoding="utf-8-sig"  -> strips the UTF-8 BOM so the first CSV header is
    "title"/"name" and not "\ufefftitle".
  * name/surname .strip() -> the members CSV contains dirty values like " James  ".
  * two date formats      -> members.date_joined is ISO datetime; inventory
    expiration_date is DD/MM/YYYY. Each is parsed with the correct format.
  * surrogate ids only    -> duplicate names/titles mean we never key off them; the
    auto-increment id (assigned by the database) is the identifier.
"""

import argparse
import csv
import sys

from datetime import datetime
from pathlib import Path

# `python -m scripts.load_data` runs with the project root on sys.path, so these
# absolute imports of the `app` package resolve correctly.
from app.config import DATA_DIR
from app.database import Base, SessionLocal, engine
from app.models import InventoryItem, Member

# Expected CSV files (copied from the assignment artifacts into data/).
MEMBERS_CSV = DATA_DIR / "members.csv"
INVENTORY_CSV = DATA_DIR / "inventory.csv"

# Columns each CSV must contain; validated before loading so a malformed file
# fails fast with a clear message instead of a confusing KeyError later.
REQUIRED_MEMBER_COLUMNS = {"name", "surname", "booking_count", "date_joined"}
REQUIRED_INVENTORY_COLUMNS = {"title", "description", "remaining_count", "expiration_date"}


def _validate_columns(path: Path, header: list[str] | None, required: set[str]) -> None:
    """Abort with a clear message if the CSV header is missing required columns."""
    present = set(header or [])
    missing = required - present
    if missing:
        raise SystemExit(
            f"ERROR: {path.name} is missing required column(s): {', '.join(sorted(missing))}"
        )


def _load_members(db) -> int:
    """Read members.csv and insert one Member row per line. Returns the count."""
    if not MEMBERS_CSV.exists():
        raise SystemExit(f"ERROR: {MEMBERS_CSV} not found. Did you copy the CSVs into data/?")

    count = 0
    # utf-8-sig removes the BOM; newline="" is the csv module's recommended setting.
    with open(MEMBERS_CSV, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        _validate_columns(MEMBERS_CSV, reader.fieldnames, REQUIRED_MEMBER_COLUMNS)

        for row in reader:
            member = Member(
                # Strip whitespace-dirty values such as " James  ".
                name=row["name"].strip(),
                surname=row["surname"].strip(),
                # booking_count is authoritative and imported as-is (some are >= 2/3).
                booking_count=int(row["booking_count"]),
                # date_joined is an ISO 8601 datetime string.
                date_joined=datetime.fromisoformat(row["date_joined"].strip()),
            )
            db.add(member)
            count += 1

    return count


def _load_inventory(db) -> int:
    """Read inventory.csv and insert one InventoryItem row per line. Returns the count."""
    if not INVENTORY_CSV.exists():
        raise SystemExit(f"ERROR: {INVENTORY_CSV} not found. Did you copy the CSVs into data/?")

    count = 0
    with open(INVENTORY_CSV, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        _validate_columns(INVENTORY_CSV, reader.fieldnames, REQUIRED_INVENTORY_COLUMNS)

        for row in reader:
            item = InventoryItem(
                title=row["title"].strip(),
                description=row["description"].strip(),
                # Some items legitimately have remaining_count == 0 (e.g. Route 66).
                remaining_count=int(row["remaining_count"]),
                # expiration_date is DD/MM/YYYY (NOT ISO) — parse with an explicit format.
                expiration_date=datetime.strptime(row["expiration_date"].strip(), "%d/%m/%Y"),
            )
            db.add(item)
            count += 1

    return count


def _reset_schema() -> None:
    """Drop all tables and recreate them, giving a clean, idempotent import."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, (optionally) reset, load both CSVs, print a summary."""
    parser = argparse.ArgumentParser(description="Load CSV data into the booking database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before loading (makes the import idempotent).",
    )
    args = parser.parse_args(argv)

    # With --reset we start from a clean schema. Without it, ensure tables exist and
    # refuse to double-load if data is already present (keeps counts correct).
    if args.reset:
        _reset_schema()
    else:
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Guard against accidental duplicate loads when --reset was not passed.
        if not args.reset and db.query(Member).count() > 0:
            raise SystemExit(
                "Data already present. Re-run with --reset to reload from scratch."
            )

        members_loaded = _load_members(db)
        inventory_loaded = _load_inventory(db)
        # Single commit so the whole import is atomic.
        db.commit()
    finally:
        db.close()

    # Human-friendly summary, matching the format described in the project plan.
    print(f"Loaded {members_loaded} members")
    print(f"Loaded {inventory_loaded} inventory items")
    print("Database ready at booking.db")


if __name__ == "__main__":
    # Delegate to main(); SystemExit messages surface as clean CLI errors.
    main(sys.argv[1:])
