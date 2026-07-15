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

- **Python 3.11+** (developed and tested on 3.12) — this is the *only* thing you
  need to install. Everything else (the web server, the database, the frontend)
  is a Python library installed into a local virtual environment in the next
  step. No Docker, no Node.js, no PostgreSQL/MySQL server, and no system-wide
  package installs are required.
- `pip` and the standard library's `venv` module. Both ship with Python on
  Windows and macOS. On some Linux distributions (Debian/Ubuntu) `venv` is a
  separate package — see Troubleshooting below if `python -m venv` fails.

**Check whether Python is already installed** by opening a terminal
(Command Prompt/PowerShell on Windows, Terminal on macOS/Linux) and running:

```bash
python --version
```

If that prints `Python 3.11` or higher, you're set — use `python` in the
commands below. If it prints an error, or a version below 3.11, try:

```bash
python3 --version
```

If `python3` works instead, substitute `python3` for `python` in every command
below (this is common on macOS and Linux). If neither command works, install
Python from [python.org/downloads](https://www.python.org/downloads/) (check
"Add Python to PATH" during install on Windows), then re-open your terminal and
try again.

## Getting the Code

Download or clone this repository, then locate the `booking-app/` folder — it
is the project root and contains this `README.md`, an `app/` folder, a
`data/` folder (with `members.csv` and `inventory.csv`), and a
`requirements.txt`. **All commands below must be run from inside
`booking-app/`.**

```bash
cd booking-app
```

## Setup

Run these from the `booking-app/` directory. This creates an isolated Python
environment (`.venv/`) inside the project folder and installs the exact
libraries this app needs (FastAPI, Uvicorn, SQLAlchemy, Jinja2, pytest, etc.
— see `requirements.txt`) without touching anything else on your machine.

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

**Windows Command Prompt (cmd.exe)**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

After activation, your prompt should be prefixed with `(.venv)`. Every command
in the rest of this README assumes the virtual environment is active — if you
close and reopen your terminal, re-run the activate line (not the whole setup)
before continuing.

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
http://127.0.0.1:8000/bookings    # active + cancelled bookings, cancel per row
http://127.0.0.1:8000/book        # booking + cancellation forms
http://127.0.0.1:8000/docs        # interactive API documentation (Swagger UI)
```

## Frontend Pages

- **`/inventory`** — a table of every item: title, description, remaining count,
  an **Available / Unavailable / Expired** badge, and expiration date. Sold-out
  and expired items stay visible (not hidden) so both availability rules are
  obvious. An item that is both sold out and expired shows **Expired** — the more
  specific reason.
- **`/bookings`** — the bookings made through this app, split into **Active** and
  **Cancelled** tables (member, item, reference, timestamps).
  - Each active row has a **Cancel** button that cancels that booking directly —
    no need to look up the reference in the database first. It reuses the same
    `POST /cancel` handler (and therefore the same service and business rules) as
    the form on `/book`, then redirects back here (Post-Redirect-Get).
  - Only bookings created through this app appear here. The imported CSV
    `booking_count` has no matching booking rows and so is not listed or cancellable.
- **`/book`** — a booking form (member + item dropdowns) and a cancellation form.
  - The member dropdown lists everyone alphabetically (first name, then surname)
    and shows each member's join date ("member since ...") so members who share
    the exact same name (the CSV has duplicates) are still distinguishable.
  - The item dropdown excludes **expired** items entirely (they cannot be booked);
    sold-out-but-not-expired items are still listed so the "no longer available"
    rule is demoable through the form.
  - Submissions use **Post-Redirect-Get**, so refreshing the page after booking
    does not double-book. Success and error messages appear near the top.
  - Cancelling by reference here still works, but the easiest way to cancel is the
    per-row button on **`/bookings`**.

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
badges, and the `/bookings` active/cancelled split with its per-row cancel flow).
**34 tests pass** as of the last run.

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
- **Cancelled bookings are kept.** Cancellation sets `cancelled_at` rather than
  deleting the row, which keeps history easy to reason about.
- **SQLite + single transaction.** Check-then-decrement of availability runs in one
  transaction. SQLite serialises writes, which is correct here; production would
  move to PostgreSQL with row-level locking or optimistic versioning.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'app'`** — run commands from the
  `booking-app/` directory, and use the module form: `python -m scripts.load_data`.
- **`python: command not found` (macOS/Linux)** — use `python3` instead of
  `python` in every command in this README.
- **`No module named venv` / `ensurepip is not available` (Linux)** — your
  distro ships `venv` separately; install it (Debian/Ubuntu:
  `sudo apt install python3-venv`) then retry.
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
