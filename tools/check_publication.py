"""Screen tracked source and reachable history without exposing matched values.

Inherited binaries must match the assets reviewed in the clean Spatial Prep root.
This screening does not certify the absence of all identifying information.
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLEAN_BASE = 'eed0534c594661cc8ed67770133de04309cc281a'
PATTERNS = [re.compile(r'\b[A-Z]{1,8}[-:]?\d{2}[-:]\d{3,}\b', re.I),
            re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
            re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
FORBIDDEN = {'.localdata', '.env', 'api-token', 'blokids', 'dummies', 'WORK_HANDOFF.md', 'HANDOFF_ASTRA.md'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--denylist', type=Path, help='Optional private identifier matching list; never distributed.')
    args = parser.parse_args()
    known = [v.strip().casefold() for v in args.denylist.read_text().splitlines() if v.strip()] if args.denylist else []
    manifest = set((ROOT / 'tools/public-files.txt').read_text().splitlines())
    reviewed = git('show', CLEAN_BASE + ':tools/reviewed-assets.sha256').decode().splitlines()
    approved = {}
    for line in reviewed:
        digest, path = line.split('  ', 1)
        approved.setdefault(path, set()).add(digest)
    docs_review = (ROOT / 'tools/reviewed-docs.sha256').read_text().splitlines()
    for line in docs_review:
        digest, path = line.split('  ', 1)
        approved.setdefault(path, set()).add(digest)
    problems = set(); inspected = set()

    def check(path, data, history=False):
        if (any(part in FORBIDDEN for part in Path(path).parts) or Path(path).suffix in ('.sqlite3', '.db', '.zip', '.csv')
                or (not history and path not in manifest)):
            problems.add('Unapproved file present')
        key = (path, hashlib.sha256(data).hexdigest())
        if key in inspected:
            return
        inspected.add(key)
        try:
            text = path + '\n' + data.decode('utf-8')
        except UnicodeDecodeError:
            # Bundled planner media must be byte-identical to the reviewed source assets.
            reviewed_path = path.removeprefix('planner/')
            if key[1] not in approved.get(reviewed_path, set()):
                problems.add('Unreviewed binary content')
            return
        if any(pattern.search(text) for pattern in PATTERNS):
            problems.add('Identifier or credential pattern detected')
        if any(value in text.casefold() for value in known):
            problems.add('Private identifier match detected')

    tracked = set(git('ls-files', '-z').decode().strip('\0').split('\0'))
    if tracked != manifest:
        problems.add('Tracked files differ from public manifest')
    for name in tracked:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            problems.add('Missing or nonregular tracked file')
        else:
            check(name, path.read_bytes())
    commits = git('rev-list', '--all').decode().splitlines()
    for commit in commits:
        message = git('show', '-s', '--format=%B', commit).decode()
        if any(pattern.search(message) for pattern in PATTERNS) or any(v in message.casefold() for v in known):
            problems.add('Commit message needs review')
        for entry in git('ls-tree', '-rz', commit).split(b'\0'):
            if not entry:
                continue
            metadata, name = entry.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            if mode not in ('100644', '100755') or kind != 'blob':
                problems.add('Nonregular file in history')
                continue
            check(name.decode(), git('cat-file', 'blob', oid), True)
    print(f'Screened {len(tracked)} tracked files, {len(commits)} commits and {len(inspected)} unique file versions.')
    for problem in sorted(problems):
        print('FAIL:', problem, '(matched values withheld)')
    print(f'{len(problems)} findings. This is screening, not a guarantee of de-identification.')
    raise SystemExit(bool(problems))


if __name__ == '__main__':
    main()
