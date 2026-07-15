"""Route package: thin transport adapters over the shared service layer.

- `api`   : JSON endpoints under /api/* (Pydantic in/out).
- `pages` : server-rendered HTML pages and form POST handlers (Post-Redirect-Get).

Neither module contains business rules; both delegate to `app.services`.
"""
