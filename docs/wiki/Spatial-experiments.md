# Prepare a spatial experiment

[Wiki home](Home.md) · [README](../../README.md)

## Start or reopen

From **Inventory & plan**, filter blocks by ID, free-form labels or metadata. Select individual blocks, the current page or every matching block. **Unselect all** clears the entire selection, including blocks hidden by the current filter.

Choose **Review & plan**, resolve any outstanding QC, and name the experiment. To resume an existing plan without selecting new blocks, use **Prepare spatial experiment → Open experiment**. You can open a browser draft, a locally saved experiment or an experiment JSON file.

Each experiment keeps a cropped working tissue image, metadata and source references. Inventory originals remain in the archive project. A block accepted without a tissue photo can be included as a record, but cannot be scored until a photo is supplied. Off-mat photographs require manual calibration.

## Declare your slides

Open **Slide overview**. Add slides in bulk by entering the required total, then edit their names directly or paste a list with one name per line. Defaults use `{experiment_name}_slide_001`, `_002`, and so on.

The list order determines the next slide offered while working through blocks. Renaming a slide preserves its placements. Up to 200 slides are supported per experiment.

## Score tissue and assign pieces

In **Blocks & scoring**, select a block and draw polygons around the retained pieces. Each polygon edge becomes a scoring line. Check the scale and orientation before relying on dimensions. The compact annotation window starts focused on the block. Use **− / +** to zoom out or in, **Fit whole photo** to see the complete image, or **Focus block** to return to the initial view. Scroll within the image to reach its edges. Drawing controls stay directly above the image; zoom changes only the view and preserves scoring coordinates.

Use **Assign retained tissue to a slide** to find a slide by name and assign a single piece or all pieces from the block. The dropdown has two groups:

- **Recent & next:** the last-used recipient slide and its successor in the declared list.
- **All slides:** the complete list, including those two slides, in declared order.

Assignments preserve existing placements. Assigning the same piece to the same slide again does not duplicate it here; use the piece library in **Slide mapping** when you deliberately need another section.

## Arrange and review

**Open slide map** takes you to the chosen slide. New assignments start at its center: move and rotate pieces into position, then resolve overlap, margin and clearance warnings. Rotation updates live while dragging or typing.

Review the exact assay product, dimensions and protocol in **Assay configuration**. **Review & handoff** exports a draft instruction deck and placement CSV, including block-to-piece-to-slide links. The deck can be printed to PDF from the browser.

## Save

**Save experiment** writes the current plan to the configured local folder. **Save project** saves the whole inventory and its experiment collection. **Export experiment JSON** downloads a portable copy explicitly. See [storage and backups](Storage-and-backups.md).

The planner accepts up to 1,000 blocks, with a 180 MB compact-experiment size check when creating a selection. A draft plan is not a released laboratory instruction; review it with the technician before use.
