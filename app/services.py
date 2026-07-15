"""Business logic — the SINGLE source of truth for booking rules.

Both the JSON API (`routes/api.py`) and the HTML form routes (`routes/pages.py`)
call these two functions. The rules are therefore implemented exactly once, which
is the central architectural decision of this project.

Each function:
- takes an active SQLAlchemy `Session` (the caller owns its lifecycle),
- validates the business rules,
- raises a domain exception from `errors.py` if a rule is violated,
- performs all its writes inside a single transaction (one `commit`) so the
  operation is atomic — either everything succeeds or nothing changes.
"""

import uuid

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MAX_BOOKINGS
from app.errors import (
    BookingAlreadyCancelled,
    BookingLimitReached,
    BookingNotFound,
    InventoryItemNotFound,
    ItemUnavailable,
    MemberNotFound,
)
from app.models import Booking, InventoryItem, Member


def _generate_reference() -> str:
    """Generate a short, unique, human-quotable booking reference.

    Format: "BK-" followed by 8 uppercase hex characters, e.g. "BK-8F3A2C9D".
    A uuid4 gives us plenty of entropy; 8 hex chars keep it easy to read out over
    the phone while collisions remain vanishingly unlikely at this scale. The
    `reference` column is also UNIQUE, so a (practically impossible) collision
    would surface as a database error rather than a silent overwrite.
    """
    return "BK-" + uuid.uuid4().hex[:8].upper()


def book_item(db: Session, member_id: int, inventory_item_id: int) -> Booking:
    """Create a booking for `member_id` against `inventory_item_id`.

    Business rules (in order):
      1. The member must exist.
      2. The inventory item must exist.
      3. The member must be below MAX_BOOKINGS.
      4. The item must have remaining availability AND not be expired
         (`InventoryItem.is_available` — see models.py — combines both checks so
         this stays the single source of truth; the UI filters expired items out
         of the booking dropdown too, but this check is what actually protects
         the JSON API, which a client could call directly with any item id).

    On success it creates a Booking row, increments the member's booking_count,
    decrements the item's remaining_count, and commits all three changes together.

    Returns the newly created (and refreshed) Booking.
    Raises: MemberNotFound, InventoryItemNotFound, BookingLimitReached, ItemUnavailable.
    """
    # 1. Load the member; a missing member is a 404-style domain error.
    member = db.get(Member, member_id)
    if member is None:
        raise MemberNotFound()

    # 2. Load the inventory item; a missing item is likewise a 404-style error.
    item = db.get(InventoryItem, inventory_item_id)
    if item is None:
        raise InventoryItemNotFound()

    # 3. Enforce the per-member cap. Using >= (not ==) also correctly blocks members
    #    whose imported booking_count already exceeds the cap (e.g. 3).
    if member.booking_count >= MAX_BOOKINGS:
        raise BookingLimitReached()

    # 4. Enforce availability. Check expiration FIRST so the error message tells
    #    the caller the real reason (an expired item might coincidentally also be
    #    sold out, but "expired" is the more specific and more useful fact).
    if item.is_expired:
        raise ItemUnavailable("This item has expired and can no longer be booked")
    if item.remaining_count <= 0:
        raise ItemUnavailable()

    # All rules pass — create the booking and update the two counters.
    booking = Booking(
        reference=_generate_reference(),
        member_id=member.id,
        inventory_item_id=item.id,
        created_at=datetime.now(timezone.utc),
    )
    member.booking_count += 1
    item.remaining_count -= 1

    # Persist everything atomically: the new row and both counter updates are part
    # of the same transaction, so a failure cannot leave the counters inconsistent.
    db.add(booking)
    db.commit()

    # Refresh so auto-generated fields (id, defaults) are populated on the returned object.
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, member_id: int, booking_reference: str) -> Booking:
    """Cancel the booking identified by `member_id` + `booking_reference`.

    Business rules:
      1. A booking with that reference must exist AND belong to that member.
         (Requiring the member_id to match is a light ownership check so one member
         cannot cancel another member's booking by guessing a reference.)
      2. The booking must not already be cancelled.

    On success it stamps `cancelled_at`, decrements the member's booking_count
    (never below zero as a safety net), increments the item's remaining_count, and
    commits all changes together.

    Returns the updated Booking.
    Raises: BookingNotFound, BookingAlreadyCancelled.
    """
    # 1. Find the booking by reference AND member. A mismatch on either looks the
    #    same to the caller ("Booking not found") so we don't leak whether a
    #    reference exists for a different member.
    booking = db.scalar(
        select(Booking).where(
            Booking.reference == booking_reference,
            Booking.member_id == member_id,
        )
    )
    if booking is None:
        raise BookingNotFound()

    # 2. Reject double-cancellation. `cancelled_at` being set means it's already done.
    if booking.cancelled_at is not None:
        raise BookingAlreadyCancelled()

    # Perform the cancellation and reverse the counters that book_item changed.
    booking.cancelled_at = datetime.now(timezone.utc)

    member = db.get(Member, booking.member_id)
    if member is not None:
        # max(..., 0) guards against ever driving the counter negative even if the
        # data were somehow inconsistent.
        member.booking_count = max(member.booking_count - 1, 0)

    item = db.get(InventoryItem, booking.inventory_item_id)
    if item is not None:
        item.remaining_count += 1

    # Commit the cancellation and both counter reversals in one transaction.
    db.commit()
    db.refresh(booking)
    return booking
