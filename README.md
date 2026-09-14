# Spatial Prep

Plan FFPE block scoring and recipient-slide placement for spatial transcriptomics. Spatial Prep pairs block photographs, maps retained tissue, checks placement geometry, and creates a technician handoff report.

**Local research software.** The application runs on your computer and starts with an empty experiment. Laboratory validation and institutional approval remain separate from this software release. Exported plans require operator review.

## Start

Install Python 3.11 or newer and [uv](https://docs.astral.sh/uv/), then run from this directory:

```sh
uv run --no-project --with-requirements requirements.txt python server.py
```

Open [Spatial Prep](http://127.0.0.1:8774). Leave the terminal running. The first run may download dependencies. Subsequent image and ID processing is local; the app has no analytics or external processing service.

Alternatively, create a Python virtual environment, install `requirements.txt`, and run `python server.py` inside it. See [RUN.md](RUN.md) for details and troubleshooting.

## From block to slide

1. **Download and print the mat.** Use the app’s **Download photo mats** link. Choose A4 or Letter and print page 1 at 100%. Page 2 includes the photography guide.
2. **Prepare matching ID + QR labels.** Paste IDs or load a CSV in **Print ID + QR labels**. Check that the printed text, QR value and physical block agree.
3. **Capture and ingest.** Take identifier-side and tissue-side photographs for each block. Keep all four markers and the matching label visible. Ingest the folder; review ambiguous or unmatched captures.
4. **Draw scoring polygons.** Outline each retained piece. Its edges define the scoring lines. Record orientation and technician notes.
5. **Configure and map slides.** Enter the exact slide product, usable dimensions, margins and protocol revision. Place pieces, set rotations, and review overlap and clearance checks.
6. **Review and export.** Download the HTML instruction deck, print it to PDF, and save an experiment backup. Backups include source photographs and IDs.

## Privacy and storage

The server binds to `127.0.0.1` and serves only listed app assets. Photos sent from the browser to the local analyzer are processed in memory. Experiments, source photographs and analysis results are stored in browser IndexedDB. Exported files remain wherever you save them.

There is no built-in user authentication, encryption at rest, audit trail, or automatic retention policy. Use identifiable material only in an institution-approved environment and workflow. Do not expose the server to a network. Image re-encoding does not remove visible labels, and backups can contain original image metadata. See [SECURITY.md](SECURITY.md).

## Accuracy and release scope

- Marker registration corrects the paper plane; it does not measure block height or lens distortion.
- Capture-height bounds and scoring tolerance are user-entered assumptions, not validated confidence intervals. The 17 cm illustration is one setup example; update the capture bounds to match your setup.
- Side classification uses printed-rim features and may need manual assignment. QR decoding does not verify the visible human-readable ID.
- The initial 10 × 22 mm placement window is an example. Platform names do not load manufacturer-validated geometry. Complex exclusion zones are not implemented.
- Coordinates use the placement window’s top-left, with each piece positioned by its polygon vertex-average center. Mirror acts horizontally in the source image before clockwise rotation.
- Reports are enlarged planning aids, not cutting templates or immutable laboratory release records.

## Development

```sh
node tests/geometry.test.js
node tests/ingest.test.js
node tests/scoring-edit.test.js
uv run --no-project --with-requirements requirements-dev.txt python tests/test_pipeline.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_registration.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_server.py
uv run --no-project --with-requirements requirements-dev.txt python -m playwright install chromium
uv run --no-project --with-requirements requirements-dev.txt python tests/test_browser.py
uv run --no-project --with-requirements requirements-dev.txt python tools/audit_release.py
```

Tests generate synthetic IDs and images in memory. They do not need a specimen list or local photographs. See [RELEASE.md](RELEASE.md) for publication preparation and [LICENSING.md](LICENSING.md) for licensing and commercial use.

## License

Free for uses permitted by [PolyForm Noncommercial 1.0.0](LICENSE), including its educational and public-research permissions. Other uses require a [separate commercial agreement](COMMERCIAL_LICENSE.md).
