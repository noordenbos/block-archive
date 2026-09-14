# Run Spatial Prep locally

From the project directory:

```sh
uv run --no-project --with-requirements requirements.txt python server.py
```

Open [http://127.0.0.1:8774](http://127.0.0.1:8774), keeping the terminal running. Do not open `index.html` directly: folder ingestion needs the local `/api/analyze` endpoint.

Without uv, create a virtual environment (`python -m venv .venv`), activate it, install dependencies (`python -m pip install -r requirements.txt`), then run `python server.py`. Python 3.11 or newer is recommended.

## Storage and transfer

The app processes photos and labels locally. Its HTTP server binds only to loopback, checks the request host and API origin, suppresses request logs, and serves only listed application files. Processing uses memory; browser IndexedDB stores experiments, source images and analysis results. Download experiment backups before clearing browser storage or changing browser or port.

Use institution-approved capture, transfer, storage and retention arrangements for identifiable material. The app provides no built-in authentication, encryption at rest or audit logging. Project files and reports can retain identifying information. Do not place private data in the repository.

## Photography

Download an A4 or Letter mat using **Download photo mats**. Print at actual size and measure the 50 mm check line. Keep all four corner markers, the ruler and the matching ID label in frame. The supported mat uses ArUco 4x4 IDs 0–3 and a 65 × 55 mm block zone.

Take identifier-side and tissue-side photos with the same matching label. Use **Ingest photo folder**. QR payloads determine groups; filename order does not. Clear pairs become blocks, while ambiguous, conflicting and unmatched images remain in the ingest report. Review failures or assign image roles manually when appropriate.

JPEG, PNG and WebP are accepted. Convert HEIC locally first. The analyzer scales images to a maximum dimension of 2200 pixels; manual image imports are limited to 20 MB and resampled to 1800 pixels. Folder ingestion retains source photos in the experiment backup.

The 17 cm stand illustration is an example, not a universal distance. Under **Capture geometry and scoring tolerance**, set the minimum camera distance and maximum block-face height for your setup; the defaults assume a minimum camera distance of 350 mm. Paper-plane calibration cannot recover tissue elevation. Bench validation of print scale, height bounds and tolerance is still required.

QR decoding does not perform OCR verification. Confirm that the QR, printed label and block match. If earlier labels were produced using a generator that reused a QR image, reprint and recapture; changing the code does not correct existing photographs.

## Troubleshooting

- **Fetch failure during ingest:** open the app from the server URL, not a local file.
- **Port already in use:** an existing instance may be running. Use that instance or stop it before restarting to load server changes.
- **Restart:** press Ctrl-C in the server terminal and run the command again. `python stop_server.py` shows the listener and asks for confirmation before stopping it.
- **Unmatched captures:** retain the originals and inspect the QR, markers and side assignment. **Reanalyze retained photos** reruns analysis.
- **Unavailable local storage:** use a normal browser window with storage enabled. Restore from your experiment backup if needed.

## Validation

See the commands in [README.md](README.md). The tests use generated fixtures and cover label QR correspondence, image rotation, marker registration, pairing, scoring edits and HTTP access boundaries. They are software regression checks, not independent bench or clinical validation.
