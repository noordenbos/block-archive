# API and development

[Wiki home](Home.md) · [README](../../README.md)

## API

Read the [API guide](http://127.0.0.1:8780/static/api.html) and download the typed [OpenAPI schema](http://127.0.0.1:8780/openapi.json) from the running server. The guide is also in [static/api.html](../../static/api.html).

External clients authenticate with `Authorization: Bearer <token>` using the token in `.localdata/api-token`. Do not commit, log or send that token with a project backup. The browser uses a separate same-origin HttpOnly session cookie.

Key routes:

- `GET /api/v1/blocks/by-code?block_code=…`: exact code lookup, with photos and history.
- `GET /api/v1/blocks?year=2026&case_number=001234`: all blocks within a case; paginated.
- `GET /api/v1/blocks?query=…&status=awaiting_archive`: indexed search and return queue.
- `POST /api/v1/blocks/{id}/photos`: authenticated photo upload.
- `POST /api/v1/blocks/{id}/checkout`, `/complete-cut`, `/rearchive`: recorded workflow transitions.
- `PUT /api/v1/blocks/{id}/external-links`: references to other systems or datasets.
- `GET /api/v1/events?after=…`: incremental event feed for polling integrations.

Every update requires a recorded actor and current record version. Stale updates return 409 instead of overwriting another change. UUIDs are stable; exact block-code lookup trims whitespace and ignores case. The year/case/subspecimen/cassette identity is also unique within the installation. Different laboratories with overlapping identifiers need separate namespaces or installations.

No LIS/LIMS connector or outbound webhook is configured. Image URLs are authenticated, not public links. An external system can resolve its block code, retrieve images with the API token, or link users to `/archive?block=<URL-encoded code>` on this server.

## Tests

```sh
uv run --no-project --with-requirements requirements-dev.txt pytest -q tests/test_api.py tests/test_export.py tests/test_inventory.py tests/test_capture_metadata.py tests/test_projects.py tests/test_side_detection.py
uv run --no-project --with-requirements requirements-dev.txt python -m playwright install chromium
uv run --no-project --with-requirements requirements-dev.txt python tests/test_browser.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_inventory_browser.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_projects_browser.py
node tests/project-format.test.js
node tests/side-detection.test.js
node tests/geometry.test.js
node tests/ingest.test.js
node tests/scoring-edit.test.js
python tools/check_publication.py
```

Tests use generated synthetic records and images in temporary directories. They cover the return cycle, image freshness constraints, case hierarchy, indexed search, external links, version conflicts, authentication, backup/recovery and browser workflows.

## Data handling

This is a local project workspace, not a deployed hospital information system. It has a shared API credential and self-declared operator attribution, not verified staff identity or roles. See [SECURITY.md](../../SECURITY.md) before handling identifiable material or planning a network deployment. The event history is append-only through the API but is not tamper-proof against someone with filesystem access.

Original photos are retained unchanged; thumbnails remove source metadata. All data processing runs locally, without analytics or external scripts. No record deletion, retention policy, multi-site namespace, LIS synchronization, or clinical validation is implemented. Institutions must determine approved use and storage.

## Repository layout

```text
block_archive/   Python application: API, archive storage, inventory, QC and imaging
static/          Inventory and archive browser interface
planner/         Spatial planner interface and printable photography assets
tools/           Import, backup, export, documentation and publication utilities
tests/           Synthetic API, browser and geometry checks
docs/            Wiki pages and reviewed documentation images
server.py        Small compatibility launcher
requirements*.txt  Runtime and development dependencies
```

Run the documented `python server.py` command from the repository root, or use `python -m block_archive` with the same options and dependencies. Import the app factory as `from block_archive.server import create_app`. The root launcher also re-exports it for existing integrations.

The default private data directory remains `.localdata/` at the repository root. Moving Python modules does not move or migrate user data. Image templates and browser assets are resolved relative to the installation, independently of the shell's working directory.
