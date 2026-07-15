"""SQLAlchemy ORM models: Member, InventoryItem, Booking.

Design notes (important for the interview):

- Both `members` and `inventory_items` use a surrogate auto-increment `id` as the
  primary key. The source CSVs contain DUPLICATE member names (e.g. "Grace Miller"
  twice) and DUPLICATE inventory titles (e.g. "London" twice), so a natural key
  would be ambiguous. Every API payload and form value therefore uses the `id`.

- `booking_count` on Member is treated as an AUTHORITATIVE stored counter: it is
  imported from the CSV and then incremented/decremented as bookings are made and
  cancelled. (An alternative "legacy offset + derived active count" model is
  discussed in docs/decisions.md.)

- Bookings are never deleted. A cancellation sets `cancelled_at`; an active booking
  is one where `cancelled_at IS NULL`. Keeping history makes the data easier to
  reason about and to demo.

- `InventoryItem.is_available` requires BOTH `remaining_count > 0` AND
  `not is_expired`. Expiration enforcement was added on 2026-07-15 (see
  docs/decisions.md), superseding the earlier "display-only" MVP decision.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Defined once so every timestamp in the app is created the same way. We use
    timezone-aware UTC (not the deprecated naive `datetime.utcnow()`) so that
    stored and serialised times are unambiguous.
    """
    return datetime.now(timezone.utc)


# Human-friendly date format shared by every "long date" display in the UI, e.g.
# "01 July 2026". Centralised here so the member "member since ..." label and any
# future date-display code stay consistent.
_DISPLAY_DATE_FORMAT = "%d %B %Y"


class Member(Base):
    """A person who can book inventory items."""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Name/surname are stored stripped of surrounding whitespace (the CSV contains
    # dirty values such as " James  "). They are intentionally NOT unique.
    name: Mapped[str] = mapped_column(String, nullable=False)
    surname: Mapped[str] = mapped_column(String, nullable=False)

    # Authoritative counter of the member's current bookings. Imported from the CSV
    # and mutated by the service layer on book/cancel. Some members legitimately
    # start at or above MAX_BOOKINGS and simply cannot book until they cancel.
    booking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # When the member joined, parsed from the CSV's ISO datetime string.
    date_joined: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Audit field: when this row was inserted into our database.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Convenience relationship to this member's bookings (active and cancelled).
    bookings: Mapped[list["Booking"]] = relationship(back_populates="member")

    @property
    def full_name(self) -> str:
        """Human-friendly "Name Surname" used in dropdown labels and templates."""
        return f"{self.name} {self.surname}"

    @property
    def joined_display(self) -> str:
        """`date_joined` formatted as "01 July 2026" for dropdown labels.

        `members.csv` has duplicate (name, surname) pairs (project rule: names are
        NEVER unique identifiers), so a dropdown showing only "Jane Doe" twice would
        be impossible for a user to tell apart. Appending the join date ("member
        since ...") to every option gives a human-readable disambiguator even though
        the value actually submitted by the form is still the unambiguous `id`.
        """
        return self.date_joined.strftime(_DISPLAY_DATE_FORMAT)


class InventoryItem(Base):
    """A bookable item of inventory (e.g. a trip)."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Title is NOT unique — "London" appears twice with different availability/dates.
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # How many of this item are still bookable. Decremented on booking, incremented
    # on cancellation. An item with 0 remaining stays visible but is not bookable.
    remaining_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Parsed from the CSV's DD/MM/YYYY format (naive datetime, time component is
    # always midnight). ENFORCED as of the 2026-07-15 decision below: expired items
    # are blocked from booking, not just displayed. See docs/decisions.md.
    expiration_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Audit field: when this row was inserted into our database.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Convenience relationship to bookings made against this item.
    bookings: Mapped[list["Booking"]] = relationship(back_populates="item")

    @property
    def is_expired(self) -> bool:
        """True once `expiration_date` has passed.

        Compared by CALENDAR DATE (not exact datetime) because `expiration_date`
        only ever carries a date (its time component is always midnight, an
        artefact of the DD/MM/YYYY CSV format). Comparing `.date()` to `.date()`
        also sidesteps any naive-vs-timezone-aware datetime comparison error,
        since `expiration_date` has no tzinfo but `_utcnow()` does.
        """
        return self.expiration_date.date() < _utcnow().date()

    @property
    def is_available(self) -> bool:
        """True when the item can be booked right now.

        Two independent conditions must BOTH hold:
          1. Stock: at least one unit remains (`remaining_count > 0`).
          2. Freshness: the item has not expired (`not is_expired`).
        This single property is the one place both rules are combined, so
        `services.book_item()` and every template stay in sync automatically —
        neither has to remember to check expiration separately.
        """
        return self.remaining_count > 0 and not self.is_expired


class Booking(Base):
    """A single booking made through THIS application.

    Only bookings created here have a `reference`, which is why only these bookings
    can be cancelled — pre-import bookings represented by the CSV `booking_count`
    have no reference and are out of scope for cancellation.
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Public, human-quotable identifier returned to the caller, e.g. "BK-8F3A2C9D".
    # Unique so it unambiguously identifies one booking.
    reference: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Foreign keys tie the booking to a member and an inventory item.
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=False
    )

    # When the booking was created (UTC).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # NULL while the booking is active; set to the UTC cancellation time when
    # cancelled. We keep the row rather than deleting it.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships back to the parent rows.
    member: Mapped["Member"] = relationship(back_populates="bookings")
    item: Mapped["InventoryItem"] = relationship(back_populates="bookings")

    @property
    def is_active(self) -> bool:
        """True when the booking has not been cancelled."""
        return self.cancelled_at is None
