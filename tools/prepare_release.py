"""Copy the reviewed release manifest into a new directory, without Git history."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_files():
    return [line.strip() for line in (ROOT / 'tools/release-files.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        parser.error('Destination already exists; use a new directory.')
    files = release_files()
    for relative in files:
        source = ROOT / relative
        if not source.is_file() or source.resolve() != source or not source.is_relative_to(ROOT):
            parser.error('Invalid manifest entry: ' + relative)
    destination.mkdir(parents=True)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    print(f'Copied {len(files)} manifest-listed files. No Git history or remote copied.')


if __name__ == '__main__':
    main()
