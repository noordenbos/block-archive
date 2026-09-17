"""Project-scoped local JSON saves, separate from the live archive database."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from block_archive.archive import ArchiveError
from block_archive import projects
def atomic(path, writer):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.saving-', dir=path.parent)
    os.close(fd)
    try:
        writer(Path(temporary))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def location(manager, ident):
    directory = manager.directory(ident)
    settings = directory / 'save-location.json'
    base = json.loads(settings.read_text())['folder'] if settings.exists() else ''
    destination = Path(base) / 'BlockArchive' / ident if base else directory / 'saved'
    return {'folder':base, 'destination':str(destination.resolve()), 'default':not bool(base)}


def configure(manager, ident, folder):
    if not isinstance(folder,str) or len(folder)>4096:
        raise ArchiveError(422,'Choose an existing local folder.')
    folder=folder.strip()
    if folder:
        path=Path(folder).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ArchiveError(422,'Enter the full path to an existing folder.')
        folder=str(path.resolve())
        destination=Path(folder)/'BlockArchive'/ident
    else:
        destination=manager.directory(ident)/'saved'
    try:
        destination.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.TemporaryFile(dir=destination):pass
        atomic(manager.directory(ident)/'save-location.json',lambda p:p.write_text(json.dumps({'folder':folder})))
    except OSError as error:
        raise ArchiveError(422,'This folder is not writable. Choose another folder.') from error
    return location(manager,ident)


def save(manager, ident, body, kind):
    destination=Path(location(manager,ident)['destination'])
    try:
        if kind=='project':
            projects.validate_experiments(body)
            path=destination/'project.json'
            atomic(path,lambda p:projects.export_project(manager.archive(ident),manager.info(ident)['name'],body,p))
            atomic(manager.directory(ident)/'restored-experiments.json',lambda p:p.write_text(json.dumps(body)))
        else:
            eid=body.get('experimentId')
            if not isinstance(eid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',eid):
                raise ArchiveError(422,'Invalid experiment ID.')
            projects.validate_experiments({'entries':[{'key':'experiment:'+eid,'value':body}]})
            path=destination/('experiment-'+eid+'.json')
            atomic(path,lambda p:p.write_text(json.dumps(body)))
        return {'path':str(path),'name':body.get('name',manager.info(ident)['name'])}
    except OSError as error:
        raise ArchiveError(422,'Could not save to the selected folder. Check that it is available and writable.') from error


def experiments(manager, ident):
    restored=manager.directory(ident)/'restored-experiments.json'
    entries={e['key']:e for e in json.loads(restored.read_text())['entries']} if restored.exists() else {}
    for path in Path(location(manager,ident)['destination']).glob('experiment-*.json'):
        try:
            state=json.loads(path.read_text());key='experiment:'+state['experimentId']
            entry={'key':key,'value':state};projects.validate_experiments({'entries':[entry]})
            old=entries.get(key)
            if not old or state.get('updated','')>=old['value'].get('updated',''):entries[key]=entry
        except (ValueError,KeyError,ArchiveError):continue
    return {'entries':list(entries.values())}


def browse():
    if sys.platform=='darwin':
        command=['osascript','-e','POSIX path of (choose folder with prompt "Choose a folder for Block Archive saves")']
    elif sys.platform=='win32':
        command=['powershell','-NoProfile','-STA','-Command','Add-Type -AssemblyName System.Windows.Forms; $picker = New-Object System.Windows.Forms.FolderBrowserDialog; if ($picker.ShowDialog() -eq "OK") { $picker.SelectedPath }']
    else:
        command=['zenity','--file-selection','--directory','--title=Choose a folder for Block Archive saves']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        return {'folder':result.stdout.strip() if result.returncode==0 else ''}
    except (OSError,subprocess.TimeoutExpired) as error:
        raise ArchiveError(422,'Folder picker unavailable. Paste the full folder path instead.') from error
