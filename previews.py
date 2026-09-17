"""Disposable local block-zone previews; original images and scoring stay unchanged."""
from pathlib import Path
import tempfile
import threading
from PIL import Image
from archive import ArchiveError
from tools.export_crops import block_crop

_CROPS = threading.BoundedSemaphore(2)


def block_preview(store, source, photo_id):
    # Source records are immutable, and each project has its own private cache.
    folder = store.directory / 'preview-cache' / 'block-zone-v1'
    destination = folder / (photo_id+'.jpg')
    with _CROPS:
        if destination.is_file():
            return destination
        try:
            with Image.open(source) as image:
                crop, _ = block_crop(image)
        except ValueError as error:
            raise ArchiveError(422, 'A reliable block crop is unavailable. Review the photograph in Import & QC.') from error
        crop.thumbnail((780,780))
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.NamedTemporaryFile(dir=folder,suffix='.jpg',delete=False) as file:
            temporary = Path(file.name)
        try:
            crop.save(temporary,'JPEG',quality=90)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def experiment_image(store, source, photo_id):
    """One bounded working image; no original/identifier copies in experiments."""
    import base64
    import io
    import json
    from PIL import ImageOps
    folder = store.directory / 'preview-cache' / 'experiment-v1'
    destination = folder / (photo_id+'.json')
    with _CROPS:
        if destination.is_file():
            return json.loads(destination.read_text())
        with Image.open(source) as original:
            try:
                image, _ = block_crop(original)
                calibrated = True
            except ValueError:
                # Preserve the existing manual-calibration workflow for off-mat
                # captures, but never embed a full-resolution original.
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1300,1300))
                calibrated = False
        output = io.BytesIO();image.save(output,'JPEG',quality=88)
        result = {'image':'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode(),
                  'mmPerPx':.05 if calibrated else None,
                  'framing':'block-zone' if calibrated else 'uncropped-preview',
                  'width':image.width,'height':image.height}
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.NamedTemporaryFile(dir=folder,mode='w',suffix='.json',delete=False) as file:
            temporary=Path(file.name)
            try:
                json.dump(result,file)
            except BaseException:
                temporary.unlink(missing_ok=True);raise
        try:
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return result
