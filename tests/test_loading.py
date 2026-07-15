"""Tests for CSV import behaviour.

We exercise the real loader functions (`_load_members` / `_load_inventory`) against
the actual data/*.csv files, but insert into an isolated temporary database via the
`db_session` fixture. This verifies the row counts and the tricky data-cleaning
rules (BOM handling, whitespace stripping, duplicate rows) without touching the
developer's real booking.db.
"""

from app.models import InventoryItem, Member
from scripts.load_data import _load_inventory, _load_members


def test_members_csv_loads_all_rows(db_session):
    """All 45 members import; the BOM does not corrupt the first row."""
    count = _load_members(db_session)
    db_session.commit()

    assert count == 45
    assert db_session.query(Member).count() == 45


def test_member_whitespace_is_stripped(db_session):
    """The dirty value " James  " is stored stripped as "James"."""
    _load_members(db_session)
    db_session.commit()

    # There should be exactly one member named "James" (stripped), and none with
    # surrounding whitespace still attached.
    james = db_session.query(Member).filter(Member.name == "James").all()
    assert len(james) == 1
    assert james[0].name == "James"


def test_inventory_csv_loads_all_rows(db_session):
    """All 15 inventory items import."""
    count = _load_inventory(db_session)
    db_session.commit()

    assert count == 15
    assert db_session.query(InventoryItem).count() == 15


def test_duplicate_inventory_titles_both_present(db_session):
    """Both "London" rows import (duplicate titles are allowed; ids disambiguate)."""
    _load_inventory(db_session)
    db_session.commit()

    londons = db_session.query(InventoryItem).filter(InventoryItem.title == "London").all()
    assert len(londons) == 2
    # The two rows differ in remaining_count (2 and 1), proving they are distinct.
    assert {item.remaining_count for item in londons} == {2, 1}


def test_sold_out_item_imported_with_zero(db_session):
    """Route 66 imports with remaining_count == 0 (stays visible, not bookable)."""
    _load_inventory(db_session)
    db_session.commit()

    route66 = db_session.query(InventoryItem).filter(InventoryItem.title == "Route 66").one()
    assert route66.remaining_count == 0
