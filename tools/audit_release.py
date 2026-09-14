"""Screen release files and reachable Git history; never print matched values.

This is a conservative screening tool, not an exhaustive PHI detector.
Binary assets require reviewed checksums. Review their visible content separately.
"""
import argparse
import hashlib
import io
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'specimen-style identifier': re.compile(r'\b[A-Z]{1,8}[-:]?\d{2}[-:]\d{3,}\b', re.I),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'cloud access key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'patient record field': re.compile(r'\b(?:patient_name|patient_id|medical_record_number|date_of_birth)\s*[:=]\s*[\"\'][^\"\']+'),
}
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--denylist', type=Path, help='Private text file: one known identifier per line')
    args = parser.parse_args()
    allowed = set((ROOT / 'tools/release-files.txt').read_text().splitlines()) - {''}
    hashes = dict(line.split('  ', 1)[::-1] for line in (ROOT / 'tools/reviewed-assets.sha256').read_text().splitlines())
    denied = [line.strip().casefold() for line in args.denylist.read_text().splitlines() if line.strip()] if args.denylist else []
    failures = set()
    screened = set()

    def text_check(text, context):
        text = unquote(text)
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                failures.add((context, name))
        if any(value in text.casefold() for value in denied):
            failures.add((context, 'private denylist match'))

    def inspect(path, data, context):
        text_check(path, context)
        key = (path, hashlib.sha256(data).hexdigest())
        if key in screened:
            return
        screened.add(key)
        if path not in allowed:
            failures.add((context, 'file not in release manifest'))
        suffix = Path(path).suffix.lower()
        if suffix in ('.png', '.pdf'):
            if hashes.get(path) != key[1]:
                failures.add((context, 'binary not in reviewed asset checksums'))
            if suffix == '.png':
                with Image.open(io.BytesIO(data)) as image:
                    text_check(str(image.info), context)
                    if image.getexif():
                        failures.add((context, 'image has EXIF metadata'))
            else:
                pdf = PdfReader(io.BytesIO(data))
                text_check(str(pdf.metadata), context)
                if pdf.attachments or pdf.trailer['/Root'].get('/Metadata'):
                    failures.add((context, 'PDF attachments or XMP require review'))
                for page in pdf.pages:
                    text_check(page.extract_text(), context)
                    if page.get('/Annots'):
                        failures.add((context, 'PDF annotations require review'))
        else:
            try:
                text_check(data.decode('utf-8'), context)
            except UnicodeDecodeError:
                failures.add((context, 'unexpected binary file'))

    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            failures.add((str(relative), 'symlink not permitted'))
        elif path.is_file():
            inspect(relative.as_posix(), path.read_bytes(), relative.as_posix())
    for missing in allowed - {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}:
        failures.add((missing, 'manifest file missing'))

    commits = 0
    if (ROOT / '.git').exists():
        history = subprocess.check_output(['git', 'rev-list', '--all'], cwd=ROOT, text=True).splitlines()
        for commit in history:
            commits += 1
            message = subprocess.check_output(['git', 'show', '-s', '--format=%B', commit], cwd=ROOT, text=True)
            text_check(message, 'commit message')
            tree = subprocess.check_output(['git', 'ls-tree', '-rz', commit], cwd=ROOT)
            for record in tree.split(b'\0'):
                if not record:
                    continue
                metadata, raw_path = record.split(b'\t', 1)
                mode, kind, oid = metadata.decode().split()
                path = raw_path.decode()
                if mode not in ('100644', '100755') or kind != 'blob':
                    failures.add((path, 'nonregular history entry'))
                    continue
                data = subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=ROOT)
                inspect(path, data, 'history:' + path)
    for context, reason in sorted(failures):
        # Paths in the new release manifest are safe; suppress other paths.
        safe = context if context.removeprefix('history:') in allowed else '[unlisted content]'
        print(f'FAIL: {safe}: {reason}')
    print(f'Screened {len(screened)} unique file versions and {commits} reachable commits; {len(failures)} findings.')
    print('Visible media review and maintainer publication approval remain required.')
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
