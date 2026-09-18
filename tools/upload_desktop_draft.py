"""Upload installers only to a matching unpublished draft; never publish a release."""
import json
import os
from pathlib import Path
import subprocess
import sys

tag = os.environ['DESKTOP_RELEASE_TAG']
release = json.loads(subprocess.check_output(['gh','release','view',tag,'--repo',os.environ['GITHUB_REPOSITORY'],'--json','isDraft,targetCommitish']))
if not release['isDraft'] or release['targetCommitish'] != os.environ['GITHUB_SHA']:
    raise SystemExit('Release must be a draft targeting this exact source commit.')
files = sorted(Path(sys.argv[1]).iterdir())
if not files or any(not p.is_file() or p.is_symlink() for p in files):
    raise SystemExit('Invalid installer output.')
subprocess.run(['gh','release','upload',tag,'--repo',os.environ['GITHUB_REPOSITORY'],*map(str,files)],check=True)
