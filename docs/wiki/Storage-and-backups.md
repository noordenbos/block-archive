# Projects, storage and backups

[Wiki home](Home.md) · [README](../../README.md)

## Projects and experiments


The project bar is visible above both the inventory and planner:

- **New project** starts an empty inventory and experiment collection. Existing projects remain available on the laptop.
- **Open project** switches between local projects or restores a complete project JSON into a separate inventory. It never replaces an existing project.
- **Save project** writes one JSON to the configured local save folder containing every inventory photo and thumbnail, archive record/history, label, metadata column, grouping/QC decision, selection snapshot, and every experiment saved in this browser for that project—including scoring, slide layouts and compact working images.

The original inventory appears as **Local archive**. New and imported projects live under `.localdata/projects/`; each gets its own browser experiment storage. Switching in one tab protects other tabs from writing to the wrong inventory; reload an older tab to use the newly selected project. Colleagues' copies remain independent.

Project JSON includes original image bytes and is limited to 2 GB, with up to 256 MB of experiment data. **Save experiment** remains available inside the planner for a single experiment. **Back up archive** creates an archive-only ZIP and does not include browser scoring or slide edits. A full project save collects experiments from the current browser profile and app address; it cannot collect plans stored on another computer or browser profile.

To move an existing standalone Spatial Prep experiment from port 8774, first **Save experiment** there, then use **Open experiment → Open experiment file** in this combined planner. The different browser origin does not automatically transfer previous experiments. Continue using the same browser profile and `127.0.0.1:8780` for this app; changing to `localhost` uses different browser storage.

## Local save location

**Save project** and **Save experiment** write JSON files directly to disk, without the browser Downloads folder. The default is `saved/` inside the active project's private `.localdata` directory (inside the installation). **Save location → Choose folder** opens the computer's folder picker; you can also paste an existing absolute path or select **Use default**. A custom folder contains `BlockArchive/<project-id>/project.json` and separate `experiment-<id>.json` files. Each save replaces its previous file atomically. The setting persists per archive project; no symlinks are needed. Changing it does not move previous saves, the live database or original photos.

Browser edits remain drafts until saved. **Open experiment** includes experiments saved in the configured folder, as well as browser drafts. Whole-project saves include the inventory originals and browser experiments; standalone experiment saves include their compact working images. **Export project JSON** and **Export experiment JSON** remain explicit browser downloads for sharing. Save-location settings stay on this computer and are not included in portable project files. Keep local data outside Git; if choosing storage inside another checkout, exclude that location from Git too.

The folder picker runs on the computer running the local app: macOS uses its native chooser, Windows uses a folder dialog, and Linux uses Zenity when installed. If unavailable, paste the folder path. To move the live data directory as well, start the server with `--data-dir /absolute/path`; move/copy existing data with the server stopped.

## Backup and recovery

Use **Save project** for a full inventory-plus-experiments JSON and **Open project → Open project JSON** to restore it into a separate project. Verify the restored inventory and plans before removing old data. JSON files contain photographs and identifiers, but no API credential.

Use **Back up archive** for a consistent ZIP of the database and all stored image files. The API token is deliberately excluded. For larger archives, use:

```sh
uv run --no-project --with-requirements requirements.txt python tools/backup.py --output /approved/path/archive-backup.zip
```

To restore, stop the server, extract a trusted backup into a **new empty data directory**, and start with `--data-dir` pointing to it. A new API token is generated; update clients. Test recovery before relying on a backup. Photographs and backups can contain identifiers and original metadata. Archive access is briefly locked against changes while a backup is copied.
