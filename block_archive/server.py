"""Block Archive: local browser workspace and authenticated versioned API."""
from pathlib import Path
from typing import Literal
import argparse
import json
import os
import secrets
import tempfile
import base64
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from block_archive.archive import Archive, ArchiveError, MAX_IMAGE_BYTES
from block_archive.label_pdf import pdf_bytes, parse_ids, qr_png
from block_archive import inventory
from block_archive import metadata
from block_archive import capture_review
from block_archive import projects
from block_archive import local_saves
from block_archive.previews import block_preview, experiment_image

ROOT = Path(__file__).resolve().parents[1]
PLANNER_ASSETS = frozenset((ROOT / 'tools/planner-assets.txt').read_text().splitlines())


class ProjectName(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"^[^\x00-\x1f]+$")


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Actor(Input):
    actor: str = Field(min_length=1, max_length=80, description='Recorded operator; not an authenticated personal identity.')


class NewBlock(Actor):
    block_code: str = Field(min_length=1, max_length=120, description='Full block identifier, including any block suffix. Unique ignoring case.')
    archive_year: int = Field(ge=1900, le=2199)
    case_number: str = Field(pattern=r'^[0-9]{1,12}$', description='Sequential case number; leading zeroes are retained.')
    subspecimen: str = Field(pattern=r'^[A-Z]{1,4}$', description='Container/subspecimen letter, e.g. B.')
    cassette_number: int = Field(ge=1, le=9999, description='Cassette number within the subspecimen, e.g. 4.')
    description: str = Field(default='', max_length=2000, description='Known cassette contents.')

    @field_validator('block_code', 'actor')
    @classmethod
    def printable(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('Use printable characters.')
        return value


class Versioned(Actor):
    expected_version: int = Field(ge=1, description='Version from the last block response. Stale updates return 409.')


class EditBlock(Versioned):
    description: str = Field(max_length=2000)


class Movement(Versioned):
    note: str = Field(default='', max_length=2000)


class Rearchive(Movement):
    photo_id: UUID


class ExternalLink(Versioned):
    system: str = Field(min_length=1, max_length=80)
    external_id: str = Field(min_length=1, max_length=200)
    url: HttpUrl | None = None


class ConfirmImport(Versioned):
    block_id: UUID
    expected_block_version: int = Field(ge=1)


class InventoryEntry(Input):
    key: str = Field(min_length=1, max_length=100)
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class InventoryLabels(Actor):
    entries: list[InventoryEntry] = Field(min_length=1, max_length=1000)
    labels: list[str] = Field(min_length=1, max_length=50)
    action: Literal['add', 'remove'] = 'add'

    @field_validator('labels')
    @classmethod
    def clean_labels(cls, values):
        values = sorted(set(v.strip().casefold() for v in values))
        if any(not v or len(v) > 80 or any(ord(c) < 32 for c in v) for v in values):
            raise ValueError('Labels must be printable, nonempty and at most 80 characters.')
        return values


class PlanningEntry(InventoryEntry):
    name: str = Field(min_length=1, max_length=120)
    tissue_id: str | None = Field(default=None, min_length=1, max_length=36)
    identifier_id: str | None = Field(default=None, max_length=36)
    confirmed: bool


class PlanningSelection(Actor):
    name: str = Field(min_length=1, max_length=160)
    entries: list[PlanningEntry] = Field(min_length=1, max_length=1000)


class MetadataPreview(Input):
    text: str = Field(max_length=2 * 1024 * 1024)
    id_column: str | None = Field(default=None, max_length=80)


class MetadataEntry(Input):
    matching_id: str = Field(min_length=1, max_length=120)
    fields: dict[str, str]
    expected_version: int = Field(ge=0)

    @field_validator('matching_id')
    @classmethod
    def printable_id(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('Use a printable matching ID.')
        return value


class MetadataSave(Actor):
    entries: list[MetadataEntry] = Field(min_length=1, max_length=10000)
    mode: Literal['fill', 'overwrite', 'replace'] = 'fill'


class CaptureAssignment(Input):
    photo_id: UUID
    group_name: str = Field(min_length=1, max_length=120)
    role: Literal['unknown', 'tissue', 'identifier']


class CaptureReview(Actor, InventoryEntry):
    photos: list[CaptureAssignment] = Field(min_length=1, max_length=1000)
    accept_qc: bool = False
    missing_side: Literal["", "tissue", "identifier"] = ""


class AnalyzeCapture(Actor):
    photo_id: UUID
    source: Literal['photos', 'imports']


class ImportRecord(BaseModel):
    id: UUID
    filename: str
    sha256: str
    imported_at: str
    actor: str
    label_text: str
    barcodes: list[str]
    content_type: str
    width: int
    height: int
    block_id: UUID | None
    version: int
    url: str
    thumbnail_url: str


class ImportPage(BaseModel):
    items: list[ImportRecord]
    total: int
    pending: int
    offset: int
    limit: int
    next_offset: int | None


class ErrorResponse(BaseModel):
    detail: str



class PhotoRecord(BaseModel):
    id: UUID
    block_id: UUID
    cycle: int
    kind: Literal['baseline', 'post_cut', 'reference']
    created_at: str
    actor: str
    note: str
    sha256: str
    content_type: str
    width: int
    height: int
    url: str
    thumbnail_url: str


class LinkRecord(BaseModel):
    id: UUID
    block_id: UUID
    system: str
    external_id: str
    url: str | None


class EventRecord(BaseModel):
    sequence: int
    block_id: UUID
    type: str
    actor: str
    occurred_at: str
    data: dict
    block_code: str | None = None


class BlockRecord(BaseModel):
    id: UUID
    block_code: str
    archive_year: int
    case_number: str
    case_order: int
    subspecimen: str
    cassette_number: int
    description: str
    location: str
    status: Literal['archived', 'checked_out', 'awaiting_archive']
    cycle: int
    current_photo_id: UUID | None
    created_at: str
    updated_at: str
    cut_completed_at: str | None
    version: int


class BlockDetail(BlockRecord):
    photos: list[PhotoRecord]
    external_links: list[LinkRecord]
    events: list[EventRecord]


class BlockSummary(BlockRecord):
    photo_count: int
    preview_id: UUID | None
    thumbnail_url: str | None


class SearchResults(BaseModel):
    items: list[BlockSummary]
    total: int
    offset: int
    limit: int
    next_offset: int | None
    counts: dict[str, int]


class EventPage(BaseModel):
    items: list[EventRecord]
    next_cursor: int
    has_more: bool

def create_app(data_dir=None, allowed_origins=None, api_token=None):
    directory = Path(data_dir or os.environ.get('BLOCK_ARCHIVE_DATA_DIR', ROOT / '.localdata')).resolve()
    store = Archive(directory)
    inventory.initialize(store)
    token_path = directory / 'api-token'
    if api_token is None:
        if not token_path.exists():
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(36) + '\n')
        api_token = token_path.read_text().strip()
    if len(api_token) < 24:
        raise ValueError('API token must contain at least 24 characters.')
    session = secrets.token_urlsafe(36)
    origins = set(allowed_origins or ('http://127.0.0.1:8780', 'http://localhost:8780'))
    app = FastAPI(title='Block Archive API', version='1.0.0', docs_url=None, redoc_url=None,
                  description='Year/case archive organization, post-cut image history, and block-code links. '
                              'Authenticate external clients with a bearer token. Images and events may contain identifying data.',
                  responses={401: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 422: {'description': 'Invalid input'}})
    app.state.archive = store
    manager = projects.ProjectManager(directory, store)
    app.state.projects = manager
    store = projects.RequestArchive(manager)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(o).hostname for o in origins])

    @app.exception_handler(ArchiveError)
    async def archive_error(request, exc):
        return JSONResponse({'detail': exc.message}, status_code=exc.status)

    @app.middleware('http')
    async def boundaries(request, call_next):
        if request.headers.get('host') not in {urlsplit(o).netloc for o in origins}:
            return JSONResponse({'detail': 'Host not allowed.'}, status_code=403)
        if request.method in ('POST', 'PATCH', 'PUT'):
            try:
                length = int(request.headers.get('content-length', '-1'))
            except ValueError:
                length = -1
            maximum = (projects.MAX_PROJECT_BYTES + 65536 if request.url.path == '/api/v1/projects/import' else
                       projects.MAX_EXPERIMENT_BYTES if request.url.path in ('/api/v1/projects/export','/api/v1/local-saves/project','/api/v1/local-saves/experiment') else
                       MAX_IMAGE_BYTES + 65536 if request.url.path.endswith('/photos') else
                       25 * 1024 * 1024 if request.url.path == '/api/analyze' else
                       16 * 1024 * 1024 if request.url.path.startswith('/api/v1/metadata') else
                       1024 * 1024 if request.url.path in ('/api/v1/inventory/labels', '/api/v1/planning-selections') else 65536)
            if length < 0:
                return JSONResponse({'detail': 'A Content-Length header is required.'}, status_code=411)
            if length > maximum:
                return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
        project_id = request.cookies.get('block_archive_project', 'local')
        claimed = request.headers.get('x-archive-project')
        token_client = secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer '+api_token)
        if token_client:
            project_id = claimed or 'local'
        elif request.url.path.startswith('/api/'):
            if (claimed and claimed != project_id) or (not claimed and project_id != 'local' and request.method not in ('GET','HEAD') and request.url.path not in ('/api/labels','/api/labels.pdf','/api/analyze')):
                return JSONResponse({'detail':'The active project changed in another tab. Reload this page before continuing.'},status_code=409)
        try:
            manager.directory(project_id)
        except ArchiveError as error:
            return JSONResponse({'detail':error.message},status_code=error.status)
        context = projects.CURRENT_PROJECT.set(project_id)
        try:
            response = await call_next(request)
        finally:
            projects.CURRENT_PROJECT.reset(context)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        if request.url.path.startswith('/planner/'):
            response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    bearer = HTTPBearer(auto_error=False)

    def authorized(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        origin = request.headers.get('origin')
        if origin and origin not in origins:
            raise HTTPException(403, 'Origin not allowed.')
        if credentials and secrets.compare_digest(credentials.credentials, api_token):
            return
        cookie = request.cookies.get('block_archive_session', '')
        if not cookie or not secrets.compare_digest(cookie, session):
            raise HTTPException(401, 'Authentication required.', headers={'WWW-Authenticate': 'Bearer'})
        if request.headers.get('sec-fetch-site', 'same-origin') not in ('same-origin', 'none'):
            raise HTTPException(403, 'Use the archive from its own local page.')
        if request.method not in ('GET', 'HEAD'):
            if origin not in origins or request.headers.get('x-archive-request') != '1':
                raise HTTPException(403, 'A same-origin archive request is required.')

    protected = [Depends(authorized)]

    @app.get('/', include_in_schema=False)
    def index():
        response = FileResponse(ROOT / 'static/inventory.html')
        response.set_cookie('block_archive_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/archive', include_in_schema=False)
    def archive_page():
        response = FileResponse(ROOT / 'static/index.html')
        response.set_cookie('block_archive_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/planner', include_in_schema=False)
    def planner_redirect():
        return RedirectResponse('/planner/')

    @app.get('/planner/{name:path}', include_in_schema=False)
    def planner_asset(name: str):
        name = name or 'index.html'
        # Frozen macOS bundles use a symlink from Frameworks to Resources.
        base = (ROOT / 'planner').resolve()
        path = (base / name).resolve()
        if name not in PLANNER_ASSETS or not path.is_relative_to(base) or not path.is_file():
            raise HTTPException(404, 'Not found.')
        response = FileResponse(path)
        if name == 'index.html':
            response.set_cookie('block_archive_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/static/{name}', include_in_schema=False)
    def asset(name: str):
        if name not in ('app.js', 'style.css', 'api.html', 'imports.html', 'imports.js',
                        'inventory.js', 'inventory.css', 'inventory-filter.js', 'intake.js', 'metadata.js', 'project-workspace.js', 'project-workspace.css'):
            raise HTTPException(404, 'Not found.')
        return FileResponse(ROOT / 'static' / name)

    @app.get('/api/v1/project', dependencies=protected, tags=['Projects'])
    def current_project():
        return manager.info(projects.CURRENT_PROJECT.get())

    @app.get('/api/v1/projects', dependencies=protected, tags=['Projects'])
    def project_list():
        return {'items':manager.list()}

    @app.post('/api/v1/projects', dependencies=protected, status_code=201, tags=['Projects'])
    def new_project(body: ProjectName):
        if not body.name.strip():
            raise HTTPException(422, 'Enter a project name.')
        return manager.create(body.name.strip())

    @app.post('/api/v1/projects/{project_id}/open', dependencies=protected, tags=['Projects'])
    def open_project(project_id: str):
        response = JSONResponse(manager.info(project_id))
        response.set_cookie('block_archive_project', project_id, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/api/v1/projects/{project_id}/experiments', dependencies=protected, tags=['Projects'])
    def restored_experiments(project_id: str):
        return local_saves.experiments(manager,project_id)

    @app.get('/api/v1/save-location', dependencies=protected, tags=['Projects'])
    def save_location():
        return local_saves.location(manager,projects.CURRENT_PROJECT.get())

    @app.post('/api/v1/save-location', dependencies=protected, tags=['Projects'])
    def set_save_location(body: dict):
        return local_saves.configure(manager,projects.CURRENT_PROJECT.get(),body.get('folder'))

    @app.post('/api/v1/save-location/browse', dependencies=protected, tags=['Projects'])
    def browse_save_location():
        return local_saves.browse()

    @app.post('/api/v1/local-saves/{kind}', dependencies=protected, tags=['Projects'])
    def save_locally(kind: Literal['project','experiment'], body: dict):
        return local_saves.save(manager,projects.CURRENT_PROJECT.get(),body,kind)

    @app.post('/api/v1/projects/export', dependencies=protected, tags=['Projects'])
    def save_project(body: dict):
        handle = tempfile.NamedTemporaryFile(prefix='project-', suffix='.json', dir=directory, delete=False)
        path = Path(handle.name); handle.close()
        try:
            projects.export_project(store,manager.info(projects.CURRENT_PROJECT.get())['name'],body,path)
        except BaseException:
            path.unlink(missing_ok=True); raise
        return FileResponse(path,media_type='application/json',filename='block-archive-project.json',
                            background=BackgroundTask(path.unlink,missing_ok=True))

    @app.post('/api/v1/projects/import', dependencies=protected, status_code=201, tags=['Projects'])
    def restore_project(file: UploadFile = File()):
        try:
            if file.size is not None and file.size > projects.MAX_PROJECT_BYTES:
                raise HTTPException(413,'Project exceeds the 2 GB JSON limit.')
            try:
                document = json.load(file.file)
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(422,'Choose a valid project JSON file.')
            return projects.import_project(manager,document)
        finally:
            file.file.close()

    @app.get('/api/v1/inventory', dependencies=protected, tags=['Planning'])
    def inventory_items():
        return {'items': inventory.list_items(store)}

    @app.get('/api/v1/metadata', dependencies=protected, tags=['Metadata'])
    def metadata_records():
        with store.connect() as db:
            return {'records':list(metadata.records(db).values())}

    @app.post('/api/v1/metadata/preview', dependencies=protected, tags=['Metadata'])
    def preview_metadata(body: MetadataPreview):
        return metadata.preview(store, body.text, body.id_column)

    @app.post('/api/v1/metadata/columns', dependencies=protected, tags=['Metadata'])
    def metadata_columns(body: MetadataPreview):
        return metadata.columns(body.text)

    @app.post('/api/v1/metadata', dependencies=protected, tags=['Metadata'])
    def save_metadata(body: MetadataSave):
        metadata.save(store, [entry.model_dump() for entry in body.entries], body.actor, body.mode)
        return {'saved':len(body.entries)}

    @app.post('/api/v1/inventory/review', dependencies=protected, tags=['Planning'])
    def review_capture(body: CaptureReview):
        photos = [{**p.model_dump(), 'photo_id':str(p.photo_id)} for p in body.photos]
        return {'keys':capture_review.save_review(store,body.key,body.revision,photos,body.actor,body.accept_qc,body.missing_side)}

    @app.post('/api/v1/inventory/analyze', dependencies=protected, tags=['Planning'])
    def analyze_capture(body: AnalyzeCapture):
        path, _ = (store.photo_path(str(body.photo_id)) if body.source == 'photos' else store.inbox_path(str(body.photo_id)))
        from block_archive.vision import analyze
        try:
            result = analyze(path.read_bytes())
        except Exception:
            result = {'error':'Photo analysis failed.'}
        capture_review.record_analysis(store,str(body.photo_id),result)
        return {'status':'analyzed' if not result.get('error') else 'needs_review'}

    @app.post('/api/v1/inventory/labels', dependencies=protected, tags=['Planning'])
    def inventory_labels(body: InventoryLabels):
        inventory.label_items(store, [e.model_dump() for e in body.entries], body.labels, body.action, body.actor)
        return {'status': 'ok'}

    @app.post('/api/v1/planning-selections', dependencies=protected, status_code=201, tags=['Planning'])
    def planning_selection(body: PlanningSelection):
        result = inventory.create_selection(store, body.name, body.actor, [e.model_dump() for e in body.entries])
        return {'id': result['id'], 'url': '/planner/?selection=' + result['id']}

    @app.get('/api/v1/planning-selections/{selection_id}', dependencies=protected, tags=['Planning'])
    def planning_selection_detail(selection_id: UUID):
        return inventory.get_selection(store, str(selection_id))

    @app.post('/api/analyze', dependencies=protected, include_in_schema=False)
    async def analyze_photo(request: Request):
        from block_archive.vision import analyze
        try:
            return await run_in_threadpool(analyze, await request.body())
        except Exception:
            raise HTTPException(422, 'Image analysis failed. Check the format and size.')

    @app.post('/api/v1/inventory/photos', dependencies=protected, status_code=201, tags=['Planning'])
    def import_inventory_photo(file: UploadFile = File(), actor: str = Form(min_length=1, max_length=80)):
        actor = actor.strip()
        if not actor:
            raise HTTPException(422, 'An operator is required.')
        try:
            raw = file.file.read(MAX_IMAGE_BYTES + 1)
        finally:
            file.file.close()
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(413, 'Choose a photo no larger than 20 MB.')
        filename = Path(file.filename or 'uploaded-photo').name[:255]
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.upload') as temporary:
            temporary.write(raw); temporary.flush()
            # Import validates image dimensions and format before running computer vision.
            image_id, created = store.import_image(temporary.name, actor=actor, filename=filename)
        with store.connect() as db:
            analyzed = db.execute('SELECT 1 FROM capture_analysis WHERE photo_id=?',(image_id,)).fetchone()
        if created or not analyzed:
            from block_archive.vision import analyze
            try:
                result = analyze(raw)
                codes = [code for code in result['qrValues'] if code and len(code) <= 120]
            except Exception:
                codes = []; result = {'error':'Photo analysis failed.'}
            capture_review.record_analysis(store,image_id,result)
            if codes and created:
                with store.connect(write=True) as db:
                    db.execute('UPDATE import_images SET barcodes=? WHERE id=?', (json.dumps(codes), image_id))
                    db.execute('UPDATE import_search SET barcodes=? WHERE image_id=?', (json.dumps(codes), image_id))
        return {'id': image_id, 'created': created}

    @app.post('/api/labels', dependencies=protected, include_in_schema=False)
    @app.post('/api/labels.pdf', dependencies=protected, include_in_schema=False)
    async def planner_labels(request: Request):
        try:
            values = parse_ids((await request.body()).decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise HTTPException(422, 'Provide a valid one-column ID list.')
        if request.url.path.endswith('.pdf'):
            return Response(pdf_bytes(values), media_type='application/pdf')
        return [{'id': value, 'png': 'data:image/png;base64,' + base64.b64encode(qr_png(value)).decode()} for value in values]

    @app.get('/api/v1/health', tags=['Service'])
    def health():
        return {'status': 'ok', 'version': '1.0.0'}

    @app.get('/imports', include_in_schema=False)
    def imports_page():
        response = FileResponse(ROOT / 'static/imports.html')
        response.set_cookie('block_archive_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/api/v1/imports', dependencies=protected, tags=['Imports'], response_model=ImportPage)
    def imports(query: str = Query('', max_length=120), status: Literal['pending', 'linked', 'all'] = 'pending',
                limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
        return store.inbox_list(query, status, limit, offset)

    @app.get('/api/v1/imports/{image_id}', dependencies=protected, tags=['Imports'], response_model=ImportRecord)
    def imported_image(image_id: UUID):
        return store.inbox_detail(str(image_id))

    @app.get('/api/v1/imports/{image_id}/image', dependencies=protected, tags=['Imports'], response_class=FileResponse,
             responses={200: {'content': {mime: {'schema': {'type': 'string', 'format': 'binary'}} for mime in ('image/jpeg', 'image/png', 'image/webp')}}})
    def import_image(image_id: UUID):
        path, mime = store.inbox_path(str(image_id))
        return FileResponse(path, media_type=mime)

    @app.get('/api/v1/imports/{image_id}/experiment-image', dependencies=protected, include_in_schema=False)
    def import_experiment_image(image_id: UUID):
        path, _ = store.inbox_path(str(image_id))
        return experiment_image(store,path,str(image_id))

    @app.get('/api/v1/photos/{photo_id}/experiment-image', dependencies=protected, include_in_schema=False)
    def registered_experiment_image(photo_id: UUID):
        path, _ = store.photo_path(str(photo_id))
        return experiment_image(store,path,str(photo_id))

    @app.get('/api/v1/imports/{image_id}/block-preview', dependencies=protected, include_in_schema=False)
    def import_block_preview(image_id: UUID):
        path, _ = store.inbox_path(str(image_id))
        return FileResponse(block_preview(store,path,str(image_id)),media_type='image/jpeg')

    @app.get('/api/v1/photos/{photo_id}/block-preview', dependencies=protected, include_in_schema=False)
    def registered_block_preview(photo_id: UUID):
        path, _ = store.photo_path(str(photo_id))
        return FileResponse(block_preview(store,path,str(photo_id)),media_type='image/jpeg')

    @app.get('/api/v1/imports/{image_id}/thumbnail', dependencies=protected, tags=['Imports'], response_class=FileResponse,
             responses={200: {'content': {'image/jpeg': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def import_thumbnail(image_id: UUID):
        path, mime = store.inbox_path(str(image_id), True)
        return FileResponse(path, media_type=mime)

    @app.post('/api/v1/imports/{image_id}/confirm', dependencies=protected, tags=['Imports'], response_model=BlockDetail)
    def confirm_import(image_id: UUID, body: ConfirmImport):
        return store.confirm_import(str(image_id), **(body.model_dump() | {'block_id': str(body.block_id)}))

    @app.get('/api/v1/blocks', dependencies=protected, tags=['Blocks'], response_model=SearchResults)
    def blocks(query: str = Query('', max_length=120),
               status: Literal['archived', 'checked_out', 'awaiting_archive'] | None = None,
               year: int | None = Query(None, ge=1900, le=2199),
               case_number: str | None = Query(None, pattern=r'^[0-9]{1,12}$'),
               sort: Literal['archive', 'recent'] = 'archive', limit: int = Query(40, ge=1, le=100),
               offset: int = Query(0, ge=0)):
        return store.list(query, status, limit, offset, year, sort, case_number)

    @app.get('/api/v1/blocks/by-code', dependencies=protected, tags=['Blocks'], response_model=BlockDetail)
    def by_code(block_code: str = Query(min_length=1, max_length=120)):
        """Exact case-insensitive lookup. Query parameter supports codes containing slashes or punctuation."""
        return store.by_code(block_code)

    @app.post('/api/v1/blocks', dependencies=protected, status_code=201, tags=['Blocks'], response_model=BlockDetail)
    def register(body: NewBlock):
        return store.create(**body.model_dump())

    @app.get('/api/v1/blocks/{block_id}', dependencies=protected, tags=['Blocks'], response_model=BlockDetail)
    def block(block_id: UUID):
        return store.detail(str(block_id))

    @app.patch('/api/v1/blocks/{block_id}', dependencies=protected, tags=['Blocks'], response_model=BlockDetail)
    def edit(block_id: UUID, body: EditBlock):
        return store.update(str(block_id), **body.model_dump())

    @app.post('/api/v1/blocks/{block_id}/checkout', dependencies=protected, tags=['Movements'], response_model=BlockDetail)
    def checkout(block_id: UUID, body: Movement):
        return store.transition(str(block_id), 'checkout', **body.model_dump())

    @app.post('/api/v1/blocks/{block_id}/complete-cut', dependencies=protected, tags=['Movements'], response_model=BlockDetail)
    def complete_cut(block_id: UUID, body: Movement):
        return store.transition(str(block_id), 'complete-cut', **body.model_dump())

    @app.post('/api/v1/blocks/{block_id}/rearchive', dependencies=protected, tags=['Movements'], response_model=BlockDetail)
    def rearchive(block_id: UUID, body: Rearchive):
        data = body.model_dump(); data['photo_id'] = str(body.photo_id)
        return store.transition(str(block_id), 'rearchive', **data)

    @app.post('/api/v1/blocks/{block_id}/photos', dependencies=protected, status_code=201, tags=['Photos'], response_model=BlockDetail)
    def photo(block_id: UUID, file: UploadFile = File(),
              kind: Literal['baseline', 'post_cut', 'reference'] = Form(),
              actor: str = Form(min_length=1, max_length=80), expected_version: int = Form(ge=1),
              note: str = Form('', max_length=2000)):
        actor = actor.strip()
        if not actor:
            raise HTTPException(422, 'An operator is required.')
        try:
            raw = file.file.read(MAX_IMAGE_BYTES + 1)
        finally:
            file.file.close()
        return store.add_photo(str(block_id), raw, kind, actor, note, expected_version)

    @app.get('/api/v1/photos/{photo_id}/image', dependencies=protected, tags=['Photos'], response_class=FileResponse,
             responses={200: {'content': {mime: {'schema': {'type': 'string', 'format': 'binary'}} for mime in ('image/jpeg', 'image/png', 'image/webp')}}})
    def image(photo_id: UUID):
        path, content_type = store.photo_path(str(photo_id))
        return FileResponse(path, media_type=content_type)

    @app.get('/api/v1/photos/{photo_id}/thumbnail', dependencies=protected, tags=['Photos'], response_class=FileResponse,
             responses={200: {'content': {'image/jpeg': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def thumbnail(photo_id: UUID):
        path, content_type = store.photo_path(str(photo_id), thumbnail=True)
        return FileResponse(path, media_type=content_type)

    @app.put('/api/v1/blocks/{block_id}/external-links', dependencies=protected, tags=['Links'], response_model=BlockDetail)
    def link(block_id: UUID, body: ExternalLink):
        data = body.model_dump(); data['url'] = str(body.url) if body.url else None
        return store.link(str(block_id), **data)

    @app.get('/api/v1/events', dependencies=protected, tags=['Integration'], response_model=EventPage)
    def events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        """Poll committed events with an increasing cursor; persist next_cursor after processing."""
        return store.events(after, limit)

    @app.get('/api/v1/blocks/{block_id}/label.pdf', dependencies=protected, tags=['Blocks'], response_class=FileResponse,
             responses={200: {'content': {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def label(block_id: UUID):
        from fastapi.responses import Response
        record = store.detail(str(block_id))
        return Response(pdf_bytes([record['block_code']]), media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="block-label.pdf"'})

    @app.get('/api/v1/backup', dependencies=protected, tags=['Service'], response_class=FileResponse,
             responses={200: {'content': {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def backup():
        handle = tempfile.NamedTemporaryFile(prefix='block-archive-', suffix='.zip', dir=directory, delete=False)
        path = Path(handle.name); handle.close()
        try:
            store.backup(path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(path, media_type='application/zip', filename='block-archive-backup.zip',
                            background=BackgroundTask(path.unlink, missing_ok=True))

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8780)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    app = create_app(args.data_dir, {f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}'})
    print(f'Block Archive: http://127.0.0.1:{args.port}', flush=True)
    print('API token is stored in the private data directory; request logging is disabled.', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
