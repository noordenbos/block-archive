"""Exercise rendered label PDFs and rotated captures using only generated IDs."""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image, ImageDraw
from label_pdf import parse_ids, pdf_bytes, qr_png
from vision import analyze

ROOT = Path(__file__).resolve().parents[1]
ids = [f'TEST-BLOCK-{i:04d}' for i in range(1, 74)] + ['TEST:74', 'TEST-75,PART', 'TEST-76']
assert parse_ids('block_id\nTEST-0001\nTEST-0001\nTEST-0002\n') == ['TEST-0001', 'TEST-0002']
for invalid in ('', 'a' * 121, 'bad\x00id'):
    try:
        parse_ids(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid ID input accepted')
pdf = pdf_bytes(ids)
with pdfium.PdfDocument(pdf) as document:
    decoded = []
    for page in document:
        image = np.array(page.render(scale=3).to_pil().convert('RGB'))
        for row in range(5):
            for col in range(2):
                x = int((14 + col * 91) * 72 / 25.4 * 3)
                y = int((25 + row * 48) * 72 / 25.4 * 3)
                cell = image[y:y + int(48 * 72 / 25.4 * 3), x:x + int(91 * 72 / 25.4 * 3)]
                value = cv2.QRCodeDetector().detectAndDecode(cell)[0]
                if not value:
                    ok, values, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(cell)
                    value = values[0] if ok and len(values) == 1 else ''
                if not value:
                    # Text can distract the decoder: isolate the printed QR area.
                    unit = 72 / 25.4 * 3
                    patch = cell[int(7*unit):int(41*unit), int(2*unit):int(36*unit)]
                    for factor in (1, .75, 1.25, 2):
                        value = cv2.QRCodeDetector().detectAndDecode(cv2.resize(patch, None, fx=factor, fy=factor))[0]
                        if value:
                            break
                if value:
                    decoded.append(value)
    assert decoded == ids, ('Missing synthetic IDs', set(ids) - set(decoded))
    assert all(ident in ''.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages) for ident in ids)

# The print reference and generated QR form a synthetic capture; no source photos.
for ident in ('TEST-CAPTURE-0001', 'TEST-CAPTURE-0002'):
    capture = Image.open(ROOT / 'artefacts/preview/FFPE-photography-A4.png').convert('RGB')
    qr = Image.open(io.BytesIO(qr_png(ident))).convert('RGB').resize((100, 100), Image.Resampling.NEAREST)
    capture.paste(qr, (260, 733))
    ImageDraw.Draw(capture).text((375, 780), ident, fill='black')
    for angle in (0, 90, 180, 270):
        out = io.BytesIO()
        capture.rotate(angle, expand=True).save(out, format='PNG')
        result = analyze(out.getvalue())
        assert result['qrValues'] == [ident], result['qrValues']
        assert result['calibration'] is not None
        assert result['registration']['accepted']
        assert result['rotationDegrees'] is not None
        assert set(result['markerIds']) == {0, 1, 2, 3}
        assert abs(((result['rotationDegrees'] + angle + 180) % 360) - 180) < 1
print('PASS: 76 synthetic rendered labels, input validation, and two generated captures in four rotations.')
