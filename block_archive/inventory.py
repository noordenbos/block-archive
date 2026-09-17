"""Inventory views and immutable experiment selections over existing archive records."""
import hashlib
import json
from block_archive.archive import ArchiveError, now, uid
from block_archive import metadata
from block_archive import capture_review
def initialize(store):
    with store.connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS inventory_labels (
                item_key TEXT PRIMARY KEY, labels TEXT NOT NULL, actor TEXT NOT NULL,
                updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS planning_selections (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
        ''')
        metadata.initialize(db)
        capture_review.initialize(db)


def snapshot(store, db):
    items = {}
    analyses, assignments, reviews = capture_review.state(db)
    for row in db.execute('SELECT * FROM blocks ORDER BY archive_year DESC,case_order,subspecimen,cassette_number'):
        block = dict(row)
        key = 'block:' + block['id']
        refs = [dict(r) for r in db.execute('SELECT system,external_id FROM external_links WHERE block_id=?', (block['id'],))]
        photos = [store.photo_record(r) for r in db.execute('SELECT * FROM photos WHERE block_id=? ORDER BY created_at DESC,id', (block['id'],))]
        items[key] = {'key': key, 'name': block['block_code'], 'block_id': block['id'],
                      'kind': 'block', 'description': block['description'], 'location': block['location'],
                      'status': block['status'], 'photos': photos, 'references': refs,
                      'evidence': '', 'source_version': block['version']}
    for row in db.execute('SELECT * FROM import_images WHERE block_id IS NULL ORDER BY filename,id'):
        photo = store.inbox_record(row)
        codes = sorted(set(photo['barcodes']))
        declared = assignments.get(photo['id'], {}).get('group_name')
        if declared:
            codes = [declared]
        # These are explicitly provisional photo groups, never inferred block identities.
        key = ('candidate:' + hashlib.sha256(codes[0].encode()).hexdigest()
               if len(codes) == 1 else 'image:' + photo['id'])
        if key not in items:
            items[key] = {'key': key, 'name': codes[0] if len(codes) == 1 else photo['filename'],
                          'block_id': None, 'kind': 'candidate', 'description': 'Unverified photo group',
                          'location': '', 'status': 'needs_review', 'photos': [], 'references': [],
                          'evidence': '', 'source_version': 0}
        items[key]['photos'].append(photo)
        items[key]['evidence'] += '\n' + photo['filename'] + '\n' + photo['label_text']
    labels = {r['item_key']: dict(r) for r in db.execute('SELECT * FROM inventory_labels')}
    all_metadata = metadata.records(db)
    for item in items.values():
        label_record = labels.get(item['key'], {})
        item['labels'] = json.loads(label_record.get('labels', '[]'))
        item['metadata_version'] = label_record.get('version', 0)
        values = all_metadata.get(metadata.id_key(item['name']), {})
        item['metadata'] = values.get('fields', {})
        item['record_metadata_version'] = values.get('version', 0)
        for photo in item['photos']:
            if photo['id'] in analyses: photo['analysis'] = analyses[photo['id']]
            if photo['id'] in assignments: photo['assignment'] = assignments[photo['id']]
        item['qc'] = capture_review.assess(item, reviews)
        evidence = [item['source_version'], item['metadata_version'], item['record_metadata_version'], item['qc'],
                    [(p['id'], p.get('version', 0)) for p in item['photos']]]
        item['revision'] = hashlib.sha256(json.dumps(evidence).encode()).hexdigest()
    return items


def list_items(store):
    with store.connect() as db:
        db.execute('BEGIN')
        return list(snapshot(store, db).values())


def label_items(store, entries, labels, action, actor):
    with store.connect(write=True) as db:
        current = snapshot(store, db)
        for entry in entries:
            item = current.get(entry['key'])
            if not item or item['revision'] != entry['revision']:
                raise ArchiveError(409, 'The inventory changed. Refresh and review the selection.')
        for entry in entries:
            item = current[entry['key']]
            updated = (sorted(set(item['labels']) | set(labels), key=str.casefold) if action == 'add'
                       else [value for value in item['labels'] if value not in labels])
            if len(updated) > 50:
                raise ArchiveError(422, 'Use no more than 50 labels per inventory item.')
            db.execute('''INSERT INTO inventory_labels VALUES(?,?,?,?,1)
                ON CONFLICT(item_key) DO UPDATE SET labels=excluded.labels,actor=excluded.actor,
                    updated_at=excluded.updated_at,version=inventory_labels.version+1''',
                       (entry['key'], json.dumps(updated), actor, now()))


def create_selection(store, name, actor, entries):
    with store.connect(write=True) as db:
        current = snapshot(store, db)
        selected, seen, names = [], set(), set()
        for entry in entries:
            item = current.get(entry['key'])
            if not item or item['revision'] != entry['revision']:
                raise ArchiveError(409, 'An inventory item changed. Refresh and review before planning.')
            if item['key'] in seen:
                raise ArchiveError(422, 'Select each inventory item once.')
            seen.add(item['key'])
            name_key = entry['name'].casefold()
            if name_key in names:
                raise ArchiveError(422, 'Use distinct full block identifiers in this experiment.')
            names.add(name_key)
            photos = {p['id']: p for p in item['photos']}
            tissue, identifier = entry['tissue_id'], entry['identifier_id']
            if (tissue and tissue not in photos) or (identifier and identifier not in photos) or (tissue and tissue == identifier) or not (tissue or identifier):
                raise ArchiveError(422, 'Choose the declared photo roles from this item.')
            automatic = (item['qc']['status'] == 'ready' and tissue == item['qc']['tissue_id']
                         and identifier == item['qc']['identifier_id'] and entry['name'] == item['name'])
            if not entry['confirmed'] and not automatic:
                raise ArchiveError(422, 'Confirm the full block identity and chosen photo roles.')
            if not tissue and not (automatic and item['qc'].get('missing_side')=='tissue'):
                raise ArchiveError(422, 'Accept the missing tissue-side exception in Import & QC first.')
            for photo_id in (tissue, identifier):
                if photo_id and not (store.images/(photo_id+'.source')).is_file():
                    raise ArchiveError(409, 'A source photo is missing. Restore it before planning.')
            selected.append({**item, 'source_name': item['name'], 'name': entry['name'], 'photos': ([photos[tissue]] if tissue else []) + ([photos[identifier]] if identifier else []),
                             'tissue_id': tissue, 'identifier_id': identifier, 'missing_side':item['qc'].get('missing_side',''),
                             'identity_reviewed': entry['confirmed'] or item['qc']['method'] == 'reviewed'})
        selection = {'id': uid(), 'name': name, 'actor': actor, 'created_at': now(), 'items': selected}
        db.execute('INSERT INTO planning_selections VALUES(?,?,?)', (selection['id'], json.dumps(selection), selection['created_at']))
        return selection


def get_selection(store, selection_id):
    with store.connect() as db:
        row = db.execute('SELECT payload FROM planning_selections WHERE id=?', (selection_id,)).fetchone()
        if not row:
            raise ArchiveError(404, 'Experiment selection not found.')
        return json.loads(row['payload'])
