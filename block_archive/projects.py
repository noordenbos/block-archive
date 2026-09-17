"""Isolated local projects and portable JSON archives; no executable SQL in imports."""
import base64
from contextvars import ContextVar
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import threading
from urllib.parse import urlsplit
from uuid import UUID
from PIL import Image
from block_archive.archive import Archive, ArchiveError, MAX_IMAGE_BYTES, MAX_PIXELS, now, uid
from block_archive import inventory
TABLES = ('blocks', 'photos', 'external_links', 'events', 'import_images', 'inventory_labels',
          'planning_selections', 'inventory_metadata', 'capture_analysis', 'capture_assignments', 'capture_reviews')
MAX_PROJECT_BYTES = 2 * 1024 ** 3
MAX_EXPERIMENT_BYTES = 256 * 1024 ** 2
CURRENT_PROJECT = ContextVar('archive_project', default='local')


def validate_experiments(value):
    if not isinstance(value, dict) or set(value) != {'entries'} or not isinstance(value['entries'], list) or len(value['entries']) > 1000:
        raise ArchiveError(422, 'Invalid experiment collection.')
    keys = set()
    for entry in value['entries']:
        if not isinstance(entry, dict) or set(entry) != {'key', 'value'}:
            raise ArchiveError(422, 'Invalid saved experiment entry.')
        key, state = entry['key'], entry['value']
        if not isinstance(key, str) or (key != 'current' and not re.fullmatch(r'experiment:[A-Za-z0-9_-]{1,120}', key)) or key in keys:
            raise ArchiveError(422, 'Invalid or repeated experiment key.')
        keys.add(key)
        if (not isinstance(state, dict) or state.get('version') != 1 or not isinstance(state.get('name'), str)
                or not isinstance(state.get('blocks'), list) or len(state['blocks']) > 1000
                or not isinstance(state.get('slides'), list) or not 1 <= len(state['slides']) <= 200
                or not isinstance(state.get('config'), dict)):
            raise ArchiveError(422, 'Invalid experiment structure.')
    return value


class ProjectManager:
    def __init__(self, root, initial):
        self.root = Path(root)
        self.folder = self.root / 'projects'
        self.folder.mkdir(exist_ok=True, mode=0o700)
        self.initial = initial
        self.stores = {"local": initial}
        self.lock = threading.Lock()

    def directory(self, project_id):
        if project_id == 'local':
            return self.root
        try:
            if str(UUID(project_id)) != project_id:
                raise ValueError()
        except (ValueError, TypeError):
            raise ArchiveError(404, 'Project not found.')
        directory = self.folder / project_id
        if directory.is_symlink() or not (directory / 'project-info.json').is_file():
            raise ArchiveError(404, 'Project not found.')
        return directory

    def info(self, project_id):
        directory = self.directory(project_id)
        if project_id == 'local':
            return {'id':'local', 'name':'Local archive', 'created_at':None}
        return json.loads((directory / 'project-info.json').read_text())

    def list(self):
        return [self.info('local')] + [self.info(path.name) for path in sorted(self.folder.iterdir())
                                      if not path.is_symlink() and (path / 'project-info.json').is_file() and not (path / '.import-pending').exists()]

    def archive(self, project_id):
        directory = self.directory(project_id)
        with self.lock:
            if project_id not in self.stores:
                store = Archive(directory)
                inventory.initialize(store)
                self.stores[project_id] = store
            return self.stores[project_id]

    def create(self, name, pending=False):
        ident = uid(); directory = self.folder / ident
        directory.mkdir(mode=0o700)
        if pending:
            (directory / '.import-pending').touch()
        info = {'id':ident, 'name':name, 'created_at':now()}
        try:
            store = Archive(directory); inventory.initialize(store)
            (directory / 'project-info.json').write_text(json.dumps(info))
        except BaseException:
            shutil.rmtree(directory); raise
        return info


class RequestArchive:
    """Resolve per request, so switching one browser cannot redirect another's writes."""
    def __init__(self, manager):
        self.manager = manager

    def __getattr__(self, name):
        return getattr(self.manager.archive(CURRENT_PROJECT.get()), name)


def export_project(store, name, experiments, destination):
    validate_experiments(experiments)
    with store.connect(write=True) as db, open(destination, 'w', encoding='utf-8') as output:
        tables = {table:[dict(row) for row in db.execute('SELECT * FROM '+table)] for table in TABLES}
        header = {'format':'block-archive-project', 'version':1, 'name':name, 'exported_at':now()}
        output.write(json.dumps(header)[:-1] + ',"archive":{"tables":')
        json.dump(tables,output,ensure_ascii=False)
        output.write(',"images":[')
        first = True
        for row in db.execute('SELECT id FROM photos UNION SELECT id FROM import_images'):
            for suffix in ('.source','.jpg'):
                path = store.images / (row['id']+suffix)
                if not path.is_file():
                    raise ArchiveError(409, 'A source photo is missing. Restore it before saving this project.')
                if not first: output.write(',')
                first = False
                json.dump({'name':path.name,'data':base64.b64encode(path.read_bytes()).decode('ascii')},output)
        output.write(']},"experiments":')
        json.dump(experiments,output,ensure_ascii=False)
        output.write('}')
        if output.tell() > MAX_PROJECT_BYTES:
            raise ArchiveError(413, 'This project exceeds the 2 GB JSON limit. Use archive backups and separate experiment exports.')


