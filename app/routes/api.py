"""JSON API routes: POST /api/book and POST /api/cancel.

These handlers are intentionally THIN. Their only jobs are:
  1. Receive validated request data (Pydantic did the validation).
  2. Call the matching service function.
  3. Shape the successful result into the response model.

They do NOT contain business rules and they do NOT catch domain exceptions — a
raised BookingError propagates to the single exception handler registered in
`main.py`, which turns it into the correct `{ "error": ... }` response and status
code. This keeps error-to-HTTP mapping in exactly one place.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.schemas import (
    BookRequest,
    BookResponse,
    CancelRequest,
    CancelResponse,
    ErrorResponse,
)

# All routes in this module are prefixed with /api and grouped under "API" in /docs.
router = APIRouter(prefix="/api", tags=["API"])


@router.post(
    "/book",
    response_model=BookResponse,
    status_code=status.HTTP_201_CREATED,
    # Documenting the possible error responses makes the /docs page self-explanatory.
    responses={
        404: {"model": ErrorResponse, "description": "Member or item not found"},
        409: {"model": ErrorResponse, "description": "Limit reached or item unavailable"},
    },
)
def book(payload: BookRequest, db: Session = Depends(get_db)) -> BookResponse:
    """Create a booking. Returns 201 with the booking reference on success."""
    booking = services.book_item(
        db,
        member_id=payload.member_id,
        inventory_item_id=payload.inventory_item_id,
    )
    return BookResponse(
        booking_reference=booking.reference,
        member_id=booking.member_id,
        inventory_item_id=booking.inventory_item_id,
        booked_at=booking.created_at,
    )


@router.post(
    "/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "Booking not found"},
        409: {"model": ErrorResponse, "description": "Booking already cancelled"},
    },
)
def cancel(payload: CancelRequest, db: Session = Depends(get_db)) -> CancelResponse:
    """Cancel an active booking. Returns 200 with the cancellation time on success."""
    booking = services.cancel_booking(
        db,
        member_id=payload.member_id,
        booking_reference=payload.booking_reference,
    )
    return CancelResponse(
        booking_reference=booking.reference,
        status="cancelled",
        cancelled_at=booking.cancelled_at,
    )
