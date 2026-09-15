"""Block Archive: local browser workspace and authenticated versioned API."""
from pathlib import Path
from typing import Literal
import argparse
import json
import os
import secrets
import tempfile
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from archive import Archive, ArchiveError, MAX_IMAGE_BYTES
from label_pdf import pdf_bytes

ROOT = Path(__file__).resolve().parent


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
    app = FastAPI(title='Block Archive API', version='0.1.0', docs_url=None, redoc_url=None,
                  description='Year/case archive organization, post-cut image history, and block-code links. '
                              'Authenticate external clients with a bearer token. Images and events may contain identifying data.',
                  responses={401: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 422: {'description': 'Invalid input'}})
    app.state.archive = store
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
            maximum = MAX_IMAGE_BYTES + 65536 if request.url.path.endswith('/photos') else 65536
            if length < 0:
                return JSONResponse({'detail': 'A Content-Length header is required.'}, status_code=411)
            if length > maximum:
                return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
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
        response = FileResponse(ROOT / 'static/index.html')
        response.set_cookie('block_archive_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/static/{name}', include_in_schema=False)
    def asset(name: str):
        if name not in ('app.js', 'style.css', 'api.html', 'imports.html', 'imports.js'):
            raise HTTPException(404, 'Not found.')
        return FileResponse(ROOT / 'static' / name)

    @app.get('/api/v1/health', tags=['Service'])
    def health():
        return {'status': 'ok', 'version': '0.1.0'}

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


if __name__ == '__main__':
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
