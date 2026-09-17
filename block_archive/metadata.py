"""Arbitrary metadata columns, matched by exact trimmed, case-insensitive block ID."""
import csv
import io
import json
from block_archive.archive import ArchiveError, now


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS inventory_metadata (
        id_key TEXT PRIMARY KEY, matching_id TEXT NOT NULL, fields TEXT NOT NULL,
        version INTEGER NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL)''')


def id_key(value):
    return value.strip().casefold()


def clean_fields(fields):
    if len(fields) > 80:
        raise ArchiveError(422, 'Use at most 80 metadata columns.')
    result = {}
    seen = set()
    for name, value in fields.items():
        name = name.strip()
        if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ArchiveError(422, 'Column names must be printable and 1–80 characters.')
        if name.casefold() in seen:
            raise ArchiveError(422, 'Metadata column names must be unique, ignoring capitalization.')
        if not isinstance(value, str) or len(value) > 2000:
            raise ArchiveError(422, 'Metadata values must be text of at most 2000 characters.')
        seen.add(name.casefold()); result[name] = value.strip()
    return result


def records(db):
    return {row['id_key']: {**dict(row), 'fields': json.loads(row['fields'])}
            for row in db.execute('SELECT * FROM inventory_metadata ORDER BY matching_id COLLATE NOCASE')}


def read_table(text):
    if len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ArchiveError(413, 'Use CSV or pasted tables up to 2 MB.')
    text = text.lstrip('\ufeff')
    try:
        dialect = csv.Sniffer().sniff(text[:10000], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel_tab if '\t' in text.split('\n', 1)[0] else csv.excel
    try:
        rows = list(csv.reader(io.StringIO(text), dialect, strict=True))
    except csv.Error:
        raise ArchiveError(422, 'Could not parse the table. Check quoting and delimiters.')
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows or len(rows) < 2:
        raise ArchiveError(422, 'Include a header row and at least one data row.')
    if len(rows) > 10001 or len(rows[0]) > 81:
        raise ArchiveError(422, 'Use at most 10,000 records and 80 metadata columns plus the ID column.')
    headers = [v.strip() for v in rows[0]]
    if any(not v or len(v) > 80 for v in headers) or len({v.casefold() for v in headers}) != len(headers):
        raise ArchiveError(422, 'Every column needs a unique, nonempty header of at most 80 characters.')
    return headers, rows[1:]


def columns(text):
    headers, _ = read_table(text)
    selected = next((h for h in headers if h.casefold() in ('id','block_id','block id','matching_id','matching id','block_code')), headers[0])
    return {'headers':headers, 'id_column':selected}


def parse_table(text, column=None):
    headers, rows = read_table(text)
    selected = column or next((h for h in headers if h.casefold() in ('id','block_id','block id','matching_id','matching id','block_code')), headers[0])
    if selected not in headers:
        raise ArchiveError(422, 'Choose a matching ID column from this table.')
    position = headers.index(selected)
    parsed, seen = [], set()
    for number, values in enumerate(rows, 2):
        if len(values) != len(headers):
            raise ArchiveError(422, f'Row {number} has a different number of cells than the header.')
        ident = values[position].strip()
        if not ident or len(ident) > 120 or any(ord(c) < 32 for c in ident):
            raise ArchiveError(422, f'Row {number} needs a printable matching ID of 1–120 characters.')
        key = id_key(ident)
        if key in seen:
            raise ArchiveError(422, f'Row {number} repeats an ID. Resolve duplicates before importing.')
        seen.add(key)
        fields = clean_fields({name:value for i,(name,value) in enumerate(zip(headers,values)) if i != position})
        parsed.append({'matching_id':ident, 'fields':fields})
    return headers, selected, parsed


def preview(store, text, column=None):
    from block_archive.inventory import snapshot
    headers, selected, parsed = parse_table(text, column)
    with store.connect() as db:
        db.execute('BEGIN')
        current = records(db)
        known = {id_key(item['name']) for item in snapshot(store, db).values()}
    conflicts = 0
    for row in parsed:
        old = current.get(id_key(row['matching_id']), {})
        row['expected_version'] = old.get('version', 0)
        row['existing'] = old.get('fields', {})
        row['matched'] = id_key(row['matching_id']) in known
        old_fields = {k.casefold():v for k,v in row['existing'].items()}
        conflicts += sum(bool(value and old_fields.get(key.casefold()) and old_fields[key.casefold()] != value) for key,value in row['fields'].items())
    return {'headers':headers, 'id_column':selected, 'rows':parsed, 'conflicts':conflicts,
            'matched':sum(row['matched'] for row in parsed), 'unmatched':sum(not row['matched'] for row in parsed)}


def save(store, entries, actor, mode='fill'):
    # Validation and version checks cover the entire batch before committing anything.
    with store.connect(write=True) as db:
        current = records(db); seen = set()
        for entry in entries:
            key = id_key(entry['matching_id'])
            if key in seen:
                raise ArchiveError(422, 'Each matching ID may occur only once in a save.')
            seen.add(key)
            old = current.get(key, {})
            if old.get('version', 0) != entry['expected_version']:
                raise ArchiveError(409, 'Metadata changed since you opened it. Refresh or preview again.')
            incoming = clean_fields(entry['fields'])
            updated = {} if mode == 'replace' else dict(old.get('fields', {}))
            canonical = {name.casefold():name for name in updated}
            for name, value in incoming.items():
                target = canonical.get(name.casefold(), name)
                if mode == 'replace' or (value and (mode == 'overwrite' or not updated.get(target))):
                    updated[target] = value
            clean_fields(updated)
            db.execute('''INSERT INTO inventory_metadata VALUES(?,?,?,?,?,?)
                ON CONFLICT(id_key) DO UPDATE SET matching_id=excluded.matching_id,fields=excluded.fields,
                    version=excluded.version,actor=excluded.actor,updated_at=excluded.updated_at''',
                (key, entry['matching_id'].strip(), json.dumps(updated), old.get('version',0)+1, actor, now()))
