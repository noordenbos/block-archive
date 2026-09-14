# Release candidate: local research edition

This version provides a local FFPE scoring and placement workflow, printable photography mats, operator instructions, and reviewed synthetic test fixtures. The app starts with an empty experiment; its header identifies it as local research software. Exported reports remain drafts for operator review.

## Included changes

- Prominent A4 and Letter downloads with printing instructions and an optional setup illustration.
- Removed development-only photo loaders and hard-coded specimen identifiers.
- Startup waits for all workflow scripts, preventing a race that could initialize a demo experiment.
- Generated test fixtures replace private label lists and source photographs.
- Local HTTP serving is limited to explicit app assets; directory browsing and private-file access are blocked.
- The command-line label tool uses the same QR/PDF generator as the app.
- Runtime and development dependencies are separated; PDF tools no longer depend on PyMuPDF.
- Regression tests and a release-content audit run in CI.

## Publication gate

1. Use a new repository created from `tools/release-files.txt`; never push the older development repository’s history to it.
2. Run the tests and `tools/audit_release.py` from the clean snapshot. Review each distributed PDF and image. The release manifest excludes real photographs, ID lists, project backups and private handoff notes.
3. Confirm institutional rights to offer the selected PolyForm Noncommercial license and separate commercial agreements. See `LICENSING.md`.
4. Keep the repository private until the maintainer completes the final content and rights review. Making it public is a separate action.

`tools/prepare_release.py` copies only the manifest-listed files into a new destination. It refuses an existing destination and does not copy Git history or initialize a remote. `tools/audit_release.py` screens the working tree and every reachable commit. An optional private denylist can supplement the generic checks without being copied into the release. Automated checks are screening, not PHI certification.

Software checks do not validate capture accuracy or authorize clinical deployment. Bench validation, manufacturer geometry verification and institutional approval remain separate work.
