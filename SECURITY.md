# Security and deployment scope

Block Archive currently runs on loopback for local projects. It is not a configured institutional or network service.

## Implemented boundaries

- API block data, images, event history, label PDFs and backups require a bearer token or same-origin browser session.
- The API token is generated locally, saved with owner-only file permissions and never included in backups or returned to the browser.
- Browser sessions use a separate HttpOnly, SameSite=Strict cookie. Cookie-authenticated writes require the expected Origin and a custom header. Unexpected hosts are rejected; CORS is not enabled.
- Static routes serve only the selected UI assets. Database files, photographs on disk, Git files and tokens are not served as static content.
- Images use generated UUID filenames. Decoding validates file type, dimensions and size. Thumbnails omit source metadata; originals are retained as uploaded.
- SQLite transactions coordinate state changes, image references and events. Clients must supply the current version, and invalid transitions are rejected.
- No analytics, external browser scripts, outbound link fetches or external image services are used. HTTP access logging is disabled.

## Limits before institutional deployment

The shared bearer token is an installation credential, not an individual identity. Operator names are self-declared. The event ledger cannot resist changes by an administrator with access to the database. The archive has no role-based access control, encryption at rest, retention enforcement, deletion workflow or clinical validation.

A hospital deployment needs appropriate identity integration, user permissions, HTTPS, secure storage and backup, retention/deletion procedures and an institutional security review. Do not expose the current loopback service directly to a network or treat this release as approval to process PHI.

Original photos can retain visible identifiers and metadata, including location metadata. Backups and API responses can contain identifying information. Use institution-approved capture, transfer and storage arrangements. Archive directories are not publication inputs even when someone calls their contents “dummy”.

## Backups and credentials

Store backups outside the Git checkout in an approved location. Restore only trusted ZIP files into a new empty directory while the service is stopped. A fresh directory generates a new API credential. To rotate credentials, stop the service, remove its `api-token` file, restart, and securely update clients. Restart also invalidates browser sessions until users reload the archive page.

## Reporting

Report security problems privately to the repository maintainer. Do not include patient information, specimen identifiers, photographs, credentials or archive backups in public issues or pull requests. Use synthetic reproductions.

## Combined inventory and planner

Inventory metadata, labels, source photos and selection snapshots are private archive data. Planner experiments contain working tissue photographs and identifiers in browser IndexedDB, locally saved experiment files and explicit JSON exports. Save folders are configured per archive project; native folder selection runs on the computer hosting the loopback app. Live archive data stays in the configured data directory. **Save project** JSON includes both inventory data and all experiments in the current browser/project. Archive ZIP backups exclude browser scoring and slide edits; individual experiment JSON remains available. Full JSON restores use fixed database tables, validate image filenames/checksums, and create a separate project directory and browser database. Credentials are never exported. Projects separate workspaces, not users or access permissions; the same local session/token can access every local project.

The planner shares the archive's loopback server, session cookie and same-origin mutation protection. Only listed planner assets are served. Its content security policy permits local data-URL images and inline styles used by the scoring canvas and reports; scripts remain same-origin only. Regex filtering runs in a terminable browser worker.
