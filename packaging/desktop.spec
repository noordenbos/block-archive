# Run from the sanitized staging directory prepared by tools/build_desktop.py.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import os
import sys
root = Path(SPECPATH)
datas = [(str(root/name), name) for name in ('static', 'planner', 'desktop_resources')]
datas += [(str(root/'tools/planner-assets.txt'), 'tools'), (str(root/'LICENSE'), '.'), (str(root/'THIRD_PARTY_NOTICES.txt'), '.')]
a = Analysis([str(root/'desktop_main.py')], pathex=[str(root)], datas=datas,
             hiddenimports=collect_submodules('uvicorn'), excludes=['pytest','playwright','IPython','notebook'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BlockArchive', debug=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False,
          codesign_identity=os.environ.get('BLOCK_ARCHIVE_CODESIGN_IDENTITY') or None,
          entitlements_file=str(root/'entitlements.plist') if sys.platform=='darwin' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BlockArchive')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Block Archive.app', bundle_identifier='org.blockarchive.desktop',
                 info_plist={'CFBundleShortVersionString':'1.0.0','CFBundleVersion':'1.0.0',
                             'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'14.0'})
