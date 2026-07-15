"""HTML page + form routes (server-rendered, Post-Redirect-Get).

Pages:
  GET  /            -> redirects to /inventory (friendly landing page)
  GET  /inventory   -> table of all inventory items and their availability
  GET  /bookings    -> active and cancelled bookings, with a per-row cancel button
  GET  /book        -> booking form (member + item dropdowns) and cancel form
  POST /book        -> handle a booking form submission, then redirect (PRG)
  POST /cancel      -> handle a cancellation form submission, then redirect (PRG)

Like the JSON API, these routes are thin adapters over `app.services`; they never
reimplement business rules.

Post-Redirect-Get (PRG): after handling a POST we issue a 303 redirect to a GET
page, passing a short status via query-string parameters. This means refreshing
the results page re-runs a harmless GET instead of re-submitting the form (which
would otherwise double-book).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import MAX_BOOKINGS
from app.database import get_db
from app.errors import BookingError
from app.models import Booking, InventoryItem, Member
from app import services

# Jinja2 templates live in app/templates. This object renders them to HTML.
# We compute the path relative to this file so it works regardless of CWD.
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web"])


# ---------------------------------------------------------------------------
# Small helpers to load the data the templates need
# ---------------------------------------------------------------------------
def _all_items(db: Session) -> list[InventoryItem]:
    """Return EVERY inventory item (including sold-out and expired), ordered by id.

    Used by the /inventory table, which must show every item — including expired
    ones flagged "Expired" — so the availability rules are visible, not hidden.
    Do NOT reuse this for the booking dropdown; use `_bookable_items()` instead.
    """
    return list(db.scalars(select(InventoryItem).order_by(InventoryItem.id)))


def _bookable_items(db: Session) -> list[InventoryItem]:
    """Return only items that are NOT expired, for the /book item dropdown.

    Expired items must not be selectable when creating a new booking. We still
    include sold-out (but not expired) items here — deliberately unchanged from
    before — so a user can pick one and see the service layer's clear
    "no longer available" error, which is useful for demoing that rule.

    `is_expired` is a Python property (derived from `datetime.now()`), not a SQL
    column, so it cannot be pushed into the `WHERE` clause; filtering in Python
    after the (small, ~15-row) fetch is simpler and fast enough at this scale.
    """
    return [item for item in _all_items(db) if not item.is_expired]


def _all_members(db: Session) -> list[Member]:
    """Return every member, ordered alphabetically by first name then surname.

    `id` is kept as a final tiebreaker so the order is fully deterministic even
    for members who share both name AND surname. Sorting happens in SQL (not
    Python) so it works the same way regardless of dataset size.

    Note: members.csv has duplicate (name, surname) pairs, so alphabetical order
    alone cannot tell two such members apart in a dropdown — see
    `Member.joined_display`, rendered alongside the name in booking.html, for the
    human-readable disambiguator. The value actually submitted by the form is
    still the unambiguous `id`.
    """
    return list(db.scalars(select(Member).order_by(Member.name, Member.surname, Member.id)))


def _bookings(db: Session, *, cancelled: bool) -> list[Booking]:
    """Return bookings made through this app, split by active vs cancelled.

    `cancelled=False` returns active bookings (`cancelled_at IS NULL`) ordered by
    most-recently created; `cancelled=True` returns cancelled bookings ordered by
    most-recently cancelled. `member` and `item` are eager-loaded (joinedload) so
    the template can show human-readable names without triggering a query per row.
    """
    condition = Booking.cancelled_at.isnot(None) if cancelled else Booking.cancelled_at.is_(None)
    order = Booking.cancelled_at.desc() if cancelled else Booking.created_at.desc()
    stmt = (
        select(Booking)
        .where(condition)
        .order_by(order)
        .options(joinedload(Booking.member), joinedload(Booking.item))
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# GET pages
# ---------------------------------------------------------------------------
@router.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """Landing route: send visitors straight to the inventory page."""
    return RedirectResponse(url="/inventory", status_code=303)


@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Render the inventory table. Sold-out items are shown but flagged unavailable."""
    # Current Starlette expects `request` as the first positional argument to
    # TemplateResponse (the older name-first signature is removed).
    return templates.TemplateResponse(
        request,
        "inventory.html",
        {"items": _all_items(db)},
    )