def validate_json_columns(table, row):
    fields = {'events':{'data':dict}, 'import_images':{'barcodes':list}, 'inventory_labels':{'labels':list},
              'planning_selections':{'payload':dict}, 'inventory_metadata':{'fields':dict}, 'capture_analysis':{'payload':dict}}
    for key, expected in fields.get(table, {}).items():
        parsed = json.loads(row[key])
        if not isinstance(parsed, expected):
            raise ValueError('Invalid embedded JSON.')
        if table in ('import_images','inventory_labels') and not all(isinstance(value,str) for value in parsed):
            raise ValueError('Invalid label list.')
        if table == 'inventory_metadata':
            from block_archive import metadata
            metadata.clean_fields(parsed)
        if table == 'capture_analysis':
            if parsed.get('qrValues') is not None and (not isinstance(parsed['qrValues'],list) or not all(isinstance(value,str) for value in parsed['qrValues'])):
                raise ValueError('Invalid QR values.')


def import_project(manager, document):
    if not isinstance(document,dict) or document.get('format') != 'block-archive-project' or document.get('version') != 1:
        raise ArchiveError(422, 'Choose a complete Block Archive project JSON. Open individual experiment files inside the planner.')
    name = document.get('name')
    if not isinstance(name,str) or not name.strip() or len(name) > 160:
        raise ArchiveError(422, 'Invalid project name.')
    archive = document.get('archive',{})
    if not isinstance(archive,dict) or not isinstance(archive.get('tables'),dict) or set(archive['tables']) != set(TABLES) or not isinstance(archive.get('images'),list):
        raise ArchiveError(422, 'The project archive is incomplete or unsupported.')
    experiments = validate_experiments(document.get('experiments'))
    if len(json.dumps(experiments).encode()) > MAX_EXPERIMENT_BYTES:
        raise ArchiveError(413, 'The experiment collection exceeds 256 MB.')
    info = manager.create(name.strip() + ' (imported)' if len(name.strip()) <= 149 else name.strip(), pending=True)
    directory = manager.directory(info['id'])
    try:
        store = manager.archive(info['id'])
        with store.connect(write=True) as db:
            for table in TABLES:
                columns = [row[1] for row in db.execute('PRAGMA table_info('+table+')')]
                rows = archive['tables'][table]
                if not isinstance(rows,list) or len(rows) > 100000:
                    raise ValueError('Invalid archive table.')
                for row in rows:
                    if table == 'capture_reviews' and isinstance(row,dict) and 'missing_side' not in row:
                        row = {**row, 'missing_side':''}
                    if not isinstance(row,dict) or set(row) != set(columns):
                        raise ValueError('Unsupported archive columns.')
                    if table == 'capture_reviews' and row['missing_side'] not in ('','tissue','identifier'):
                        raise ValueError('Invalid missing-side exception.')
                    validate_json_columns(table,row)
                    if table in ('blocks','photos','import_images') and str(UUID(row['id'])) != row['id']:
                        raise ValueError('Invalid record ID.')
                    if table == 'external_links' and row['url'] and urlsplit(row['url']).scheme not in ('http','https'):
                        raise ValueError('Invalid external reference URL.')
                    db.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', [row[column] for column in columns])
            expected = {}
            for table in ('photos','import_images'):
                for row in archive['tables'][table]:
                    for suffix in ('.source','.jpg'):
                        key = row['id']+suffix
                        if key in expected and expected[key]['sha256'] != row['sha256']:
                            raise ValueError('Inconsistent image checksum.')
                        expected[key] = row
            seen = set()
            if len(archive['images']) != len(expected):
                raise ValueError('Missing or extra image files.')
            for image in archive['images']:
                if not isinstance(image,dict) or set(image) != {'name','data'} or image['name'] not in expected or image['name'] in seen:
                    raise ValueError('Invalid image filename.')
                seen.add(image['name'])
                if not isinstance(image['data'],str) or len(image['data']) > (MAX_IMAGE_BYTES+2)//3*4:
                    raise ValueError('Image is too large.')
                raw = base64.b64decode(image['data'],validate=True)
                row = expected[image['name']]
                if image['name'].endswith('.source') and hashlib.sha256(raw).hexdigest() != row['sha256']:
                    raise ValueError('Image checksum mismatch.')
                with Image.open(io.BytesIO(raw)) as photo:
                    if photo.format not in ('JPEG','PNG','WEBP') or photo.width*photo.height > MAX_PIXELS or getattr(photo,'n_frames',1) != 1:
                        raise ValueError('Unsupported image.')
                    photo.verify()
                (store.images/image['name']).write_bytes(raw)
            for row in archive['tables']['blocks']:
                refs = db.execute('SELECT system,external_id FROM external_links WHERE block_id=?',(row['id'],)).fetchall()
                db.execute('INSERT INTO block_search VALUES(?,?,?,?,?)',(row['id'],row['block_code'],row['description'],row['location'],
                           ' '.join(ref['system']+' '+ref['external_id'] for ref in refs)))
            for row in archive['tables']['import_images']:
                db.execute('INSERT INTO import_search VALUES(?,?,?,?)',(row['id'],row['filename'],row['label_text'],row['barcodes']))
            # Exercise derived metadata/QC now, while a failed import can still be discarded.
            inventory.snapshot(store,db)
        (directory/'restored-experiments.json').write_text(json.dumps(experiments))
        (directory/'.import-pending').unlink()
        return info
    except BaseException as error:
        manager.stores.pop(info['id'], None)
        shutil.rmtree(directory)
        if isinstance(error,ArchiveError): raise
        if isinstance(error,(ValueError,TypeError,KeyError,OSError,sqlite3.Error)):
            raise ArchiveError(422,'Project JSON is invalid or incomplete. No existing project was changed.') from error
        raise
