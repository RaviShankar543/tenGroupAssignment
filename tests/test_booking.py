"""Service-layer tests: the business rules in `services.py`.

These call the service functions directly (no HTTP) against the isolated
`db_session` + `seed_basic` fixtures, so they verify the rules precisely and fast.
"""

import pytest

from app.errors import (
    BookingAlreadyCancelled,
    BookingLimitReached,
    BookingNotFound,
    InventoryItemNotFound,
    ItemUnavailable,
    MemberNotFound,
)
from app.services import book_item, cancel_booking


def test_successful_booking_updates_counters(db_session, seed_basic):
    """A valid booking returns a reference, +1 member count, -1 item remaining."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]
    member_start = member.booking_count
    item_start = item.remaining_count

    booking = book_item(db_session, member.id, item.id)

    assert booking.reference.startswith("BK-")
    assert member.booking_count == member_start + 1
    assert item.remaining_count == item_start - 1
    assert booking.cancelled_at is None


def test_member_at_max_is_rejected(db_session, seed_basic):
    """A member with booking_count == MAX_BOOKINGS (2) is blocked."""
    member = seed_basic["at_limit_member"]
    item = seed_basic["available_item"]

    with pytest.raises(BookingLimitReached):
        book_item(db_session, member.id, item.id)


def test_member_above_max_is_rejected(db_session, seed_basic):
    """A member whose imported count exceeds the cap (3) is also blocked."""
    member = seed_basic["over_limit_member"]
    item = seed_basic["available_item"]

    with pytest.raises(BookingLimitReached):
        book_item(db_session, member.id, item.id)


def test_sold_out_item_is_rejected(db_session, seed_basic):
    """Booking an item with remaining_count == 0 raises ItemUnavailable."""
    member = seed_basic["available_member"]
    item = seed_basic["sold_out_item"]

    with pytest.raises(ItemUnavailable):
        book_item(db_session, member.id, item.id)


def test_expired_item_is_rejected(db_session, seed_basic):
    """Booking an item whose expiration_date has passed raises ItemUnavailable,
    even though it still has plenty of remaining_count (5) — proving expiration
    is enforced independently of stock."""
    member = seed_basic["available_member"]
    item = seed_basic["expired_item"]

    with pytest.raises(ItemUnavailable):
        book_item(db_session, member.id, item.id)


def test_expired_item_error_message_mentions_expiry(db_session, seed_basic):
    """The rejection message names "expired" specifically, not the generic
    sold-out message, so the caller gets the real reason."""
    member = seed_basic["available_member"]
    item = seed_basic["expired_item"]

    with pytest.raises(ItemUnavailable, match="expired"):
        book_item(db_session, member.id, item.id)


def test_unknown_member_raises(db_session, seed_basic):
    """A non-existent member id raises MemberNotFound."""
    item = seed_basic["available_item"]
    with pytest.raises(MemberNotFound):
        book_item(db_session, 999999, item.id)


def test_unknown_item_raises(db_session, seed_basic):
    """A non-existent item id raises InventoryItemNotFound."""
    member = seed_basic["available_member"]
    with pytest.raises(InventoryItemNotFound):
        book_item(db_session, member.id, 999999)


def test_cancel_active_booking_reverses_counters(db_session, seed_basic):
    """Cancelling sets cancelled_at, -1 member count, +1 item remaining."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    booking = book_item(db_session, member.id, item.id)
    count_after_book = member.booking_count
    remaining_after_book = item.remaining_count

    cancelled = cancel_booking(db_session, member.id, booking.reference)

    assert cancelled.cancelled_at is not None
    assert member.booking_count == count_after_book - 1
    assert item.remaining_count == remaining_after_book + 1


def test_cancel_twice_is_rejected(db_session, seed_basic):
    """A second cancellation of the same booking raises BookingAlreadyCancelled."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    booking = book_item(db_session, member.id, item.id)
    cancel_booking(db_session, member.id, booking.reference)

    with pytest.raises(BookingAlreadyCancelled):
        cancel_booking(db_session, member.id, booking.reference)


def test_cancel_unknown_reference_raises(db_session, seed_basic):
    """Cancelling an unknown reference raises BookingNotFound."""
    member = seed_basic["available_member"]
    with pytest.raises(BookingNotFound):
        cancel_booking(db_session, member.id, "BK-DOESNOT")


def test_cancel_wrong_member_raises(db_session, seed_basic):
    """Cancelling with a mismatched member (ownership check) raises BookingNotFound."""
    member = seed_basic["available_member"]
    other = seed_basic["over_limit_member"]
    item = seed_basic["available_item"]

    booking = book_item(db_session, member.id, item.id)

    with pytest.raises(BookingNotFound):
        cancel_booking(db_session, other.id, booking.reference)
