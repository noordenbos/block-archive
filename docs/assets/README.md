# Documentation image provenance

`workflow.png` is a three-panel composition rendered by `tools/render_readme.py`:

1. The existing reviewed `planner/artefacts/examples/phone-stand-17cm.png` illustration. It is synthetic, not a photograph of patient material. The example height is not a universal calibration requirement.
2. A screenshot of the actual inventory UI running in a fresh temporary archive, with four generated synthetic block images and `DEMO` identifiers. The fixed selection tray is hidden for the cropped panel.
3. Two actual app captures: a real tissue-side crop with demonstration retained-piece outlines and dashed scoring lines, followed by those same pieces on a recipient slide. The outlines and placements are illustrative, not an actual experiment plan.

`tissue-block.jpg` is an existing tissue-side crop explicitly approved by the maintainer for this documentation. It was visually checked for visible identifiers and checked for EXIF, comments and XMP metadata before inclusion. It contains only the block and mat background; its filename and demonstration labels do not link to a case. The renderer reads this reviewed asset, not a live archive, OCR output or existing browser profile. No redaction is relied upon. The image was visually reviewed and its SHA-256 is recorded in `tools/reviewed-docs.sha256`; the publication audit rejects unreviewed binary changes.

To regenerate from the repository root:

```sh
uv run --python 3.12 --no-project --with-requirements requirements-dev.txt python tools/render_readme.py
```

Install Playwright Chromium first, or set `SPATIAL_BROWSER_PATH` to a local Chrome executable. Review a regenerated image before updating its approved hash.
