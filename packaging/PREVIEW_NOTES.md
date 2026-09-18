Desktop installer preview for maintainer testing.

These packages include Python, application dependencies, static assets and synthetic photography guides. No archive database, patient photographs, API tokens, exports or local settings are included. Each build runs the installed executable against a new temporary archive and checks startup, inventory assets, planner assets, native image processing and backup creation.

The macOS and Windows packages are not yet verified with distribution signing credentials. Keep this release as a draft. Do not publish these files or add them to the public download catalog until signing and platform installation checks are complete.

Archives are stored separately from the application in the operating system's per-user application-data directory. Updates and uninstalling the application should leave archives intact. Back up before updating.

Files ending in SHA256SUMS.txt contain checksums, not digital signatures. The build JSON records dependency versions, source file hashes and signing status.
