"""Pydantic v2 request/response models for the JSON API.

These define the exact JSON contract for `/api/book` and `/api/cancel`:
- Request models validate incoming JSON (types, required fields) automatically.
  If validation fails, FastAPI returns 422 before our handler ever runs.
- Response models document and shape the JSON we return, and drive the schema
  shown on the interactive `/docs` page.

Keeping these separate from the SQLAlchemy models means the database schema and
the public API can evolve independently.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class BookRequest(BaseModel):
    """Body for POST /api/book. Uses database IDs (names/titles are not unique)."""

    member_id: int = Field(..., description="ID of the member making the booking")
    inventory_item_id: int = Field(..., description="ID of the item being booked")


class CancelRequest(BaseModel):
    """Body for POST /api/cancel.

    Requires the member_id as well as the reference so we can verify the booking
    belongs to that member (a light ownership check in the service layer).
    """

    member_id: int = Field(..., description="ID of the member who owns the booking")
    booking_reference: str = Field(..., description="Reference returned when booking, e.g. BK-8F3A2C9D")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
class BookResponse(BaseModel):
    """Success body for POST /api/book (returned with HTTP 201)."""

    booking_reference: str
    member_id: int
    inventory_item_id: int
    booked_at: datetime


class CancelResponse(BaseModel):
    """Success body for POST /api/cancel (returned with HTTP 200)."""

    booking_reference: str
    status: str  # always "cancelled" on success
    cancelled_at: datetime


class ErrorResponse(BaseModel):
    """Uniform error body: every failure returns `{ "error": "message" }`.

    Declared so the shape appears in the OpenAPI docs; the actual error responses
    are produced by the exception handlers in `main.py`.
    """

    error: str
