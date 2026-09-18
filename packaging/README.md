# Desktop distribution

`desktop_main.py` starts the combined local app in a browser without requiring a Python installation. It binds only to loopback on an available port, keeps a single desktop instance per user-data directory, and exposes storage/start/quit controls at `/desktop`. No network service is installed.

Default storage:

- macOS: `~/Library/Application Support/Block Archive/archive`
- Windows: `%LOCALAPPDATA%\Block Archive\archive`
- Linux: `$XDG_DATA_HOME/block-archive/archive`, or `~/.local/share/block-archive/archive`

The first-run page displays the actual path. Switching storage selects an empty directory or an existing archive; it never copies, deletes or merges the previous archive. Existing source installations retain their existing `.localdata` default. Select that full path in the desktop controls if migrating, after stopping the source-launched copy. Back up first. Keep the live archive on local storage rather than a network or cloud-sync folder.

## Build and test

Use a native machine for each target. PyInstaller is not a cross-compiler.

```sh
uv run --python 3.12 --no-project --with-requirements requirements-desktop.txt python tools/build_desktop.py --output .build/new-desktop-build
```

The output directory must not exist. The builder copies only application files from `tools/public-files.txt` into clean staging, collects dependency notices, creates a frozen app, and runs `--smoke-test` in a new temporary directory. macOS outputs a DMG (drag the app to Applications), Windows outputs a per-user Inno Setup installer, and Linux outputs a portable tar.gz. Windows builds require Inno Setup 6. GitHub's Windows runner includes it.

The `Build desktop installers` workflow runs native macOS arm64/Intel, Windows x64 and Linux x64 builds. Windows also silently installs its EXE into a temporary location and tests the installed copy. All outputs are attached to a draft release; the upload helper refuses published releases or a mismatched commit. They are never automatically published. Checksums and a build manifest accompany each platform. The standalone binary accepts `--smoke-test` for isolated verification.

## Signing and release gate

No distribution signing credentials are bundled or stored in source control. A successful build or SHA-256 checksum is not proof of publisher identity.

**macOS:** configure a Developer ID Application certificate in the build keychain and provide its name through `BLOCK_ARCHIVE_CODESIGN_IDENTITY`. PyInstaller signs the application. Verify the bundle with `codesign --verify --deep --strict`, notarize the final DMG with Apple's `xcrun notarytool submit ... --wait` using a securely configured keychain profile, then staple and validate it with `xcrun stapler`. Check Gatekeeper with `spctl --assess`. Test an actual downloaded DMG on a separate Mac. The current unsigned preview is ad-hoc signed only; it is not notarized.

**Windows:** use the institution's Authenticode certificate or approved signing service. Sign and timestamp the frozen executable before Inno Setup, then sign and timestamp the final setup EXE with `signtool`. Verify both using `signtool verify /pa /all`. Test the downloaded installer, first launch, update and uninstall on supported Windows machines. The workflow does not assume a certificate is present or disable OS protections.

**Linux:** test the portable archive on the supported distribution baseline and sign the checksum manifest using the maintainer's distribution-signing key before marking it verified.

After signing changes artifact bytes, regenerate SHA-256 checksums and update the build manifest. Record real verification evidence; do not merely change a status flag. Only then publish a versioned release and update the separate website's release catalog with verified URLs/checksums. Keep unsigned or untested platforms unavailable. The public site can offer the source ZIP meanwhile.

Before release, run the publication audit and inspect build manifests. Staging must contain no `.localdata`, database, imported images, exports, API tokens or settings. Test backups and restore using synthetic data. Updates replace application files only; the Windows uninstaller has no user-data removal directives. No automatic updates or network synchronization are implemented.

Primary references: [PyInstaller platform builds](https://pyinstaller.org/en/stable/usage.html), [PyInstaller macOS signing](https://pyinstaller.org/en/stable/feature-notes.html), [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution), [Inno Setup per-user installation](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
