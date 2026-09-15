# Block Archive

A local pathology block organizer, derived from [Spatial Prep](https://github.com/noordenbos/spatial-prep). It follows a **year → case → subspecimen → cassette** archive and maintains a searchable photographic record each time a block returns after cutting.

For example, B4 means subspecimen B, cassette 4. The full printed block code remains the lookup key for other systems; the separate case fields determine filing order and group related blocks. Known cassette contents are searchable.

## Start

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required for this command:

```sh
uv run --no-project --with-requirements requirements.txt python server.py
```

Open [Block Archive](http://127.0.0.1:8780). Spatial Prep can continue running separately on port 8774. Alternatively, install `requirements.txt` in a virtual environment and run `python server.py`.

The app starts empty. It stores the database, original photographs, thumbnails and API token in `.localdata/`, excluded from Git. Set `BLOCK_ARCHIVE_DATA_DIR` or `--data-dir` to use another approved directory. Do not use a network filesystem for the SQLite database.

## Technician workflow

1. Enter your operator name or initials. Register the **full block code**, archive year, case number, subspecimen and cassette number. Add the known cassette contents.
2. Add an initial photograph and confirm the block's first archive position.
3. **Check out for cutting** when the block leaves the archive.
4. **Mark cutting complete** when cutting is finished.
5. Take and upload a **new post-cut photo**. Return the block to its year–case/subspecimen/cassette position and confirm rearchiving.

Every cycle keeps its photographs and recorded events. A previous-cycle image, another block’s image, or a reference image cannot satisfy rearchiving. Re-uploading identical image bytes for the same block is rejected. This checks uploads, not when the physical photograph was taken; the operator remains responsible for verifying the code and image.

Search full codes, case numbers, cassette contents, filing positions or external IDs. Case blocks are sorted numerically: B4 precedes B10. The selected record shows the other blocks in its case. A barcode scanner that enters text and presses Enter can use the main search field.

The full code and case hierarchy are immutable in this first version. Verify them when registering; correction/merge workflows are not yet implemented. Two-digit years from unfamiliar historical codes require an explicit four-digit year rather than guessing a century.

## Generic API

Read the [API guide](http://127.0.0.1:8780/static/api.html) and download the typed [OpenAPI schema](http://127.0.0.1:8780/openapi.json) from the running server. The guide is also in [static/api.html](static/api.html).

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

No LIS/LIMS connector or outbound webhook is configured. Image URLs are authenticated, not public links. An external system can resolve its block code, retrieve images with the API token, or link users to `/?block=<URL-encoded code>` on this server.

## Backup and recovery

Use **Back up archive** for a consistent ZIP of the database and all stored image files. The API token is deliberately excluded. For larger archives, use:

```sh
uv run --no-project --with-requirements requirements.txt python tools/backup.py --output /approved/path/archive-backup.zip
```

To restore, stop the server, extract a trusted backup into a **new empty data directory**, and start with `--data-dir` pointing to it. A new API token is generated; update clients. Test recovery before relying on a backup. Photographs and backups can contain identifiers and original metadata. Archive access is briefly locked against changes while a backup is copied.

## Scope and data handling

This is a local, single-archive first release, not a deployed hospital information system. It has a shared API credential and self-declared operator attribution, not verified staff identity or roles. See [SECURITY.md](SECURITY.md) before handling identifiable material or planning a network deployment. The event history is append-only through the API but is not tamper-proof against someone with filesystem access.

Original photos are retained unchanged; thumbnails remove source metadata. All data processing runs locally, without analytics or external scripts. No record deletion, retention policy, multi-site namespace, LIS synchronization, or clinical validation is implemented. Institutions must determine approved use and storage.

## Tests

```sh
uv run --no-project --with-requirements requirements-dev.txt pytest -q tests/test_api.py
uv run --no-project --with-requirements requirements-dev.txt python -m playwright install chromium
uv run --no-project --with-requirements requirements-dev.txt python tests/test_browser.py
python tools/check_publication.py
```

Tests use generated synthetic records and images in temporary directories. They cover the return cycle, image freshness constraints, case hierarchy, indexed search, external links, version conflicts, authentication, backup/recovery and browser workflows.

## License and origin

[PolyForm Noncommercial 1.0.0](LICENSE), with [separate commercial licensing](COMMERCIAL_LICENSE.md) for uses outside its permissions. See [LICENSING.md](LICENSING.md).

Forked from Spatial Prep's clean release commit `eed0534c594661cc8ed67770133de04309cc281a`. The existing spatial planning app is unchanged. This fork retains the license and label generator, while replacing the planning workspace with persistent archive records and a versioned API.
