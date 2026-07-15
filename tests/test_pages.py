"""HTML page-rendering tests for /inventory and /book.

These go through the FastAPI `TestClient` and assert on the rendered HTML, since
the behaviours under test (dropdown ordering/content, status badges) are template
concerns, not service-layer concerns. `seed_basic` (see conftest.py) provides a
small, predictable dataset including an `expired_item` so these tests do not
depend on the real CSV data or on today's date drifting relative to hard-coded
dates.
"""


def test_book_page_lists_members_alphabetically_with_join_date(client, seed_basic):
    """GET /book orders the member dropdown by (name, surname) and shows each
    member's join date so members with identical names stay distinguishable."""
    resp = client.get("/book")
    assert resp.status_code == 200
    html = resp.text

    # "AtLimit Member" sorts before "Available Member" alphabetically by first
    # name ('t' < 'v' at the second character), which sorts before "OverLimit
    # Member" ('O' > 'A'). This only holds if ordering is alphabetical, not by id
    # (id order would be Available, AtLimit, OverLimit — the reverse for the first
    # pair — since that is insertion order in seed_basic).
    at_limit_pos = html.index("AtLimit Member")
    available_pos = html.index("Available Member")
    over_limit_pos = html.index("OverLimit Member")
    assert at_limit_pos < available_pos < over_limit_pos

    # The "member since ..." disambiguator (Member.joined_display) is present.
    assert "member since 01 January 2024" in html


def test_book_page_item_dropdown_excludes_expired_item(client, seed_basic):
    """The item <select> on /book must not offer the expired item, but the
    booking page as a whole may still mention it if it appeared elsewhere (it
    should not, since /book only renders bookable items)."""
    resp = client.get("/book")
    assert resp.status_code == 200
    html = resp.text

    assert "Bali" in html  # available_item: still offered.
    assert "Route 66" in html  # sold_out_item: still offered (only stock is 0).
    assert "Expired Trip" not in html  # expired_item: must be filtered out.


def test_inventory_page_shows_expired_badge_not_unavailable(client, seed_basic):
    """/inventory lists the expired item with an "Expired" badge, distinct from
    the generic "Unavailable" badge used for sold-out (but not expired) items."""
    resp = client.get("/inventory")
    assert resp.status_code == 200
    html = resp.text

    # All three items remain visible (nothing is hidden from this table).
    assert "Bali" in html
    assert "Route 66" in html
    assert "Expired Trip" in html

    # The expired item's row uses the expired-specific badge...
    assert 'badge-expired">Expired</span>' in html
    # ...and the sold-out (non-expired) item still uses the generic one.
    assert 'badge-unavailable">Unavailable</span>' in html


def test_bookings_page_empty_state(client, seed_basic):
    """With no bookings yet, /bookings renders both tables and their empty states."""
    resp = client.get("/bookings")
    assert resp.status_code == 200
    html = resp.text

    assert "No active bookings yet." in html
    assert "No cancelled bookings." in html


def test_bookings_page_lists_active_and_offers_row_cancel(client, seed_basic):
    """After booking, /bookings shows the row as active with a per-row cancel form
    carrying the member id and reference (so no reference typing is needed)."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]

    booked = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    )
    assert booked.status_code == 201
    reference = booked.json()["booking_reference"]

    html = client.get("/bookings").text
    assert reference in html
    assert "Bali" in html
    assert 'badge-available">Active</span>' in html
    # The per-row cancel form has everything the /cancel handler needs.
    assert f'name="booking_reference" value="{reference}"' in html
    assert f'name="member_id" value="{member.id}"' in html
    assert 'name="next" value="/bookings"' in html


def test_bookings_page_row_cancel_moves_booking_to_cancelled(client, seed_basic):
    """Posting the per-row cancel form redirects back to /bookings (PRG) and the
    booking then appears under the cancelled table, not the active one."""
    member = seed_basic["available_member"]
    item = seed_basic["available_item"]
    reference = client.post(
        "/api/book", json={"member_id": member.id, "inventory_item_id": item.id}
    ).json()["booking_reference"]

    resp = client.post(
        "/cancel",
        data={
            "member_id": str(member.id),
            "booking_reference": reference,
            "next": "/bookings",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/bookings?")

    html = client.get("/bookings").text
    # The reference now sits after the "Cancelled" heading, i.e. in that table.
    assert html.rindex(reference) > html.index(">Cancelled<")
    assert 'badge-cancelled">Cancelled</span>' in html
