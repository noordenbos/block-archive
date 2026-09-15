"""Persistent block records, image history, and transactional archive movements."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import re
import sqlite3
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from import_inbox import ImportInbox

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def uid():
    return str(uuid.uuid4())


def code_key(code):
    return code.strip().upper()


class ArchiveError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class Archive(ImportInbox):
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.images = self.directory / 'images'
        self.images.mkdir(exist_ok=True, mode=0o700)
        self.database = self.directory / 'archive.sqlite3'
        with self.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1, 2):
                raise RuntimeError('Unsupported archive database version; no migration was attempted.')
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS blocks (
                    id TEXT PRIMARY KEY, block_code TEXT NOT NULL, code_key TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '', archive_year INTEGER NOT NULL,
                    case_number TEXT NOT NULL, case_order INTEGER NOT NULL,
                    subspecimen TEXT NOT NULL, cassette_number INTEGER NOT NULL, location TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('awaiting_archive','archived','checked_out')),
                    cycle INTEGER NOT NULL DEFAULT 0, current_photo_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    cut_completed_at TEXT, version INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(archive_year,case_order,subspecimen,cassette_number)
                );
                CREATE INDEX IF NOT EXISTS blocks_case_number ON blocks(case_order, archive_year);
                CREATE INDEX IF NOT EXISTS blocks_sequence ON blocks(archive_year, case_order, subspecimen, cassette_number);
                CREATE INDEX IF NOT EXISTS blocks_status ON blocks(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY, block_id TEXT NOT NULL REFERENCES blocks(id),
                    cycle INTEGER NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    actor TEXT NOT NULL, note TEXT NOT NULL, sha256 TEXT NOT NULL,
                    content_type TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    UNIQUE(block_id, sha256)
                );
                CREATE INDEX IF NOT EXISTS photos_block ON photos(block_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS external_links (
                    id TEXT PRIMARY KEY, block_id TEXT NOT NULL REFERENCES blocks(id),
                    system TEXT NOT NULL, external_id TEXT NOT NULL, url TEXT,
                    UNIQUE(block_id, system, external_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    block_id TEXT NOT NULL REFERENCES blocks(id), type TEXT NOT NULL,
                    actor TEXT NOT NULL, occurred_at TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_block ON events(block_id, sequence DESC);
                CREATE VIRTUAL TABLE IF NOT EXISTS block_search USING fts5(
                    block_id UNINDEXED, block_code, description, location, external_ids,
                    tokenize='unicode61', prefix='2 3 4'
                );
            ''')
            self.init_inbox(db)
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def row(self, db, block_id, expected_version=None):
        row = db.execute('SELECT * FROM blocks WHERE id=?', (block_id,)).fetchone()
        if row is None:
            raise ArchiveError(404, 'Block not found.')
        if expected_version is not None and row['version'] != expected_version:
            raise ArchiveError(409, 'This block changed. Refresh its record before continuing.')
        return row

    def event(self, db, block_id, kind, actor, data):
        db.execute('INSERT INTO events(block_id,type,actor,occurred_at,data) VALUES(?,?,?,?,?)',
                   (block_id, kind, actor, now(), json.dumps(data)))

    def touch(self, db, block_id):
        db.execute('UPDATE blocks SET version=version+1,updated_at=? WHERE id=?', (now(), block_id))
        row = self.row(db, block_id)
        refs = db.execute('SELECT system,external_id FROM external_links WHERE block_id=?', (block_id,)).fetchall()
        db.execute('DELETE FROM block_search WHERE block_id=?', (block_id,))
        db.execute('INSERT INTO block_search VALUES(?,?,?,?,?)',
                   (block_id, row['block_code'], row['description'], row['location'],
                    ' '.join(f'{r["system"]} {r["external_id"]}' for r in refs)))

    def photo_record(self, row):
        photo = dict(row)
        photo['url'] = f'/api/v1/photos/{photo["id"]}/image'
        photo['thumbnail_url'] = f'/api/v1/photos/{photo["id"]}/thumbnail'
        return photo

    def detail(self, block_id):
        with self.connect() as db:
            result = dict(self.row(db, block_id))
            result.pop('code_key')
            result['photos'] = [self.photo_record(r) for r in db.execute(
                'SELECT * FROM photos WHERE block_id=? ORDER BY created_at DESC,id', (block_id,))]
            result['external_links'] = [dict(r) for r in db.execute(
                'SELECT * FROM external_links WHERE block_id=? ORDER BY system,external_id', (block_id,))]
            result['events'] = [dict(r) | {'data': json.loads(r['data'])} for r in db.execute(
                'SELECT * FROM events WHERE block_id=? ORDER BY sequence DESC', (block_id,))]
            return result

    def by_code(self, code):
        with self.connect() as db:
            row = db.execute('SELECT id FROM blocks WHERE code_key=?', (code_key(code),)).fetchone()
            if row is None:
                raise ArchiveError(404, 'Block not found.')
        return self.detail(row['id'])

    def list(self, query='', status=None, limit=40, offset=0, year=None, sort='archive', case_number=None):
        clauses, args = [], []
        if status:
            clauses.append('b.status=?'); args.append(status)
        if year is not None:
            clauses.append('b.archive_year=?'); args.append(year)
        if case_number is not None:
            clauses.append('b.case_order=?'); args.append(int(case_number))
        if query.strip():
            terms, term_args = ['b.code_key=?'], [code_key(query)]
            tokens = re.findall(r'\w+', query, re.UNICODE)
            if tokens:
                match = ' AND '.join('"' + token + '"*' for token in tokens)
                terms.append('b.id IN (SELECT block_id FROM block_search WHERE block_search MATCH ?)')
                term_args.append(match)
            if re.fullmatch(r'[0-9]{1,12}', query.strip()):
                terms.append('b.case_order=?'); term_args.append(int(query.strip()))
            case_query = re.fullmatch(r'([0-9]{4})[-/ ]+([0-9]{1,12})(?:[-/ ]+([A-Za-z]{1,4})([0-9]{1,4}))?', query.strip())
            if case_query:
                clause = '(b.archive_year=? AND b.case_order=?'
                term_args.extend((int(case_query[1]), int(case_query[2])))
                if case_query[3]:
                    clause += ' AND b.subspecimen=? AND b.cassette_number=?'
                    term_args.extend((case_query[3].upper(), int(case_query[4])))
                terms.append(clause + ')')
            clauses.append('(' + ' OR '.join(terms) + ')'); args.extend(term_args)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        order = 'b.archive_year DESC,b.case_order,b.subspecimen,b.cassette_number,b.code_key' if sort == 'archive' else 'b.updated_at DESC,b.id'
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM blocks b' + where, args).fetchone()[0]
            rows = db.execute('''SELECT b.*,
                (SELECT COUNT(*) FROM photos p WHERE p.block_id=b.id) AS photo_count,
                COALESCE(b.current_photo_id,(SELECT id FROM photos p WHERE p.block_id=b.id ORDER BY created_at DESC LIMIT 1)) AS preview_id
                FROM blocks b''' + where + ' ORDER BY (b.code_key=?) DESC,' + order + ' LIMIT ? OFFSET ?',
                [*args, code_key(query), limit, offset]).fetchall()
            items = []
            for r in rows:
                item = dict(r); item.pop('code_key')
                item['thumbnail_url'] = f'/api/v1/photos/{item["preview_id"]}/thumbnail' if item['preview_id'] else None
                items.append(item)
            counts = {s: 0 for s in ('archived', 'checked_out', 'awaiting_archive')}
            counts.update({r[0]: r[1] for r in db.execute('SELECT status,COUNT(*) FROM blocks GROUP BY status')})
        return {'items': items, 'total': total, 'offset': offset, 'limit': limit,
                'next_offset': offset + limit if offset + limit < total else None, 'counts': counts}

    def create(self, block_code, description, actor, archive_year, case_number, subspecimen, cassette_number):
        block_id, stamp = uid(), now()
        try:
            with self.connect(write=True) as db:
                db.execute('''INSERT INTO blocks(id,block_code,code_key,description,archive_year,case_number,case_order,subspecimen,cassette_number,location,status,created_at,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                           (block_id, block_code.strip(), code_key(block_code), description, archive_year, case_number, int(case_number), subspecimen, cassette_number, f'{archive_year}-{case_number} / {subspecimen}{cassette_number}', 'awaiting_archive', stamp, stamp))
                self.event(db, block_id, 'registered', actor, {})
                self.touch(db, block_id)
        except sqlite3.IntegrityError as exc:
            raise ArchiveError(409, 'This block code or case/subspecimen/cassette is already registered.') from exc
        return self.detail(block_id)

    def update(self, block_id, description, actor, expected_version):
        with self.connect(write=True) as db:
            self.row(db, block_id, expected_version)
            db.execute('UPDATE blocks SET description=? WHERE id=?', (description, block_id))
            self.event(db, block_id, 'details_updated', actor, {'description': description})
            self.touch(db, block_id)
        return self.detail(block_id)

    def transition(self, block_id, action, actor, expected_version, note='', location='', photo_id=None):
        with self.connect(write=True) as db:
            row = self.row(db, block_id, expected_version)
            data = {'note': note, 'cycle': row['cycle']}
            if action == 'checkout':
                if row['status'] != 'archived':
                    raise ArchiveError(409, 'Only an archived block can be checked out.')
                data.update({'previous_location': row['location'], 'cycle': row['cycle'] + 1})
                db.execute("UPDATE blocks SET status='checked_out',cycle=cycle+1,cut_completed_at=NULL WHERE id=?", (block_id,))
            elif action == 'complete-cut':
                if row['status'] != 'checked_out':
                    raise ArchiveError(409, 'Check out the block before completing cutting.')
                db.execute("UPDATE blocks SET status='awaiting_archive',cut_completed_at=? WHERE id=?", (now(), block_id))
            elif action == 'rearchive':
                if row['status'] != 'awaiting_archive':
                    raise ArchiveError(409, 'This block is not awaiting archive.')
                photo = db.execute('SELECT * FROM photos WHERE id=? AND block_id=?', (photo_id, block_id)).fetchone()
                required_kind = 'post_cut' if row['cycle'] else 'baseline'
                if (photo is None or photo['cycle'] != row['cycle'] or photo['kind'] != required_kind
                        or (row['cut_completed_at'] and photo['created_at'] < row['cut_completed_at'])):
                    raise ArchiveError(409, 'Upload a new archive photo for this cutting cycle before rearchiving.')
                location = f'{row["archive_year"]}-{row["case_number"]} / {row["subspecimen"]}{row["cassette_number"]}'
                data.update({'location': location, 'photo_id': photo_id, 'previous_location': row['location']})
                db.execute("UPDATE blocks SET status='archived',location=?,current_photo_id=? WHERE id=?", (location, photo_id, block_id))
            else:
                raise ArchiveError(404, 'Unknown movement.')
            self.event(db, block_id, action.replace('-', '_'), actor, data)
            self.touch(db, block_id)
        return self.detail(block_id)

    def add_photo(self, block_id, raw, kind, actor, note, expected_version):
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ArchiveError(413, 'Choose a photo no larger than 20 MB.')
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('format')
                width, height = source.size
                if width * height > MAX_PIXELS or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('dimensions')
                content_type = Image.MIME[source.format]
                source.load()
                thumbnail = ImageOps.exif_transpose(source).convert('RGB')
                thumbnail.thumbnail((720, 720))
                buffer = io.BytesIO(); thumbnail.save(buffer, 'JPEG', quality=85)
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError) as exc:
            raise ArchiveError(422, 'Use a single-frame JPEG, PNG or WebP up to 40 megapixels.') from exc
        photo_id, digest = uid(), hashlib.sha256(raw).hexdigest()
        paths = [self.images / f'{photo_id}.source', self.images / f'{photo_id}.jpg']
        try:
            with self.connect(write=True) as db:
                row = self.row(db, block_id, expected_version)
                if kind == 'post_cut' and (row['status'] != 'awaiting_archive' or row['cycle'] == 0):
                    raise ArchiveError(409, 'Post-cut photos are added after cutting is marked complete.')
                if kind == 'baseline' and (row['cycle'] != 0 or row['status'] != 'awaiting_archive'):
                    raise ArchiveError(409, 'A baseline photo is only for initial archiving.')
                if db.execute('SELECT 1 FROM photos WHERE block_id=? AND sha256=?', (block_id, digest)).fetchone():
                    raise ArchiveError(409, 'This photo is already recorded for this block. Take a new photo after cutting.')
                paths[0].write_bytes(raw); paths[1].write_bytes(buffer.getvalue())
                db.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (photo_id, block_id, row['cycle'], kind, now(), actor, note, digest, content_type, width, height))
                self.event(db, block_id, 'photo_added', actor, {'photo_id': photo_id, 'kind': kind, 'cycle': row['cycle']})
                self.touch(db, block_id)
        except BaseException:
            for path in paths:
                path.unlink(missing_ok=True)
            raise
        return self.detail(block_id)

    def photo_path(self, photo_id, thumbnail=False):
        with self.connect() as db:
            row = db.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
            if row is None:
                raise ArchiveError(404, 'Photo not found.')
        path = self.images / f'{row["id"]}.{"jpg" if thumbnail else "source"}'
        if not path.is_file():
            raise ArchiveError(404, 'Stored photo is unavailable. Check the archive backup.')
        return path, 'image/jpeg' if thumbnail else row['content_type']

    def link(self, block_id, system, external_id, url, actor, expected_version):
        with self.connect(write=True) as db:
            self.row(db, block_id, expected_version)
            existing = db.execute('SELECT id FROM external_links WHERE block_id=? AND system=? AND external_id=?',
                                  (block_id, system, external_id)).fetchone()
            link_id = existing['id'] if existing else uid()
            db.execute('''INSERT INTO external_links VALUES(?,?,?,?,?)
                ON CONFLICT(block_id,system,external_id) DO UPDATE SET url=excluded.url''',
                       (link_id, block_id, system, external_id, url))
            self.event(db, block_id, 'external_link_saved', actor, {'system': system, 'external_id': external_id, 'url': url})
            self.touch(db, block_id)
        return self.detail(block_id)

    def events(self, after, limit):
        with self.connect() as db:
            rows = db.execute('''SELECT e.*,b.block_code FROM events e JOIN blocks b ON b.id=e.block_id
                                 WHERE sequence>? ORDER BY sequence LIMIT ?''', (after, limit + 1)).fetchall()
            items = [dict(r) | {'data': json.loads(r['data'])} for r in rows[:limit]]
            return {'items': items, 'next_cursor': items[-1]['sequence'] if items else after, 'has_more': len(rows) > limit}

    def backup(self, destination):
        """Consistent database and photo snapshot while writers are locked out."""
        import zipfile
        with self.connect(write=True) as lock, self.connect() as source:
            # The write reservation prevents new image records while the snapshot is copied.
            temporary = self.directory / f'backup-{uid()}.sqlite3'
            try:
                with sqlite3.connect(temporary) as target:
                    source.backup(target)
                with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.write(temporary, 'archive.sqlite3')
                    for row in lock.execute('SELECT id FROM photos UNION SELECT id FROM import_images'):
                        for suffix in ('.source', '.jpg'):
                            path = self.images / (row['id'] + suffix)
                            archive.write(path, 'images/' + path.name)
            finally:
                temporary.unlink(missing_ok=True)
