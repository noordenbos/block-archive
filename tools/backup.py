"""Write a consistent backup outside the archive data directory."""
import argparse
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from block_archive.archive import Archive

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('BLOCK_ARCHIVE_DATA_DIR', Path(__file__).resolve().parents[1] / '.localdata')))
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if not (args.data_dir / 'archive.sqlite3').is_file():
    parser.error('Archive database not found; no new archive was created.')
if args.output.exists():
    parser.error('Output already exists; choose a new filename.')
try:
    Archive(args.data_dir).backup(args.output)
except BaseException:
    args.output.unlink(missing_ok=True)
    raise
print('Archive backup completed. Store it in an approved location.')
