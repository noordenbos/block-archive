# Block Archive + Spatial Prep

Release **v1.0.0** · Local inventory, QC, spatial planning and project storage.

One local app for the block-photo inventory and spatial experiment planning. Start with photographs, select blocks, then score tissue and map pieces onto recipient slides. The **year → case → subspecimen → cassette** archive and cutting history remain available under **Block checkout & return**. The planner is bundled from [Spatial Prep](https://github.com/noordenbos/spatial-prep); no second installation or server is needed.

For example, B4 means subspecimen B, cassette 4. The full printed block code remains the lookup key for other systems; the separate case fields determine filing order and group related blocks. Known cassette contents are searchable.

## Photograph → Import & QC → Inventory & plan

The home page starts with **Photograph**. **Prepare spatial experiment** opens the planner without requiring a new block selection. The **Archive project** bar identifies the active inventory and provides **Block checkout & return** for its physical movement history. Photo-to-record linking is available inside the archive area; it is separate from Import & QC. Experiment JSON files can be opened independently, while physical block records and cutting events remain scoped to their archive project. The four tabs keep the capture, import review, selection and metadata workflows together.

1. **Photograph.** Download the A4 or Letter mat directly from the home page and print at actual size. Open the QR generator, paste full block IDs or supply an ID list, and print matching labels. Capture the identifier and tissue sides with the same full block ID, ruler and all mat markers visible. The page links to the detailed photography guide.
2. **Import & QC.** Import a folder of JPEG, PNG or WebP photographs; identical files are skipped. The app groups single QR readings, analyzes mat geometry and compares printing evidence to assign tissue and identifier sides. Clear pairs are ready automatically. The default review queue shows only exceptions: missing/extra views, unreadable or inconsistent IDs, missing mat geometry, pending analysis and ambiguous sides.
3. **Resolve exceptions.** Expand a group, inspect the originals, correct each photo's matching ID to merge/split groups, and declare its tissue/identifier side. Save grouping changes, then accept QC when the grouping, sides and image quality have been reviewed. For a single photograph, choose **Continue without tissue side** or **Continue without identifier side**, check the QC confirmation and save. A missing tissue photo becomes a record-only block in experiments, with scoring unavailable until a tissue photo is added. Other incomplete or ambiguous assignments stay flagged; missing mat calibration still requires manual calibration in the planner. A new photo or changed analysis invalidates old QC acceptance. Use **Analyze / update photos** for missing results or older side-detection results. After QC, inventory cards and experiment-selection previews show only the tissue-side block crop; full original views remain in Import & QC. Crops are cached locally and do not change originals or scoring coordinates. A failed crop links back to review. **Show ready groups and automatic side assignments** exposes the printing-feature evidence in Import & QC. The v2 detector searches a wider upper-rim band, checks dark/light contrast at two stroke sizes and looks for coherent rows. It rejects isolated texture, wax glints and filled round slots. Both views showing credible lettering, or confident methods disagreeing, require review. The original component-count heuristic remains a fallback for older projects and weak v2 evidence. Counts are evidence, not probabilities or OCR. The rim heuristic assumes an oriented cassette; failed mat registration and frozen moulds still require review. Manual declarations take precedence. This is a software intake check, not automatic clinical or image-quality certification.
4. **Inventory & plan.** Search IDs, descriptions, imported label text, arbitrary metadata values, linked dataset IDs or free-form labels. Choose Regex for case-insensitive patterns such as `^TEST-B[12]$`, or use the metadata field/value filters. Regex runs off the UI thread with a timeout. Select individual records, a page or all matches across pages; selection survives filter changes. Labels can still be added/removed in bulk.
5. **Create an experiment.** Selected groups needing QC lead back to the review queue. Ready groups use their saved tissue/identifier assignments without repeat confirmation. Name the experiment and open the planner with one cropped working tissue image per block, source references, labels and a metadata snapshot. Originals and identifier photos stay in the inventory. Off-mat photos use a reduced preview and require manual calibration. Review assay dimensions, score tissue, map pieces onto slides and export the handoff. Use **Slide overview** to create numbered slides in bulk, edit names or paste a name list. In **Blocks & scoring**, search for a recipient slide and assign individual retained pieces or all pieces. The last-used slide and its successor appear first; assignments are saved with the experiment. Existing placements are preserved. Arrange the assigned pieces in **Slide mapping**; rotation updates the map while dragging or typing.

A photo group is not a registered archive block or a cutting event. Case-only barcodes may cover several physical blocks; use full cassette identifiers and correct grouping before planning. **Block checkout & return** and **Link photos to block records** remain available for physical archive records. Experiments support up to 1,000 blocks, with a 180 MB portable-backup size check on the compact experiment. Original photo sizes no longer limit selections. Saving an older inventory experiment removes duplicate source images while preserving its working image, calibration and scoring geometry. Whole-project backups still include the inventory originals and all experiments.

### Metadata without a required CSV

Open **Metadata** to add records manually, edit their variable columns, paste a table from a spreadsheet, or drop a UTF-8 CSV/TSV file (up to 2 MB). Tables need headers. Choose the matching ID column in the preview; all other columns become metadata. Quoted commas, multiline values, Unicode and leading zeroes are retained as text.

Matching uses the complete ID, ignoring capitalization and surrounding spaces; no partial/patient-level inference is made. Duplicate IDs or ambiguous headers must be corrected before import. IDs without photos are saved for future matching. The preview reports matched/unmatched rows and differing existing values before anything is written.

**Fill empty values only** is the default import mode. **Replace supplied nonempty values** deliberately updates matching cells while retaining other columns; blank imported cells never silently erase an existing value. Use **Edit values** to clear a value or remove a column explicitly. Conflicting simultaneous edits are rejected rather than overwritten. Saved columns immediately become inventory search terms and field/value filters, and are included in archive backups and new experiment snapshots.

Selections snapshot the IDs, photo choices, labels and metadata at creation. Later inventory changes do not silently change an existing plan. Opening another selection keeps the current experiment available under **Open experiment**; reopening a selection preserves its scoring edits.

### New, Open and Save project

The project bar is visible above both the inventory and planner:

- **New project** starts an empty inventory and experiment collection. Existing projects remain available on the laptop.
- **Open project** switches between local projects or restores a complete project JSON into a separate inventory. It never replaces an existing project.
- **Save project** writes one JSON to the configured local save folder containing every inventory photo and thumbnail, archive record/history, label, metadata column, grouping/QC decision, selection snapshot, and every experiment saved in this browser for that project—including scoring, slide layouts and compact working images.

The original inventory appears as **Local archive**. New and imported projects live under `.localdata/projects/`; each gets its own browser experiment storage. Switching in one tab protects other tabs from writing to the wrong inventory; reload an older tab to use the newly selected project. Colleagues' copies remain independent.

Project JSON includes original image bytes and is limited to 2 GB, with up to 256 MB of experiment data. **Save experiment** remains available inside the planner for a single experiment. **Back up archive** creates an archive-only ZIP and does not include browser scoring or slide edits. A full project save collects experiments from the current browser profile and app address; it cannot collect plans stored on another computer or browser profile.

To move an existing standalone Spatial Prep experiment from port 8774, first **Save experiment** there, then use **Open experiment → Open experiment file** in this combined planner. The different browser origin does not automatically transfer previous experiments. Continue using the same browser profile and `127.0.0.1:8780` for this app; changing to `localhost` uses different browser storage.

## Install and start

Each colleague installs their own copy. Git distributes the software; it does **not** synchronize photographs, experiments or archive records.

### 1. Download the tool

Open [the Block Archive repository](https://github.com/noordenbos/block-archive). For a private repository, the owner must first invite your GitHub account and you must accept the invitation. A “404” while signed in usually means access is missing.

Choose **Code → Download ZIP**, extract it, and keep the folder on your computer. Alternatively, clone with GitHub Desktop, or use Git in a terminal:

```sh
git clone https://github.com/noordenbos/block-archive.git
cd block-archive
```

For ZIP downloads, open Terminal (macOS/Linux) or PowerShell (Windows), type `cd `, then drag the extracted folder into the window and press Enter. Use a local, institution-approved folder; avoid a shared or cloud-synchronized folder for the running archive.

### 2. Install uv once

[uv](https://docs.astral.sh/uv/getting-started/installation/) manages Python and the app dependencies. You do not need to install Python separately for the command below.

**macOS/Linux:** run this official installer in Terminal, then close and reopen Terminal:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If you already use Homebrew, `brew install uv` is an alternative.

**Windows:** run this in PowerShell, then close and reopen PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

If installation is managed by your institution or WinGet is unavailable, use the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) or ask IT to install uv. Confirm `uv --version` works, then return to the downloaded app folder.

### 3. Start the app

Run this from the folder containing `server.py` and `requirements.txt`:

```sh
uv run --python 3.12 --no-project --with-requirements requirements.txt python server.py
```

The first start needs internet access to download Python and dependencies. Wait for the server to start, then open [Block Archive](http://127.0.0.1:8780) in your browser. Keep the terminal open. Press **Ctrl-C** there to stop; run the same command to start again. Do not open the HTML files directly.

The combined app uses port 8780, with its planner at `/planner/`. The older standalone Spatial Prep can still run on port 8774. These addresses work only on the computer running the app.

### Updating your copy

Back up your data first, stop the server with Ctrl-C, and update from the app folder:

```sh
git pull --ff-only
```

Then run the startup command again. GitHub Desktop users can fetch and pull from the app instead. If Git reports local changes or diverging branches, stop and ask the maintainer; do not reset or delete files to force an update.

ZIP users: download and extract the new version into a **separate folder**. Keep the old copy until you have verified the new version and your data. Follow the storage instructions below before changing copies. ZIP downloads do not support `git pull`.

### Common setup problems

- **`uv` is not recognized:** reopen the terminal after installation; check `uv --version`.
- **Cannot find `server.py` or `requirements.txt`:** change into the extracted/cloned app folder first.
- **Dependency download fails:** check internet/proxy access; ask IT if downloads are restricted.
- **Address already in use:** another instance may be running. Open its URL, or stop its terminal before restarting.
- **Browser cannot connect:** keep the server terminal open and inspect its error message. Use the exact URL above.

When reporting a problem, include your OS, `uv --version`, and the error message after removing any patient details. For Git installs, `git rev-parse --short HEAD` identifies the software version.

### Your archive and colleagues’ copies

A new installation starts empty. The database, photographs, thumbnails and API token live in `.localdata/`, excluded from Git. Updating an existing clone preserves that folder. Do not delete the app folder without first making a backup.

For a new installation or another colleague’s computer, use **Save project**, transfer the JSON through an approved channel, then choose **Open project → Open project JSON** on the new copy. For an archive-only ZIP backup, follow [Backup and recovery](#backup-and-recovery). Start the new version with `--data-dir` pointing to the restored directory. Keep using that argument on subsequent starts, or set `BLOCK_ARCHIVE_DATA_DIR`; otherwise the app opens its default empty archive. Example (replace the quoted path with your restored folder):

```sh
uv run --python 3.12 --no-project --with-requirements requirements.txt python server.py --data-dir "/path/to/restored-archive"
```

Copies evolve independently; there is no automatic merging or synchronization. Do not share a live SQLite database through Box, a network drive or another synchronization service.

Basic app use does not require the optional macOS label-reading tool or export dependencies. Those workflows are described below. Patient-grouped outside-hospital PDF assembly is not yet a packaged app workflow.

## Technician workflow

1. Enter your operator name or initials. Register the **full block code**, archive year, case number, subspecimen and cassette number. Add the known cassette contents.
2. Add an initial photograph and confirm the block's first archive position.
3. **Check out for cutting** when the block leaves the archive.
4. **Mark cutting complete** when cutting is finished.
5. Take and upload a **new post-cut photo**. Return the block to its year–case/subspecimen/cassette position and confirm rearchiving.

Every cycle keeps its photographs and recorded events. A previous-cycle image, another block’s image, or a reference image cannot satisfy rearchiving. Re-uploading identical image bytes for the same block is rejected. This checks uploads, not when the physical photograph was taken; the operator remains responsible for verifying the code and image.

Search full codes, case numbers, cassette contents, filing positions or external IDs. Case blocks are sorted numerically: B4 precedes B10. The selected record shows the other blocks in its case. A barcode scanner that enters text and presses Enter can use the main search field.

The full code and case hierarchy are immutable in this first version. Verify them when registering; correction/merge workflows are not yet implemented. Two-digit years from unfamiliar historical codes require an explicit four-digit year rather than guessing a century.

## Import existing photographs

**Photo inbox** opens `/imports`. It searches imported filenames, barcode readings and label text, including photographs that have not yet been linked to a block. These readings are unverified; a case-only barcode cannot establish the individual cassette. Inspect the full-resolution original, confirm the complete block code, and link to an existing block or register its year/case/subspecimen/cassette fields.

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

## Export cropped, paired photographs

The optional exporter creates a PDF with paired tissue/cassette views and a computer-readable ZIP containing JPEG crops, `manifest.json` and one-item-per-line `pairs.jsonl`. Full source photographs are excluded. Output must be a new directory inside private storage:

```sh
uv run --no-project --with-requirements requirements-export.txt python tools/export_crops.py --review-json .localdata/view-review.json --output .localdata/exports/new-export
```

The private review JSON maps each image UUID to `view` (`tissue_face`, `cassette_side` or `unknown`), optional `barcode_code` chosen from that image's readings, `method` and `note`. Never commit this file. Without assignments, faces remain unknown. Cropping requires at least three matching mat markers and a checked perspective fit; a failed crop never falls back to exporting the full photograph.

EXIF capture timestamps retain their fractional seconds and UTC offsets. Filename timestamps are only a fallback and have an unknown timezone. Import times are never substituted. Crops resample the original pixels after EXIF orientation, retain the complete block zone and strip embedded source metadata; timestamp provenance is explicit in the JSON and PDF.

Pairing uses the same selected barcode, different faces and a capture gap of at most five minutes. Repeated codes, unclear faces and missing counterparts are flagged. Barcode readings remain unconfirmed specimen identifiers; use the stable item/image UUIDs rather than assuming barcode values are unique. These exports do not change archive records or physical workflow state.

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

Use **Save project** for a full inventory-plus-experiments JSON and **Open project → Open project JSON** to restore it into a separate project. Verify the restored inventory and plans before removing old data. JSON files contain photographs and identifiers, but no API credential.

Use **Back up archive** for a consistent ZIP of the database and all stored image files. The API token is deliberately excluded. For larger archives, use:

```sh
uv run --no-project --with-requirements requirements.txt python tools/backup.py --output /approved/path/archive-backup.zip
```

To restore, stop the server, extract a trusted backup into a **new empty data directory**, and start with `--data-dir` pointing to it. A new API token is generated; update clients. Test recovery before relying on a backup. Photographs and backups can contain identifiers and original metadata. Archive access is briefly locked against changes while a backup is copied.

## Scope and data handling

This is a local project workspace, not a deployed hospital information system. It has a shared API credential and self-declared operator attribution, not verified staff identity or roles. See [SECURITY.md](SECURITY.md) before handling identifiable material or planning a network deployment. The event history is append-only through the API but is not tamper-proof against someone with filesystem access.

Original photos are retained unchanged; thumbnails remove source metadata. All data processing runs locally, without analytics or external scripts. No record deletion, retention policy, multi-site namespace, LIS synchronization, or clinical validation is implemented. Institutions must determine approved use and storage.

## Tests

```sh
uv run --no-project --with-requirements requirements-dev.txt pytest -q tests/test_api.py tests/test_export.py tests/test_inventory.py tests/test_capture_metadata.py tests/test_projects.py tests/test_side_detection.py
uv run --no-project --with-requirements requirements-dev.txt python -m playwright install chromium
uv run --no-project --with-requirements requirements-dev.txt python tests/test_browser.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_inventory_browser.py
uv run --no-project --with-requirements requirements-dev.txt python tests/test_projects_browser.py
node tests/side-detection.test.js
node tests/geometry.test.js
node tests/ingest.test.js
node tests/scoring-edit.test.js
python tools/check_publication.py
```

Tests use generated synthetic records and images in temporary directories. They cover the return cycle, image freshness constraints, case hierarchy, indexed search, external links, version conflicts, authentication, backup/recovery and browser workflows.

## License and origin

[PolyForm Noncommercial 1.0.0](LICENSE), with [separate commercial licensing](COMMERCIAL_LICENSE.md) for uses outside its permissions. See [LICENSING.md](LICENSING.md).

Forked from Spatial Prep's clean release commit `eed0534c594661cc8ed67770133de04309cc281a`. The standalone repository remains available. This distribution bundles the planner under `planner/` and connects it to the inventory. It retains the license, reviewed photography assets and label generator, alongside persistent archive records and a versioned API.

### Local save location

**Save project** and **Save experiment** write JSON files directly to disk, without the browser Downloads folder. The default is `saved/` inside the active project's private `.localdata` directory (inside the installation). **Save location → Choose folder** opens the computer's folder picker; you can also paste an existing absolute path or select **Use default**. A custom folder contains `BlockArchive/<project-id>/project.json` and separate `experiment-<id>.json` files. Each save replaces its previous file atomically. The setting persists per archive project; no symlinks are needed. Changing it does not move previous saves, the live database or original photos.

Browser edits remain drafts until saved. **Open experiment** includes experiments saved in the configured folder, as well as browser drafts. Whole-project saves include the inventory originals and browser experiments; standalone experiment saves include their compact working images. **Export project JSON** and **Export experiment JSON** remain explicit browser downloads for sharing. Save-location settings stay on this computer and are not included in portable project files. Keep local data outside Git; if choosing storage inside another checkout, exclude that location from Git too.

The folder picker runs on the computer running the local app: macOS uses its native chooser, Windows uses a folder dialog, and Linux uses Zenity when installed. If unavailable, paste the folder path. To move the live data directory as well, start the server with `--data-dir /absolute/path`; move/copy existing data with the server stopped.
