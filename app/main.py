"""FastAPI application entry point.

Responsibilities of this module (and only these):
  1. Create the single FastAPI `app` instance.
  2. Mount static files and register the route modules (API + web pages).
  3. Register exception handlers that convert domain/validation errors into the
     uniform `{ "error": "..." }` JSON contract with correct status codes.
  4. Expose a tiny `/health` endpoint for quick "is it up?" checks.

Run locally with:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.errors import BookingError
from app.routes import api, pages

# Create the FastAPI app. The title/description show up on the interactive /docs page.
app = FastAPI(
    title="Ten Lifestyle Booking App",
    description=(
        "Manages bookable inventory with a JSON API and a server-rendered UI. "
        "Business rules live in a shared service layer used by both transports."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------
# Ensure the tables exist when the app starts. This is a safety net so the app can
# run even before `scripts/load_data.py` is executed (the pages will simply be
# empty). `create_all` is a no-op for tables that already exist, so it is safe.
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Static files (CSS)
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# The web pages (HTML) and the JSON API (/api/*) are registered separately.
app.include_router(pages.router)
app.include_router(api.router)


# ---------------------------------------------------------------------------
# Exception handlers — map errors to the uniform JSON contract
# ---------------------------------------------------------------------------
@app.exception_handler(BookingError)
async def handle_booking_error(request: Request, exc: BookingError) -> JSONResponse:
    """Turn any domain exception into `{ "error": message }` with its status code.

    Because each BookingError subclass carries its own `status_code`, this single
    handler covers every current and future business error consistently. No stack
    traces or internal exception names ever reach the client.
    """
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return malformed/invalid JSON bodies as a clean 422 in our `{ "error": ... }` shape.

    FastAPI's default validation response is a verbose list; we collapse it into a
    single readable message so API clients get the same error shape everywhere.
    (422 is the standard code for a well-formed request that fails validation and
    is explicitly accepted by the API contract.)
    """
    # Summarise the first validation problem into a short, readable sentence.
    first = exc.errors()[0] if exc.errors() else None
    if first:
        location = " -> ".join(str(part) for part in first.get("loc", []))
        message = f"Invalid request: {first.get('msg', 'validation error')} ({location})"
    else:
        message = "Invalid request"
    # Use the literal 422 rather than the framework constant, whose name is being
    # renamed across Starlette versions (avoids a deprecation warning).
    return JSONResponse(status_code=422, content={"error": message})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Web"])
def health() -> dict:
    """Lightweight liveness probe: returns `{"status": "ok"}` when the app is up."""
    return {"status": "ok"}
