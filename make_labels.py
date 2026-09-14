"""Generate labels locally using the same generator as the app."""
import argparse
from pathlib import Path
from label_pdf import parse_ids, pdf_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='One-column CSV of block IDs')
    parser.add_argument('output', type=Path, help='Destination PDF (keep outside the repository)')
    args = parser.parse_args()
    ids = parse_ids(args.source.read_text(encoding='utf-8-sig'))
    args.output.write_bytes(pdf_bytes(ids))
    print(f'Created {len(ids)} labels.')


if __name__ == '__main__':
    main()
