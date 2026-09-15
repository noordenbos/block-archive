"""Synthetic export checks; no private photos or identifiers are test fixtures."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io
import numpy as np
from PIL import Image
import pytest
from tools.export_crops import capture_timestamp, pair_photos, block_crop


def photo(key, role, second, code='SYNTHETIC-CODE'):
    return {'image_id': key, 'view': role, 'barcode_code': code, 'source_filename': key+'.jpg',
            'capture_timestamp': {'value': f'2026-01-01T12:00:{second:02d}.123-07:00', 'timezone_known': True}}


def test_capture_preserves_exif_offset_subseconds_and_does_not_use_import_time():
    image = Image.new('RGB', (20,20))
    image.getexif()[34665] = {36867: '2026:01:01 12:34:56', 36881: '-07:00', 37521: '007'}
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', exif=image.getexif())
    buffer.seek(0)
    stamp = capture_timestamp(Image.open(buffer), 'camera.jpg')
    assert stamp['value'] == '2026-01-01T12:34:56.007-07:00'
    assert stamp['timezone_known'] and stamp['subsecond_digits'] == 3
    unknown = capture_timestamp(Image.new('RGB',(20,20)), 'camera.jpg')
    assert unknown['value'] is None and not unknown['timezone_known']
    fallback = capture_timestamp(Image.new('RGB',(20,20)), 'IMG_20260101_123456123.MP.jpg')
    assert fallback['value'] == '2026-01-01T12:34:56.123'
    assert fallback['source'] == 'camera filename' and not fallback['timezone_known']


def test_pairs_use_barcode_not_adjacent_filename_and_keep_missing_view():
    rows = [photo('a','cassette_side',1), photo('b','cassette_side',2,'SECOND'),
            photo('c','tissue_face',3,'SECOND'), photo('d','tissue_face',4), photo('e','cassette_side',5,'SINGLE')]
    items = pair_photos(rows)
    sets = [{p['image_id'] for p in item['images']} for item in items]
    assert sets == [{'a','d'}, {'b','c'}, {'e'}]
    assert items[0]['images'][0]['view'] == 'tissue_face'
    assert items[2]['pairing_status'] == 'review_required'
    assert all(item['block_code'] is None for item in items)
    assert [item['item_id'] for item in items] == [item['item_id'] for item in pair_photos(list(reversed(rows)))]


def test_repeated_code_pairs_are_provisional_and_same_faces_do_not_pair():
    rows = [photo('a','cassette_side',1), photo('b','tissue_face',5),
            photo('c','cassette_side',50), photo('d','tissue_face',54)]
    items = pair_photos(rows)
    assert [{p['image_id'] for p in item['images']} for item in items] == [{'a','b'}, {'c','d'}]
    assert all('Repeated barcode' in item['review_notes'][0] for item in items)
    assert len(pair_photos([photo('a','cassette_side',1),photo('b','cassette_side',2)])) == 2
    unclear = pair_photos([photo('a','cassette_side',1),photo('b','unknown',2)])[0]
    assert unclear['pairing_status'] == 'review_required'


def test_no_markers_never_exports_full_photo_as_crop():
    with pytest.raises(ValueError, match='markers'):
        block_crop(Image.fromarray(np.full((800,600,3), 255, dtype=np.uint8)))
