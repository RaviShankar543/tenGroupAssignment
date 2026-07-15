"""Ten Lifestyle booking application package.

The `app` package contains the FastAPI application and all of its layers:

- `config`    : application settings (e.g. MAX_BOOKINGS).
- `database`  : SQLAlchemy engine, session factory, Base, and the get_db() dependency.
- `models`    : the ORM tables (Member, InventoryItem, Booking).
- `schemas`   : Pydantic request/response models for the JSON API.
- `services`  : the business rules (book_item, cancel_booking) — the single source of truth.
- `errors`    : domain exceptions raised by the service layer.
- `routes`    : thin transport adapters (JSON API + HTML form/page routes).

Both the JSON API and the HTML forms call the SAME service functions, so the
business rules are never duplicated across transports.
"""
