"""Export block-zone crops, photo timestamps and paired views from the private inbox."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import uuid
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Ordered corners on the clean release's A4 reference; Letter uses the same mat geometry.
REFERENCE = {
    0: [[148.420,178.157],[233.324,178.195],[233.309,263.033],[148.438,263.071]],
    1: [[658.558,178.172],[743.469,178.167],[743.453,263.062],[658.573,263.057]],
    2: [[658.573,900.943],[743.453,900.938],[743.472,985.738],[658.556,985.734]],
    3: [[148.438,900.929],[233.309,900.967],[233.327,985.712],[148.416,985.747]],
}
ROLES = {'tissue_face', 'cassette_side', 'unknown'}
ROLE_LABELS = {'tissue_face': 'Tissue face', 'cassette_side': 'Cassette side', 'unknown': 'Other face - review'}


def capture_timestamp(image, filename):
    exif = image.getexif()
    camera = exif.get_ifd(34665)
    original = camera.get(36867, exif.get(36867))
    if original:
        stamp = datetime.strptime(str(original), '%Y:%m:%d %H:%M:%S')
        value = stamp.isoformat(timespec='seconds')
        fractional = str(camera.get(37521, exif.get(37521, ''))).strip()
        if fractional and re.fullmatch(r'[0-9]+', fractional):
            value += '.' + fractional
        offset = str(camera.get(36881, exif.get(36881, ''))).strip()
        if offset and re.fullmatch(r'[+-][0-9]{2}:[0-9]{2}', offset):
            datetime.fromisoformat(value + offset)  # Reject invalid offsets.
            value += offset
        else:
            offset = None
        return {'value': value, 'source': 'EXIF DateTimeOriginal', 'utc_offset': offset,
                'timezone_known': bool(offset), 'subsecond_digits': len(fractional) if fractional.isdigit() else 0}
    match = re.search(r'(?:^|_)([0-9]{8})_([0-9]{6})([0-9]{3})?(?:\.|$)', filename)
    if match:
        value = datetime.strptime(match[1] + match[2], '%Y%m%d%H%M%S').isoformat()
        if match[3]:
            value += '.' + match[3]
        return {'value': value, 'source': 'camera filename', 'utc_offset': None,
                'timezone_known': False, 'subsecond_digits': len(match[3] or '')}
    return {'value': None, 'source': 'unavailable', 'utc_offset': None,
            'timezone_known': False, 'subsecond_digits': 0}


def block_crop(image):
    """Register markers at reduced size, resample the crop from full-resolution pixels."""
    oriented = ImageOps.exif_transpose(image).convert('RGB')
    small = oriented.copy()
    small.thumbnail((2200, 2200))
    array = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2BGR)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), params)
    corners, ids, _ = detector.detectMarkers(array)
    markers = {} if ids is None else {int(i): c[0] for i, c in zip(ids.flatten(), corners) if int(i) in REFERENCE}
    present = sorted(markers)
    if len(present) < 3:
        raise ValueError('At least three mat markers are required; no full-photo fallback is exported.')
    src = np.concatenate([markers[i] for i in present]).astype(np.float32)
    dst = np.concatenate([REFERENCE[i] for i in present]).astype(np.float32)
    h, _ = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
    if h is None:
        raise ValueError('Mat registration failed.')
    errors = np.linalg.norm(cv2.perspectiveTransform(src[None], h)[0] - dst, axis=1)
    rms = float(np.sqrt(np.mean(errors ** 2)))
    if rms > 2 or float(errors.max()) > 4:
        raise ValueError('Mat registration failed its residual check.')
    zone = np.array([[1300/279, 0, -296*1300/279], [0, 1100/237, -419*1100/237], [0, 0, 1]], dtype=float)
    shrink = np.diag([small.width/oriented.width, small.height/oriented.height, 1.])
    transform = zone @ h @ shrink
    full = cv2.cvtColor(np.asarray(oriented), cv2.COLOR_RGB2BGR)
    crop = cv2.warpPerspective(full, transform, (1300, 1100), borderValue=(255, 255, 255))
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), {
        'method': 'marker_registered_block_zone', 'reference_zone_mm': [65, 55],
        'output_size_px': [1300, 1100], 'oriented_source_size_px': list(oriented.size),
        'source_coordinate_frame': 'EXIF-oriented pixels', 'homography_source_to_crop': transform.tolist(),
        'marker_count': len(present), 'rms_reference_pixels': rms,
        'note': 'Paper-plane crop geometry; not a measurement of the raised block.'}


def time_key(photo):
    value = photo['capture_timestamp']['value']
    if value:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo:
            return stamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        return stamp.isoformat()
    return '9999-' + photo['source_filename']


def gap_seconds(a, b):
    if not a['capture_timestamp']['value'] or not b['capture_timestamp']['value']:
        return None
    x = datetime.fromisoformat(a['capture_timestamp']['value'])
    y = datetime.fromisoformat(b['capture_timestamp']['value'])
    if bool(x.tzinfo) != bool(y.tzinfo):
        return None
    return abs((x - y).total_seconds())


def pair_photos(photos):
    groups = defaultdict(list)
    for photo in photos:
        groups[photo['barcode_code'] or photo['image_id']].append(photo)
    items = []
    for group in groups.values():
        remaining = sorted(group, key=time_key)
        repeated = len(group) > 2
        while remaining:
            first = remaining.pop(0)
            partner = None
            if remaining and first['barcode_code']:
                candidates = [p for p in remaining if p['view'] != first['view'] or p['view'] == 'unknown']
                candidates = [p for p in candidates if gap_seconds(first, p) is not None and gap_seconds(first, p) <= 300]
                if candidates:
                    partner = min(candidates, key=lambda p: gap_seconds(first, p))
                    remaining.remove(partner)
            views = [first] + ([partner] if partner else [])
            views.sort(key=lambda p: {'tissue_face': 0, 'unknown': 1, 'cassette_side': 2}[p['view']])
            issues = []
            if not partner:
                issues.append('Missing matching view.')
            if repeated:
                issues.append('Repeated barcode: capture-time pairing is provisional; confirm cassette identity.')
            if any(p['view'] == 'unknown' for p in views):
                issues.append('Face assignment needs review.')
            if any(not p['capture_timestamp']['timezone_known'] for p in views):
                issues.append('Capture timezone unavailable for at least one image.')
            stable = '|'.join(sorted(p['image_id'] for p in views))
            items.append({'item_id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'block-archive-export:' + stable)),
                          'barcode_code': first['barcode_code'], 'block_code': None,
                          'identity_status': 'unconfirmed_barcode_reading',
                          'pairing_status': 'review_required' if issues else 'matched_barcode_and_opposite_views',
                          'pairing_method': 'exact selected barcode, opposite views, capture gap at most 300 seconds',
                          'capture_gap_seconds': gap_seconds(first, partner) if partner else None,
                          'review_notes': issues, 'images': views})
    items.sort(key=lambda item: min(time_key(p) for p in item['images']))
    for index, item in enumerate(items, 1):
        item['item_number'] = index
    return items


def wrap_text(c, text, x, y, width, font='Helvetica', size=9, leading=13):
    c.setFont(font, size)
    words = text.split()
    line = ''
    for word in words:
        trial = (line + ' ' + word).strip()
        if line and c.stringWidth(trial, font, size) > width:
            c.drawString(x, y, line); y -= leading; line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line); y -= leading
    return y


def render_pdf(path, manifest, crop_root, synthetic=False):
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle('Block Archive - paired block photographs')
    c.setAuthor('Block Archive')
    ink, teal, muted = '#203b38', '#216b5b', '#657870'
    items = manifest['items']; pages = 1 + math.ceil(len(items)/2)
    def footer(page):
        c.setStrokeColor(colors.HexColor('#dbe3dc')); c.line(32, 35, width-32, 35)
        c.setFillColor(colors.HexColor(muted)); c.setFont('Helvetica', 8)
        c.drawString(32, 22, 'Block Archive | Cropped photo export')
        c.drawRightString(width-32, 22, f'{page} / {pages}')
    c.setFillColor(colors.HexColor(teal)); c.rect(0, height-14, width, 14, fill=1, stroke=0)
    c.setFont('Helvetica-Bold', 11); c.drawString(40, height-76, 'BLOCK ARCHIVE')
    c.setFillColor(colors.HexColor(ink)); c.setFont('Helvetica-Bold', 30)
    c.drawString(40, height-124, 'Paired block photographs')
    c.setFillColor(colors.HexColor(muted))
    y = wrap_text(c, 'Tissue face and cassette side, coupled in a single record with each photograph\'s capture timestamp.', 40, height-158, width-80, size=12, leading=18)
    counts = manifest['counts']; y -= 42
    for value, label, x in [(counts['images'], 'block-zone crops', 40), (counts['paired_items'], 'two-image items', 225), (counts['unpaired_items'], 'unmatched view', 410)]:
        c.setFillColor(colors.HexColor(teal)); c.setFont('Helvetica-Bold', 34); c.drawString(x, y, str(value))
        c.setFillColor(colors.HexColor(muted)); c.setFont('Helvetica', 10); c.drawString(x, y-23, label)
    y -= 84
    notes = [
        ('Image framing', 'Each image shows the registered 65 x 55 mm block zone. Crops are resampled from the original image pixels and retain the tissue and cassette label.'),
        ('Capture time', 'Timestamps come from EXIF DateTimeOriginal where available. Subseconds and timezone offsets are retained. Import time is not substituted for capture time.'),
        ('Pairing and identity', 'Items are grouped by the selected barcode and capture proximity, with the two faces reviewed visually. Barcode readings are unconfirmed identifiers; they do not establish a verified block record.'),
        ('Review flags', f"{counts['review_items']} items have explicit review notes. Repeated barcodes, an unclear face and a missing counterpart are kept visible in their items."),
        ('Machine-readable companion', 'The companion ZIP contains manifest.json, one-item-per-line pairs.jsonl, crop JPEGs and a README. Image IDs, crop hashes, capture timestamps and pairing evidence link the two formats.'),
    ]
    for title, text in notes:
        c.setFillColor(colors.HexColor(ink)); c.setFont('Helvetica-Bold', 11); c.drawString(40, y, title)
        c.setFillColor(colors.HexColor(muted)); y = wrap_text(c, text, 40, y-19, width-80, size=10, leading=15)-22
    c.setFont('Helvetica', 8); c.drawString(40, 62, 'Generated ' + manifest['generated_at'])
    footer(1); c.showPage()
    for start in range(0, len(items), 2):
        c.setFillColor(colors.HexColor(ink)); c.setFont('Helvetica-Bold', 14)
        c.drawString(32, height-40, 'Block photographs')
        for slot, item in enumerate(items[start:start+2]):
            top = height-72-slot*355
            code = f"SYNTHETIC GROUP {item['item_number']:03}" if synthetic else (item['barcode_code'] or 'Unresolved barcode')
            c.setFillColor(colors.HexColor(teal)); c.setFont('Helvetica-Bold', 9)
            c.drawString(32, top, f"ITEM {item['item_number']:03}")
            c.setFillColor(colors.HexColor(ink)); code_size = 15
            while c.stringWidth(code, 'Helvetica-Bold', code_size) > width-65 and code_size > 8:
                code_size -= .5
            c.setFont('Helvetica-Bold', code_size); c.drawString(32, top-23, code)
            images = item['images']
            tissue = next((p for p in images if p['view'] == 'tissue_face'), None)
            cassette = next((p for p in images if p['view'] == 'cassette_side'), None)
            other = next((p for p in images if p['view'] == 'unknown'), None)
            left = tissue or other
            right = cassette or next((p for p in images if p is not left), None)
            for column, photo in enumerate((left, right)):
                x = 32+column*272; frame_w, frame_h = 259, 219
                c.setFillColor(colors.HexColor(muted)); c.setFont('Helvetica-Bold', 10)
                label = ROLE_LABELS[photo['view']] if photo else ('Tissue face' if column == 0 else 'Cassette side')
                c.drawString(x, top-46, label)
                c.setFillColor(colors.HexColor('#f2f4f0')); c.roundRect(x, top-277, frame_w, frame_h, 5, fill=1, stroke=0)
                if photo:
                    source = crop_root / photo['crop_path']
                    with Image.open(source) as original_crop:
                        preview = original_crop.convert('RGB')
                        preview.thumbnail((1000, 1000))
                        preview_bytes = io.BytesIO()
                        preview.save(preview_bytes, 'JPEG', quality=85, optimize=True)
                    preview_bytes.seek(0)
                    c.drawImage(ImageReader(preview_bytes), x, top-277, width=frame_w, height=frame_h, preserveAspectRatio=True, anchor='c')
                    value = photo['capture_timestamp']['value'] or 'Capture time unavailable'
                    c.setFillColor(colors.HexColor(ink)); c.setFont('Helvetica', 8)
                    c.drawString(x, top-292, value.replace('T', ' '))
                    c.setFillColor(colors.HexColor(muted)); c.setFont('Helvetica', 7)
                    c.drawString(x, top-305, 'EXIF capture time' if photo['capture_timestamp']['source'].startswith('EXIF') else photo['capture_timestamp']['source'])
                else:
                    c.setFillColor(colors.HexColor(muted)); c.setFont('Helvetica', 11)
                    c.drawCentredString(x+frame_w/2, top-173, 'No matching photograph')
            note = ' '.join(item['review_notes']) or 'Matched barcode and opposite views | Block identity unconfirmed'
            c.setFillColor(colors.HexColor('#8b6027' if item['review_notes'] else muted))
            wrap_text(c, note, 32, top-325, width-64, size=8, leading=10)
        footer(2+start//2); c.showPage()
    c.save()


def export(data_dir, output, review):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output/'crops').mkdir(mode=0o700)
    (output/'output/pdf').mkdir(parents=True, mode=0o700)
    with sqlite3.connect(f'file:{data_dir.resolve() / "archive.sqlite3"}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM import_images ORDER BY filename,id')]
    photos = []
    for row in rows:
        record = review.get(row['id'], {})
        role = record.get('view', 'unknown')
        if role not in ROLES:
            raise ValueError('Invalid view assignment in private review file.')
        codes = json.loads(row['barcodes'])
        selected = record.get('barcode_code', codes[0] if len(codes) == 1 else None)
        if selected is not None and selected not in codes:
            raise ValueError('Selected barcode is absent from source readings.')
        source = data_dir/'images'/(row['id']+'.source')
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Stored original does not match its recorded hash.')
        with Image.open(source) as image:
            timestamp = capture_timestamp(image, row['filename'])
            crop, geometry = block_crop(image)
        relative = 'crops/' + row['id'] + '.jpg'
        crop.save(output/relative, 'JPEG', quality=95, subsampling=0)
        photos.append({'image_id': row['id'], 'source_filename': row['filename'], 'source_sha256': row['sha256'],
                       'barcode_code': selected, 'barcode_candidates': codes, 'view': role,
                       'view_assignment_method': record.get('method', 'unassigned'),
                       'view_assignment_note': record.get('note', ''),
                       'capture_timestamp': timestamp, 'crop_path': relative,
                       'crop_sha256': hashlib.sha256((output/relative).read_bytes()).hexdigest(), 'crop_geometry': geometry})
    items = pair_photos(photos)
    manifest = {'schema_version': '1.0', 'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'source': 'Block Archive photo inbox',
                'counts': {'images': len(photos), 'items': len(items), 'paired_items': sum(len(i['images']) == 2 for i in items),
                           'unpaired_items': sum(len(i['images']) == 1 for i in items), 'review_items': sum(bool(i['review_notes']) for i in items)},
                'items': items}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n')
    (output/'pairs.jsonl').write_text(''.join(json.dumps(item, ensure_ascii=False)+'\n' for item in items))
    (output/'README.txt').write_text('''Block Archive cropped photo export, schema 1.0

manifest.json: export metadata and items array.
pairs.jsonl: one complete item per line; the same items as manifest.json.
crops/: JPEG block-zone crops; no source photographs are included.

An item couples tissue_face and cassette_side in its images array. Unknown
faces and missing counterparts remain explicit. item_id and image_id are
stable identifiers. barcode_code is a decoded, unconfirmed reading, not a
verified block identity. block_code is null until a separate verified identity
is established; do not use barcode_code as a unique specimen primary key.

capture_timestamp.value is ISO 8601 with recorded fractional seconds and
UTC offset when available. A missing offset is not UTC. Its source field
distinguishes EXIF from filename fallback. Import time is never used instead.

Repeated barcode groups are provisionally split by opposite views and nearest
capture time (maximum 300 seconds). Review notes flag ambiguity. Visual face
assignments are recorded in view_assignment_method. Missing images are not
synthesized. The report contains one or two images for every exported item.

crop_geometry records the transform from EXIF-oriented original pixels to
the crop. The 65 x 55 mm reference is the paper-plane zone, not a calibrated
measurement of tissue or cassette height. JPEG crops strip original metadata;
timestamps remain explicit in JSON and the report. Hashes cover source and
crop bytes for provenance. source_filename refers to the original local file.
''')
    render_pdf(output/'output/pdf/block-photo-report.pdf', manifest, output)
    with zipfile.ZipFile(output/'block-crops.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in ['manifest.json', 'pairs.jsonl', 'README.txt']:
            bundle.write(output/name, name)
        for path in sorted((output/'crops').iterdir()):
            bundle.write(path, path.relative_to(output))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1]/'.localdata')
    parser.add_argument('--output', type=Path, required=True, help='New private directory; must not exist')
    parser.add_argument('--review-json', type=Path, help='Private mapping of image UUID to view, barcode_code, method and note')
    args = parser.parse_args()
    os.umask(0o077)
    review = json.loads(args.review_json.read_text()) if args.review_json else {}
    manifest = export(args.data_dir, args.output, review)
    print(json.dumps(manifest['counts'], sort_keys=True))
    print('Created crop-only ZIP, JSON/JSONL and paired PDF in the private output directory.')


if __name__ == '__main__':
    main()
