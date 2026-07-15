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