@router.get("/bookings", response_class=HTMLResponse)
def bookings_page(
    request: Request,
    db: Session = Depends(get_db),
    # PRG "flash" params, populated by the redirect after a /cancel POST.
    status: str | None = None,
    message: str | None = None,
) -> HTMLResponse:
    """List active and cancelled bookings, with a cancel button on active rows.

    This gives a way to cancel from the UI without knowing the booking reference
    up front: each active row already carries its member id and reference, so the
    per-row form can post them straight to /cancel.
    """
    return templates.TemplateResponse(
        request,
        "bookings.html",
        {
            "active_bookings": _bookings(db, cancelled=False),
            "cancelled_bookings": _bookings(db, cancelled=True),
            "flash_status": status,
            "flash_message": message,
        },
    )


@router.get("/book", response_class=HTMLResponse)
def book_page(
    request: Request,
    db: Session = Depends(get_db),
    # These optional query params carry the PRG "flash" message after a POST.
    status: str | None = None,
    message: str | None = None,
    reference: str | None = None,
) -> HTMLResponse:
    """Render the booking form plus a cancellation form.

    The `status`/`message`/`reference` query params are populated by the redirect
    that follows a POST, so the user sees a confirmation or error after submitting.
    """
    return templates.TemplateResponse(
        request,
        "booking.html",
        {
            "members": _all_members(db),
            # Expired items are excluded here (but still shown on /inventory).
            "items": _bookable_items(db),
            "max_bookings": MAX_BOOKINGS,
            # Flash-style feedback: "success" or "error" (or None on first load).
            "flash_status": status,
            "flash_message": message,
            "flash_reference": reference,
        },
    )


# ---------------------------------------------------------------------------
# POST form handlers (Post-Redirect-Get)
# ---------------------------------------------------------------------------
@router.post("/book")
def book_form(
    member_id: int = Form(...),
    inventory_item_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle a booking form submission and redirect back to /book with feedback.

    We call the SAME `services.book_item` the JSON API uses. Any BookingError is
    caught here (rather than bubbling to the JSON exception handler) and turned
    into a friendly, human-readable message on the redirected page.
    """
    try:
        booking = services.book_item(
            db, member_id=member_id, inventory_item_id=inventory_item_id
        )
        # Success: pass the reference so the page can confirm it.
        params = _encode_flash(
            status="success",
            message=f"Booking confirmed. Your reference is {booking.reference}.",
            reference=booking.reference,
        )
    except BookingError as exc:
        # Expected business failure: show its safe message.
        params = _encode_flash(status="error", message=exc.message)

    # 303 See Other turns the POST into a follow-up GET (the core of PRG).
    return RedirectResponse(url=f"/book?{params}", status_code=303)


@router.post("/cancel")
def cancel_form(
    member_id: int = Form(...),
    booking_reference: str = Form(...),
    # Which page the form was submitted from, so we redirect back to it. Only a
    # small allow-list is honoured (see `_safe_next`) to avoid an open redirect.
    next: str = Form("/book"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle a cancellation form submission and redirect back with feedback.

    Both the /book cancel form and the per-row cancel buttons on /bookings post
    here; the hidden `next` field decides which page we return to (PRG).
    """
    try:
        booking = services.cancel_booking(
            db, member_id=member_id, booking_reference=booking_reference.strip()
        )
        params = _encode_flash(
            status="success",
            message=f"Booking {booking.reference} has been cancelled.",
        )
    except BookingError as exc:
        params = _encode_flash(status="error", message=exc.message)

    return RedirectResponse(url=f"{_safe_next(next)}?{params}", status_code=303)


def _safe_next(next_url: str) -> str:
    """Return `next_url` only if it is a known internal page, else `/book`.

    Restricting to an allow-list keeps this from becoming an open-redirect: the
    value comes from a form field, so we never reflect an arbitrary destination.
    """
    return next_url if next_url in {"/book", "/bookings"} else "/book"


def _encode_flash(status: str, message: str, reference: str | None = None) -> str:
    """URL-encode the flash fields into a query string for the PRG redirect."""
    from urllib.parse import urlencode

    data = {"status": status, "message": message}
    if reference:
        data["reference"] = reference
    return urlencode(data)
