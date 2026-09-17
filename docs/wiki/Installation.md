# Installation and updates

[Wiki home](Home.md) · [README](../../README.md)

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

For a new installation or another colleague’s computer, use **Save project**, transfer the JSON through an approved channel, then choose **Open project → Open project JSON** on the new copy. For an archive-only ZIP backup, follow [Backup and recovery](Storage-and-backups.md#backup-and-recovery). Start the new version with `--data-dir` pointing to the restored directory. Keep using that argument on subsequent starts, or set `BLOCK_ARCHIVE_DATA_DIR`; otherwise the app opens its default empty archive. Example (replace the quoted path with your restored folder):

```sh
uv run --python 3.12 --no-project --with-requirements requirements.txt python server.py --data-dir "/path/to/restored-archive"
```

Copies evolve independently; there is no automatic merging or synchronization. Do not share a live SQLite database through Box, a network drive or another synchronization service.

Basic app use does not require the optional macOS label-reading tool or export dependencies. Those workflows are described below. Patient-grouped outside-hospital PDF assembly is not yet a packaged app workflow.
