"""Local historical-photo intake. Label readings are searchable, unverified evidence."""
import hashlib
import io
import json
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError


class ImportInbox:
    def init_inbox(self, db):
        db.executescript('''
            CREATE TABLE IF NOT EXISTS import_images (
                id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
                imported_at TEXT NOT NULL, actor TEXT NOT NULL, label_text TEXT NOT NULL,
                barcodes TEXT NOT NULL, content_type TEXT NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, block_id TEXT REFERENCES blocks(id),
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS import_search USING fts5(
                image_id UNINDEXED, filename, label_text, barcodes,
                tokenize='unicode61', prefix='2 3 4'
            );
        ''')

    def import_image(self, path, actor='Folder import', label_text='', barcodes=None):
        from archive import ArchiveError, MAX_IMAGE_BYTES, MAX_PIXELS, now, uid
        path = Path(path)
        with path.open('rb') as source_file:
            raw = source_file.read(MAX_IMAGE_BYTES + 1)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ArchiveError(413, 'Image exceeds the 20 MB import limit.')
        digest = hashlib.sha256(raw).hexdigest()
        with self.connect() as db:
            existing = db.execute('SELECT id FROM import_images WHERE sha256=?', (digest,)).fetchone()
        if existing:
            return existing['id'], False
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > MAX_PIXELS or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Unsupported image')
                width, height, content_type = image.width, image.height, Image.MIME[image.format]
                image.load()
                thumbnail = ImageOps.exif_transpose(image).convert('RGB')
                thumbnail.thumbnail((720, 720))
                buffer = io.BytesIO()
                thumbnail.save(buffer, 'JPEG', quality=85)
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ArchiveError(422, 'Image could not be imported.') from exc
        image_id = uid()
        paths = [self.images / (image_id + '.source'), self.images / (image_id + '.jpg')]
        codes = json.dumps(barcodes or [], ensure_ascii=False)
        try:
            with self.connect(write=True) as db:
                existing = db.execute('SELECT id FROM import_images WHERE sha256=?', (digest,)).fetchone()
                if existing:
                    return existing['id'], False
                paths[0].write_bytes(raw)
                paths[1].write_bytes(buffer.getvalue())
                db.execute('''INSERT INTO import_images
                    (id,filename,sha256,imported_at,actor,label_text,barcodes,content_type,width,height)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',
                    (image_id, path.name, digest, now(), actor, label_text, codes, content_type, width, height))
                db.execute('INSERT INTO import_search VALUES(?,?,?,?)', (image_id, path.name, label_text, codes))
        except BaseException:
            for destination in paths:
                destination.unlink(missing_ok=True)
            raise
        return image_id, True

    def inbox_record(self, row):
        result = dict(row)
        result['barcodes'] = json.loads(result['barcodes'])
        result['url'] = f'/api/v1/imports/{result["id"]}/image'
        result['thumbnail_url'] = f'/api/v1/imports/{result["id"]}/thumbnail'
        return result

    def inbox_detail(self, image_id):
        from archive import ArchiveError
        with self.connect() as db:
            row = db.execute('SELECT * FROM import_images WHERE id=?', (image_id,)).fetchone()
            if not row:
                raise ArchiveError(404, 'Imported photo not found.')
            return self.inbox_record(row)

    def inbox_list(self, query='', status='pending', limit=30, offset=0):
        import re
        clauses, args = [], []
        if status != 'all':
            clauses.append('block_id IS ' + ('NULL' if status == 'pending' else 'NOT NULL'))
        tokens = re.findall(r'\w+', query)
        if tokens:
            clauses.append('id IN (SELECT image_id FROM import_search WHERE import_search MATCH ?)')
            args.append(' AND '.join('"' + token + '"*' for token in tokens))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM import_images' + where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM import_images' + where + ' ORDER BY filename,id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
            pending = db.execute('SELECT COUNT(*) FROM import_images WHERE block_id IS NULL').fetchone()[0]
        return {'items': [self.inbox_record(r) for r in rows], 'total': total, 'pending': pending,
                'offset': offset, 'limit': limit, 'next_offset': offset + limit if offset + limit < total else None}

    def inbox_path(self, image_id, thumbnail=False):
        from archive import ArchiveError
        record = self.inbox_detail(image_id)
        path = self.images / (record['id'] + ('.jpg' if thumbnail else '.source'))
        if not path.is_file():
            raise ArchiveError(404, 'Imported photo file is unavailable.')
        return path, 'image/jpeg' if thumbnail else record['content_type']

    def confirm_import(self, image_id, block_id, actor, expected_version, expected_block_version):
        from archive import ArchiveError, now
        with self.connect(write=True) as db:
            image = db.execute('SELECT * FROM import_images WHERE id=?', (image_id,)).fetchone()
            if not image:
                raise ArchiveError(404, 'Imported photo not found.')
            if image['block_id'] or image['version'] != expected_version:
                raise ArchiveError(409, 'This import changed or was already linked. Refresh before continuing.')
            block = self.row(db, block_id, expected_block_version)
            if db.execute('SELECT 1 FROM photos WHERE block_id=? AND sha256=?', (block_id, image['sha256'])).fetchone():
                raise ArchiveError(409, 'This image is already recorded for this block.')
            note = 'Historical folder import; capture time and archive position unverified. Source: ' + image['filename']
            db.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (image_id, block_id, block['cycle'], 'reference', now(), actor, note,
                        image['sha256'], image['content_type'], image['width'], image['height']))
            db.execute('UPDATE import_images SET block_id=?,version=version+1 WHERE id=?', (block_id, image_id))
            self.event(db, block_id, 'import_confirmed', actor, {'photo_id': image_id, 'note': note})
            self.touch(db, block_id)
        return self.detail(block_id)
