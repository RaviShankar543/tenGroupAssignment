# Project Description — Architecture Map

A factual map of what lives where and how a request flows through the system. For
setup/run instructions see [`README.md`](README.md); for the reasoning behind the
choices see [`docs/decisions.md`](docs/decisions.md).

## Layers

```text
Browser (HTML forms) ─┐
                      ├─► routes/pages.py ─┐
API clients (JSON) ───┘   routes/api.py  ──┤
                                           ▼
                                     services.py        (business rules — single source of truth)
                                           ▼
                                     models.py          (SQLAlchemy ORM)
                                           ▼
                                     SQLite (booking.db)
```

Both transports (JSON API and HTML forms) are **thin adapters** that call the same
functions in `services.py`. Business rules are therefore implemented exactly once.

## Files

| Path | Responsibility |
|---|---|
| `app/main.py` | Creates the FastAPI app, mounts static files, registers routers, and defines the exception handlers that map domain/validation errors to the `{ "error": ... }` JSON contract. Also creates tables on startup and exposes `/health`. |
| `app/config.py` | Constants: filesystem paths, the SQLite `DATABASE_URL`, and `MAX_BOOKINGS = 2`. |
| `app/database.py` | SQLAlchemy `engine`, `SessionLocal`, declarative `Base`, and the `get_db()` request-scoped session dependency. |
| `app/models.py` | ORM models `Member`, `InventoryItem`, `Booking` (surrogate IDs; helper properties). |
| `app/schemas.py` | Pydantic v2 request/response models for the JSON API. |
| `app/services.py` | `book_item()` and `cancel_booking()` — the real business rules, atomic per transaction. |
| `app/errors.py` | Domain exceptions, each carrying a client-safe message and its HTTP status code. |
| `app/routes/api.py` | JSON endpoints `POST /api/book`, `POST /api/cancel`. |
| `app/routes/pages.py` | HTML routes `/`, `/inventory`, `/book`, plus form handlers `POST /book`, `POST /cancel` (Post-Redirect-Get). |
| `app/templates/` | `base.html`, `inventory.html`, `booking.html`. |
| `app/static/styles.css` | Hand-written CSS (no framework, no build step). |
| `data/` | `members.csv`, `inventory.csv` (source data). |
| `scripts/load_data.py` | Creates the schema and loads both CSVs; `--reset` makes it idempotent. |
| `tests/` | `conftest.py` (isolated DB fixtures), `test_loading.py`, `test_booking.py`, `test_api.py`. |
| `docs/` | `decisions.md` (ADRs), `demo-script.md` (interview walkthrough). |

## Data model

- **members** — `id` (PK), `name`, `surname`, `booking_count`, `date_joined`, `created_at`.
- **inventory_items** — `id` (PK), `title`, `description`, `remaining_count`, `expiration_date`, `created_at`.
- **bookings** — `id` (PK), `reference` (unique), `member_id` (FK), `inventory_item_id` (FK), `created_at`, `cancelled_at` (NULL = active).

Neither `(name, surname)` nor `title` is unique because the source CSVs contain
duplicates; the surrogate `id` is the only identifier used by the API and UI.

## Business rules (in `services.py`)

**Booking** succeeds only when the member exists, the item exists,
`member.booking_count < MAX_BOOKINGS`, and the item `is_available` — which means
BOTH `remaining_count > 0` AND the item has not expired (`expiration_date` is not
in the past). On success it creates a booking, increments the member's count,
decrements the item's remaining count, and commits all changes in one transaction.
An expired item is rejected with a message naming "expired" specifically, distinct
from the generic "no longer available" (sold-out) message.

**Cancellation** succeeds only for an existing, not-yet-cancelled booking that
belongs to the given member. It stamps `cancelled_at`, decrements the member's count
(never below zero), increments the item's remaining count, and commits atomically.

## Display rules (in `routes/pages.py` + templates)

- **`/inventory`** lists every item, including sold-out and expired ones. Status is
  computed in priority order: `Expired` (expiration passed) → `Available` /
  `Unavailable` (based on remaining stock). Nothing is ever hidden.
- **`/book`** lists members ordered alphabetically by `(name, surname, id)`, with
  each option showing `Member.joined_display` ("member since ...") so members who
  share the exact same name are still distinguishable. Its item dropdown only
  offers non-expired items (`_bookable_items()`); sold-out-but-not-expired items are
  still offered so the "no longer available" rule remains demoable through the form.
