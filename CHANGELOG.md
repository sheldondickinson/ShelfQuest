# Changelog

## Unreleased

### Added

- Added a read-only Home Assistant integration endpoint at `/api/integrations/home-assistant/reading`.
- Added per-child current reading summaries with active loan counts, overdue counts, next due dates, and markdown-formatted book lists.
- Added Home Assistant dashboard documentation for tile cards plus markdown book lists.

### Changed

- Updated the Docker entrypoint to run `app.asgi:app` so integration routes can be registered cleanly without bloating `app/main.py`.

### Database impact

- No schema migration is required.
- No runtime data should be deleted or overwritten.
