"""Stored photo analysis, declared block sides and exception-only import review."""
import hashlib
import json
from block_archive.side_detection import choose_sides
from block_archive.archive import ArchiveError, now


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS capture_analysis (
            photo_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS capture_assignments (
            photo_id TEXT PRIMARY KEY, group_name TEXT NOT NULL, role TEXT NOT NULL,
            actor TEXT NOT NULL, version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS capture_reviews (
            item_key TEXT PRIMARY KEY, signature TEXT NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL
        );
    ''')
    if 'missing_side' not in {row[1] for row in db.execute('PRAGMA table_info(capture_reviews)')}:
        db.execute("ALTER TABLE capture_reviews ADD COLUMN missing_side TEXT NOT NULL DEFAULT ''")


def record_analysis(store, photo_id, analysis):
    kept = {key:analysis.get(key) for key in ('hash','qrValues','markerIds','rotationDegrees','labelFeatures','gridFeatures','printingEvidence','role','registration','identityConflict')}
    kept['calibrated'] = bool(analysis.get('calibration'))
    kept['error'] = analysis.get('error', '')
    with store.connect(write=True) as db:
        db.execute('INSERT OR REPLACE INTO capture_analysis VALUES(?,?,?)', (photo_id,json.dumps(kept),now()))


def state(db):
    return ({r['photo_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM capture_analysis')},
            {r['photo_id']:dict(r) for r in db.execute('SELECT * FROM capture_assignments')},
            {r['item_key']:dict(r) for r in db.execute('SELECT * FROM capture_reviews')})


def signature(item):
    values = [(p['id'],p.get('analysis'),p.get('assignment')) for p in item['photos']]
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()


def assess(item, reviews):
    photos = item['photos']; problems = []
    declared_tissue = [p for p in photos if p.get('assignment',{}).get('role') == 'tissue']
    declared_identifier = [p for p in photos if p.get('assignment',{}).get('role') == 'identifier']
    tissue = declared_tissue[0] if len(declared_tissue) == 1 else None
    identifier = declared_identifier[0] if len(declared_identifier) == 1 else None
    if len(photos) != 2 and not (item['kind'] == 'block' and tissue and identifier):
        problems.append(f'Expected two views; found {len(photos)}. Check grouping.')
    for photo in photos:
        analysis = photo.get('analysis')
        if not analysis:
            problems.append('Photo analysis is pending.'); continue
        if analysis.get('error'):
            problems.append('A photograph could not be analyzed.'); continue
        if analysis.get('identityConflict'):
            problems.append('A capture has an identity conflict.')
        if len(analysis.get('qrValues') or []) != 1 and not photo.get('assignment'):
            problems.append('No single readable QR ID; declare its block group.')
        elif len(analysis.get('qrValues') or []) == 1 and not photo.get('assignment') and analysis['qrValues'][0].strip().casefold() != item['name'].strip().casefold():
            problems.append('A QR reading differs from the group ID. Check grouping and labels.')
        if not analysis.get('calibrated') or analysis.get('rotationDegrees') is None:
            problems.append('Mat orientation or calibration is missing; manual calibration may be needed.')
    decision = None
    if len(photos) == 2 and not (tissue and identifier):
        decision = choose_sides([p.get('analysis') or {} for p in photos])
        if decision and not declared_tissue and not declared_identifier:
            tissue, identifier = photos[decision['tissue']], photos[decision['identifier']]
        if not (tissue and identifier):
            problems.append('Tissue and identifier sides are ambiguous; declare both sides.')
    elif not (tissue and identifier):
        problems.append('Choose one tissue side and one identifier side.')
    current_signature = signature(item)
    reviewed = reviews.get(item['key'],{}).get('signature') == current_signature
    missing_side = reviews.get(item['key'],{}).get('missing_side','') if reviewed else ''
    legacy_single = reviewed and len(photos)==1 and tissue and not identifier and not missing_side
    if legacy_single: missing_side='identifier'
    allowed_missing = reviewed and len(photos)==1 and ((missing_side=='tissue' and identifier and not tissue) or (missing_side=='identifier' and tissue and not identifier))
    ready = bool(allowed_missing or (tissue and (identifier or reviewed) and (not problems or reviewed)))
    method = 'reviewed' if reviewed else 'declared' if declared_tissue or declared_identifier else 'automatic'
    evidence = ('Sides were declared by an operator.' if declared_tissue or declared_identifier else
                ('Aligned upper-rim lettering distinguishes the identifier side; the paired opposite view is the tissue side.'
                 if decision and decision['method'] == 'rim-text-v2' else
                 'Upper-rim printing distinguishes the identifier side; the paired opposite view is the tissue side.') if tissue and identifier else
                'Upper-rim printing does not yet distinguish two usable sides. Check grouping and the individual photo results.')
    return {'status':'ready' if ready else 'needs_review', 'method':method, 'side_evidence':evidence, 'missing_side':missing_side, 'side_detector':decision['method'] if decision else None,
            'problems':list(dict.fromkeys(problems)), 'tissue_id':tissue['id'] if tissue else None,
            'identifier_id':identifier['id'] if identifier else None, 'signature':current_signature}


def save_review(store, key, revision, photos, actor, accept, missing_side=""):
    if missing_side not in ("", "tissue", "identifier"):
        raise ArchiveError(422, "Choose a valid missing-side exception.")
    if missing_side and not accept:
        raise ArchiveError(422, "Confirm QC before continuing with a missing side.")
    from block_archive import inventory
    with store.connect(write=True) as db:
        original = inventory.snapshot(store,db).get(key)
        if not original or original['revision'] != revision:
            raise ArchiveError(409, 'This group changed. Refresh its review before saving.')
        if {p['photo_id'] for p in photos} != {p['id'] for p in original['photos']} or len(photos) != len(original['photos']):
            raise ArchiveError(422, 'Include every photo in this group exactly once.')
        for photo in photos:
            if original['kind'] == 'block' and photo['group_name'] != original['name']:
                raise ArchiveError(422, 'Registered block identities must be corrected through the archive workflow.')
            db.execute('''INSERT INTO capture_assignments VALUES(?,?,?,?,1)
                ON CONFLICT(photo_id) DO UPDATE SET group_name=excluded.group_name,role=excluded.role,
                    actor=excluded.actor,version=capture_assignments.version+1''',
                       (photo['photo_id'],photo['group_name'],photo['role'],actor))
        updated = inventory.snapshot(store,db)
        changed_ids = {p['photo_id'] for p in photos}
        touched = [item for item in updated.values() if changed_ids.intersection(p['id'] for p in item['photos'])]
        for item in touched:
            if original['labels']:
                labels = sorted(set(item['labels']) | set(original['labels']))
                if len(labels) > 50:
                    raise ArchiveError(422, 'Merged group labels exceed 50. Remove some labels before grouping.')
                db.execute('''INSERT INTO inventory_labels VALUES(?,?,?,?,1)
                    ON CONFLICT(item_key) DO UPDATE SET labels=excluded.labels,actor=excluded.actor,
                        updated_at=excluded.updated_at,version=inventory_labels.version+1''',
                           (item['key'],json.dumps(labels),actor,now()))
            roles = [p.get('assignment',{}).get('role') for p in item['photos']]
            complete_roles = roles.count('tissue') == 1 and roles.count('identifier') == 1
            allowed_missing = len(roles)==1 and ((missing_side=='tissue' and roles[0]=='identifier') or (missing_side=='identifier' and roles[0]=='tissue'))
            if missing_side and not allowed_missing:
                raise ArchiveError(422, 'The missing-side exception must match a single photograph declared as the opposite side.')
            if accept and not (complete_roles or allowed_missing):
                raise ArchiveError(422, 'Declare both sides, or explicitly continue without the missing side.')
            if accept and (complete_roles or allowed_missing) and (len(roles) <= 2 or item['kind'] == 'block'):
                if any((p.get('analysis') or {}).get('identityConflict') for p in item['photos']):
                    raise ArchiveError(422, 'Correct the capture identity conflict before accepting QC.')
                db.execute('INSERT OR REPLACE INTO capture_reviews VALUES(?,?,?,?,?)', (item['key'],signature(item),actor,now(),missing_side))
        return [item['key'] for item in touched]
