"""Application configuration.

Everything that might reasonably need tuning lives here as a plain constant so it
is easy to find and easy to discuss in the interview. For a take-home of this size
we deliberately avoid a full settings framework (e.g. pydantic-settings / .env files)
— that is noted as a future improvement in docs/decisions.md.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Filesystem paths
# ---------------------------------------------------------------------------
# BASE_DIR points at the project root (the folder that contains the `app/`,
# `data/` and `scripts/` directories). We resolve it relative to THIS file so
# the app works no matter which directory the process was started from.
BASE_DIR = Path(__file__).resolve().parent.parent

# Location of the source CSV files that seed the database.
DATA_DIR = BASE_DIR / "data"

# Absolute path to the SQLite database file. Keeping it at the project root makes
# it obvious to the evaluator where the local database lives (and .gitignore
# excludes it so it never gets committed).
DB_PATH = BASE_DIR / "booking.db"

# SQLAlchemy connection URL. SQLite uses a file path after the `sqlite:///` prefix.
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------
# The maximum number of concurrent bookings a single member may hold. The brief
# fixes this at 2. It is a constant here so the rule is defined in exactly one
# place and referenced by the service layer.
MAX_BOOKINGS = 2
