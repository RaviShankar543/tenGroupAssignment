# Ten Lifestyle Booking App

## Overview

A small web application that manages bookable inventory. It loads two provided
CSV files (`members.csv`, `inventory.csv`) into a SQL database, then exposes both a
**JSON API** and a **server-rendered web UI** for booking and cancelling inventory.
The business rules live in a single service layer that both the API and the UI call,
so the rules are never duplicated.

The goal is a clear, correct, easy-to-run take-home — not a production platform.

## Technology Choices

| Choice | Why |
|---|---|
| **FastAPI + Uvicorn** | Near-free request validation via Pydantic and an auto-generated interactive API page at `/docs`. |
| **SQLite + SQLAlchemy** | Zero-setup local database (a single file), no server or credentials to configure. |
| **Pydantic v2** | Declarative request/response validation and a self-documenting API contract. |
| **Jinja2 + plain CSS** | Server-rendered pages with no frontend build step. |
| **pytest + Starlette TestClient** | Fast, isolated tests against a temporary database. |

## Prerequisites

- **Python 3.11+** (developed and tested on 3.12).
- `pip` and the ability to create a virtual environment.

## Setup

Run these from the `booking-app/` directory.

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Loading the Data

Create the database schema and import both CSVs. `--reset` drops and recreates the
tables first, so it is safe to run repeatedly (idempotent):

```bash
python -m scripts.load_data --reset
```

Expected output:

```text
Loaded 45 members
Loaded 15 inventory items
Database ready at booking.db
```

## Running the Application

```bash
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/inventory   # inventory table with availability
http://127.0.0.1:8000/book        # booking + cancellation forms
http://127.0.0.1:8000/docs        # interactive API documentation (Swagger UI)
```

## Frontend Pages

- **`/inventory`** — a table of every item: title, description, remaining count,
  an **Available / Unavailable / Expired** badge, and expiration date. Sold-out
  and expired items stay visible (not hidden) so both availability rules are
  obvious. An item that is both sold out and expired shows **Expired** — the more
  specific reason.
- **`/book`** — a booking form (member + item dropdowns) and a cancellation form.
  - The member dropdown lists everyone alphabetically (first name, then surname)
    and shows each member's join date ("member since ...") so members who share
    the exact same name (the CSV has duplicates) are still distinguishable.
  - The item dropdown excludes **expired** items entirely (they cannot be booked);
    sold-out-but-not-expired items are still listed so the "no longer available"
    rule is demoable through the form.
  - Submissions use **Post-Redirect-Get**, so refreshing the page after booking
    does not double-book. Success and error messages appear near the top.

## API Usage

The JSON API lives under `/api/*`. Requests and responses use database **IDs**
because the CSVs contain duplicate member names and inventory titles.

**Book an item** — `POST /api/book`

```bash
curl -X POST http://127.0.0.1:8000/api/book \
  -H "Content-Type: application/json" \
  -d '{"member_id": 1, "inventory_item_id": 1}'
```

Success (`201 Created`):

```json
{
  "booking_reference": "BK-8F3A2C9D",
  "member_id": 1,
  "inventory_item_id": 1,
  "booked_at": "2026-07-15T10:30:00Z"
}
```

**Cancel a booking** — `POST /api/cancel`

```bash
curl -X POST http://127.0.0.1:8000/api/cancel \
  -H "Content-Type: application/json" \
  -d '{"member_id": 1, "booking_reference": "BK-8F3A2C9D"}'
```

Success (`200 OK`):

```json
{ "booking_reference": "BK-8F3A2C9D", "status": "cancelled", "cancelled_at": "2026-07-15T10:45:00Z" }
```

**Error shape.** Every failure returns `{ "error": "human-readable message" }`:

| Situation | Status |
|---|---|
| Missing / invalid field | 422 |
| Member or item not found | 404 |
| Booking not found | 404 |
| Member at the max booking limit | 409 |
| Item unavailable (sold out) | 409 |
| Item unavailable (expired) | 409 |
| Booking already cancelled | 409 |

> **Note on the brief:** the assignment names `POST /book` and `POST /cancel`. The
> JSON contract is exposed under `/api/book` and `/api/cancel`, and the bare
> `/book` / `/cancel` paths are reused for HTML **form** submissions. Both call the
> same service functions, so the brief's endpoints are fully covered.

## Running Tests

```bash
pytest
```

Tests run against a temporary SQLite database (never your real `booking.db`) and
cover CSV loading, the service-layer business rules, the HTTP API contract, and
HTML page rendering (member ordering/join date, expired-item filtering and
badges). **31 tests pass** as of the last run.

## Design Decisions and Trade-offs

- **Service layer as the single source of truth.** The JSON API and HTML forms are
  thin adapters over `app/services.py`; rules exist in exactly one place.
- **IDs, not names.** The CSVs have duplicate member names and inventory titles, so
  every payload/form value uses the surrogate database `id`.
- **`booking_count` is authoritative.** The imported value is treated as a live
  counter, incremented on booking and decremented on cancellation. Members whose
  imported count already meets or exceeds the limit simply cannot book.
- **`expiration_date` is enforced.** `InventoryItem.is_available` requires both
  stock (`remaining_count > 0`) and freshness (`not is_expired`). Expired items are
  blocked from booking (API and form), shown as **Expired** on `/inventory`
  (distinct from **Unavailable**), and excluded from the `/book` item dropdown.
  This was the MVP's original scope (display-only) until enforcement was
  explicitly requested; see `docs/decisions.md` for both entries.
- **Cancelled bookings are kept.** Cancellation sets `cancelled_at` rather than
  deleting the row, which keeps history easy to reason about.
- **SQLite + single transaction.** Check-then-decrement of availability runs in one
  transaction. SQLite serialises writes, which is correct here; production would
  move to PostgreSQL with row-level locking or optimistic versioning.

Full decision records are in [`docs/decisions.md`](docs/decisions.md).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'app'`** — run commands from the
  `booking-app/` directory, and use the module form: `python -m scripts.load_data`.
- **Virtual environment not active** — you should see `(.venv)` in your prompt;
  re-run the activate command for your OS.
- **PowerShell blocks activation** (`running scripts is disabled`) — run once:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate.
- **`Form data requires "python-multipart"`** — install dependencies
  (`pip install -r requirements.txt`); `python-multipart` is required for form POSTs.
- **Inventory/booking pages are empty** — you have not loaded data yet; run
  `python -m scripts.load_data --reset`.
- **`Address already in use` on port 8000** — another server is running; stop it or
  start on another port: `uvicorn app.main:app --port 8001`.
- **`pip install` SSL certificate error (corporate network)** — add the trusted
  hosts: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt`.

## Future Improvements

- PostgreSQL with Alembic migrations and row-level locking for concurrent bookings.
- Derive booking counts from active bookings instead of a mutable counter.
- Authentication/authorization and per-member ownership checks on cancel.
- Show "expires in N days" as a softer warning before the hard expiry cutoff, and/or
  let an admin extend an item's `expiration_date`.
- Audit logging, structured logging, and error monitoring.
- Pagination / search / autocomplete for the member and item dropdowns (45+ members
  and growing "member since ..." labels will get long for a plain `<select>`).
