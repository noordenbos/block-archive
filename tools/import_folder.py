"""Copy a local photo folder into the private, searchable import inbox."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive import Archive, ArchiveError


def import_folder(store, source, labels=None):
    readings = {row['filename']: row for row in (labels or [])}
    counts, records = Counter(), []
    for path in sorted(source.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
            counts['ignored'] += 1
            continue
        reading = readings.get(path.name, {})
        try:
            image_id, created = store.import_image(path,
                label_text='\n'.join(line['text'] for line in reading.get('text', [])),
                barcodes=reading.get('barcodes', []))
            outcome = 'imported' if created else 'already_present'
            records.append({'filename': path.name, 'id': image_id, 'outcome': outcome})
            counts[outcome] += 1
        except (ArchiveError, OSError) as exc:
            # Detailed paths and identifiers stay out of console output.
            records.append({'filename': path.name, 'outcome': 'failed', 'reason': type(exc).__name__})
            counts['failed'] += 1
    return dict(counts), records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('BLOCK_ARCHIVE_DATA_DIR', Path(__file__).resolve().parents[1] / '.localdata')))
    parser.add_argument('--labels-json', type=Path, help='Private output from tools/read_labels.swift')
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error('Source folder is unavailable.')
    store = Archive(args.data_dir)
    labels = json.loads(args.labels_json.read_text()) if args.labels_json else []
    counts, records = import_folder(store, args.source, labels)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = store.directory / ('import-report-' + stamp + '.json')
    fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as target:
        json.dump({'counts': counts, 'source': str(args.source.resolve()), 'records': records}, target, indent=2)
    print(json.dumps(counts, sort_keys=True))
    print('Private import report saved in the data directory. Source files were not modified.')
    return 1 if counts.get('failed') else 0


if __name__ == '__main__':
    sys.exit(main())
