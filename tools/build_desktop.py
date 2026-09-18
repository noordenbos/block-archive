"""Build from explicit public files only. Never copy a working archive into an installer."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from block_archive.desktop import VERSION


def stage_source(stage):
    allowed = set((ROOT/'tools/public-files.txt').read_text().splitlines())
    files = [name for name in sorted(allowed) if name.startswith(('block_archive/', 'static/', 'planner/', 'desktop_resources/'))
             or name in ('desktop_main.py', 'LICENSE', 'tools/planner-assets.txt', 'tools/export_crops.py')]
    for name in files:
        source = ROOT/name
        if source.is_symlink() or not source.is_file() or '.localdata' in source.parts:
            raise ValueError('Nonregular or private input rejected.')
        target = stage/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(ROOT/'packaging/desktop.spec', stage/'desktop.spec')
    shutil.copy2(ROOT/'packaging/entitlements.plist', stage/'entitlements.plist')
    notices = ['Third-party dependencies distributed with Block Archive\n']
    versions = {}
    for dist in sorted(metadata.distributions(), key=lambda d:d.metadata.get('Name','').lower()):
        name = dist.metadata.get('Name', 'Unknown')
        versions[name] = dist.version
        notices.append('\n'+name+' '+dist.version+'\n'+str(dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See included license text.'))
        for file in dist.files or []:
            if any(part.lower() in ('licenses','license','license.txt','license.md','copying','notice') for part in file.parts):
                path = dist.locate_file(file)
                if path.is_file():
                    notices.append(path.read_text(encoding='utf-8', errors='replace'))
    (stage/'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices), encoding='utf-8')
    return {name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in files}, versions


def build(output, installer=True):
    output.mkdir(parents=True, exist_ok=False)
    stage = output/'source'; stage.mkdir()
    hashes, versions = stage_source(stage)
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(output/'cache'))
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', str(output/'dist'),
                    '--workpath', str(output/'work'), str(stage/'desktop.spec')], cwd=stage, env=env, check=True)
    platform_name = {'darwin':'macos','win32':'windows'}.get(sys.platform,'linux')
    arch = 'arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
    binary = output/'dist'/('Block Archive.app/Contents/MacOS/BlockArchive' if sys.platform=='darwin' else 'BlockArchive/BlockArchive'+('.exe' if sys.platform=='win32' else ''))
    subprocess.run([str(binary), '--smoke-test'], check=True, timeout=180)
    packages = output/'installers'; packages.mkdir()
    base = f'BlockArchive-{VERSION}-{platform_name}-{arch}'
    if sys.platform == 'darwin' and installer:
        dmg_source = output/'dmg'; dmg_source.mkdir()
        subprocess.run(['ditto',str(output/'dist/Block Archive.app'),str(dmg_source/'Block Archive.app')],check=True)
        (dmg_source/'Applications').symlink_to('/Applications')
        subprocess.run(['hdiutil','create','-volname','Block Archive','-srcfolder',str(dmg_source),'-ov','-format','UDZO',str(packages/(base+'.dmg'))],check=True)
    elif sys.platform == 'win32' and installer:
        compiler = shutil.which('ISCC.exe') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        subprocess.run([compiler, '/DBuildRoot='+str(output/'dist'), '/DOutputRoot='+str(packages),str(ROOT/'packaging/windows.iss')],check=True)
    else:
        shutil.make_archive(str(packages/base), 'gztar', root_dir=output/'dist', base_dir='BlockArchive')
    info = {'version':VERSION,'platform':platform_name,'architecture':arch,'smoke_test':'passed',
            'signing':'not_verified','source_files':hashes,'dependencies':versions,
            'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in packages.iterdir() if p.is_file()}}
    (packages/(base+'-build.json')).write_text(json.dumps(info,indent=2)+'\n')
    (packages/(base+'-SHA256SUMS.txt')).write_text(''.join(digest+'  '+name+'\n' for name,digest in info['assets'].items()))
    print('Build and packaged smoke test passed. Installer signing is not verified.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    build(args.output.resolve())


if __name__=='__main__':
    main()
