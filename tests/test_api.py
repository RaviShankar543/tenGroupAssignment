"""HTTP-level tests for the JSON API contract (§8 of the plan).

These go through the FastAPI `TestClient`, so they verify the full stack: routing,
Pydantic validation, the service layer, and the exception handlers that shape
`{ "error": ... }` responses and status codes.

The `client` fixture shares the same temporary database as `db_session`, and
`seed_basic` populates it, so ids referenced below exist.
"""


def test_book_success_returns_201(client, seed_basic):
    """A valid booking returns 201 and the documented success body."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    resp = client.post(
        "/api/book",
        json={"member_id": member.id, "inventory_item_id": item.id},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["booking_reference"].startswith("BK-")
    assert body["member_id"] == member.id
    assert body["inventory_item_id"] == item.id
    assert "booked_at" in body


def test_book_member_not_found_returns_404(client, seed_basic):
    """Unknown member id → 404 with the uniform error shape."""
    item = seed_basic["available_item"]
    resp = client.post(
        "/api/book", json={"member_id": 999999, "inventory_item_id": item.id}
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "Member not found"}


def test_book_item_not_found_returns_404(client, seed_basic):
    """Unknown item id → 404."""
    member = seed_basic["available_member"]
    resp = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": 999999}
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "Inventory item not found"}


def test_book_at_limit_returns_409(client, seed_basic):
    """Member at the max booking limit → 409."""
    member = seed_basic["at_limit_member"]
    item = seed_basic["available_item"]
    resp = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    )
    assert resp.status_code == 409
    assert resp.json() == {
        "error": "Member has reached the maximum number of bookings"
    }


def test_book_sold_out_returns_409(client, seed_basic):
    """Sold-out item → 409."""
    member = seed_basic["available_member"]
    item = seed_basic["sold_out_item"]
    resp = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    )
    assert resp.status_code == 409
    assert resp.json() == {"error": "This item is no longer available"}


def test_book_expired_item_returns_409(client, seed_basic):
    """Booking an item past its expiration_date -> 409 with an expiry-specific
    message, even though it still has stock. Exercised at the HTTP layer to prove
    a client cannot bypass the rule by calling the JSON API directly (the UI-level
    dropdown filtering is a courtesy, not the actual enforcement point)."""
    member = seed_basic["available_member"]
    item = seed_basic["expired_item"]
    resp = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    )
    assert resp.status_code == 409
    assert resp.json() == {
        "error": "This item has expired and can no longer be booked"
    }


def test_book_missing_field_returns_422(client, seed_basic):
    """A malformed body (missing field) → 422 in the uniform error shape."""
    resp = client.post("/api/book", json={"member_id": 1})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_cancel_success_returns_200(client, seed_basic):
    """Booking then cancelling returns 200 with status 'cancelled'."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    booked = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    ).json()
    reference = booked["booking_reference"]

    resp = client.post(
        "/api/cancel",
        json={"member_id": member.id, "booking_reference": reference},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["booking_reference"] == reference
    assert body["status"] == "cancelled"
    assert "cancelled_at" in body


def test_cancel_unknown_reference_returns_404(client, seed_basic):
    """Cancelling an unknown reference → 404."""
    member = seed_basic["available_member"]
    resp = client.post(
        "/api/cancel",
        json={"member_id": member.id, "booking_reference": "BK-NOPE1234"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "Booking not found"}


def test_cancel_twice_returns_409(client, seed_basic):
    """Cancelling the same booking twice → 409 on the second attempt."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    reference = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    ).json()["booking_reference"]

    client.post(
        "/api/cancel",
        json={"member_id": member.id, "booking_reference": reference},
    )
    resp = client.post(
        "/api/cancel",
        json={"member_id": member.id, "booking_reference": reference},
    )
    assert resp.status_code == 409
    assert resp.json() == {"error": "Booking has already been cancelled"}


def test_health_endpoint(client):
    """The health probe returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
