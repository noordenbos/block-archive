# Importing and exporting photographs

[Wiki home](Home.md) · [README](../../README.md)

## Historical photo linking

**Link photos to block records** opens `/imports`. It searches imported filenames, barcode readings and label text, including photographs that have not yet been linked to a block. These readings are unverified; a case-only barcode cannot establish the individual cassette. Inspect the full-resolution original, confirm the complete block code, and link to an existing block or register its year/case/subspecimen/cassette fields.

Import a local folder (top-level JPEG, PNG and WebP files; sources are never modified):

```sh
uv run --no-project --with-requirements requirements.txt python tools/import_folder.py /approved/photo-folder
```

On macOS, optionally read labels first using Apple's on-device Vision framework:

```sh
mkdir -p .localdata/import-review
swift -module-cache-path /tmp/block-archive-swift-cache tools/read_labels.swift /approved/photo-folder .localdata/import-review/labels.json
uv run --no-project --with-requirements requirements.txt python tools/import_folder.py /approved/photo-folder --labels-json .localdata/import-review/labels.json
```

Use a private output directory for label readings. Processing sends nothing to an OCR service. The importer preserves original bytes, makes metadata-free thumbnails, deduplicates identical files by SHA-256 and records a private result report. Re-running skips existing images. Console output contains totals only. A failed file is reported privately and does not prevent other images from loading.

Confirming a link records a **historical reference**, not a cutting or physical return event. Its timestamp records import/linking, not capture. It cannot satisfy the requirement for a fresh archive photo. Import images, readings and confirmed links are included in archive backups. Unlinked readings are searchable through the inbox API; confirmed images are also returned through normal block-code lookup.

- `GET /api/v1/imports?query=…&status=pending`: search the inbox; status also accepts `linked` or `all`.
- `GET /api/v1/imports/{id}` and `/image`, `/thumbnail`: metadata and authenticated images.
- `POST /api/v1/imports/{id}/confirm`: link using `block_id`, `actor`, `expected_version` and `expected_block_version`.

## Paired crop exports

The optional exporter creates a PDF with paired tissue/cassette views and a computer-readable ZIP containing JPEG crops, `manifest.json` and one-item-per-line `pairs.jsonl`. Full source photographs are excluded. Output must be a new directory inside private storage:

```sh
uv run --no-project --with-requirements requirements-export.txt python tools/export_crops.py --review-json .localdata/view-review.json --output .localdata/exports/new-export
```

The private review JSON maps each image UUID to `view` (`tissue_face`, `cassette_side` or `unknown`), optional `barcode_code` chosen from that image's readings, `method` and `note`. Never commit this file. Without assignments, faces remain unknown. Cropping requires at least three matching mat markers and a checked perspective fit; a failed crop never falls back to exporting the full photograph.

EXIF capture timestamps retain their fractional seconds and UTC offsets. Filename timestamps are only a fallback and have an unknown timezone. Import times are never substituted. Crops resample the original pixels after EXIF orientation, retain the complete block zone and strip embedded source metadata; timestamp provenance is explicit in the JSON and PDF.

Pairing uses the same selected barcode, different faces and a capture gap of at most five minutes. Repeated codes, unclear faces and missing counterparts are flagged. Barcode readings remain unconfirmed specimen identifiers; use the stable item/image UUIDs rather than assuming barcode values are unique. These exports do not change archive records or physical workflow state.
