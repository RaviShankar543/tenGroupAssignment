"""Domain exceptions raised by the service layer.

The service layer (`services.py`) speaks in terms of BUSINESS problems, not HTTP.
It raises these exceptions and stays completely unaware of status codes, JSON, or
HTML. The transport adapters then map each exception to the right response:

- The JSON API maps them via a single exception handler in `main.py`.
- The HTML form routes catch `BookingError` and re-render the page with the message.

Each exception carries:
- `.message`     : a human-readable, client-safe string (no internals leaked).
- `.status_code` : the HTTP status the API should return for this situation.

Keeping the status code on the exception means the mapping lives in one place and
new error types automatically get correct HTTP handling.
"""


class BookingError(Exception):
    """Base class for all expected, user-facing booking/cancellation errors.

    `status_code` defaults to 400 but every concrete subclass overrides it with the
    status defined in the API contract (see the plan §8).
    """

    status_code: int = 400

    def __init__(self, message: str):
        # Store the safe, human-readable message and also pass it to the base
        # Exception so standard traceback/logging still shows something useful.
        self.message = message
        super().__init__(message)


class MemberNotFound(BookingError):
    """Raised when no member exists for the supplied member_id → HTTP 404."""

    status_code = 404

    def __init__(self, message: str = "Member not found"):
        super().__init__(message)


class InventoryItemNotFound(BookingError):
    """Raised when no inventory item exists for the supplied id → HTTP 404."""

    status_code = 404

    def __init__(self, message: str = "Inventory item not found"):
        super().__init__(message)


class BookingNotFound(BookingError):
    """Raised when no booking matches the member + reference → HTTP 404."""

    status_code = 404

    def __init__(self, message: str = "Booking not found"):
        super().__init__(message)


class BookingLimitReached(BookingError):
    """Raised when the member is already at/above MAX_BOOKINGS → HTTP 409.

    409 Conflict is used (rather than 400) because the request itself is valid;
    it conflicts with the current state of the member's account.
    """

    status_code = 409

    def __init__(
        self, message: str = "Member has reached the maximum number of bookings"
    ):
        super().__init__(message)


class ItemUnavailable(BookingError):
    """Raised when the item has no remaining availability → HTTP 409."""

    status_code = 409

    def __init__(self, message: str = "This item is no longer available"):
        super().__init__(message)


class BookingAlreadyCancelled(BookingError):
    """Raised when cancelling a booking that is already cancelled → HTTP 409."""

    status_code = 409

    def __init__(self, message: str = "Booking has already been cancelled"):
        super().__init__(message)
