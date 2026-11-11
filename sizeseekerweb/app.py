"""FastAPI application: JSON API under /api plus the static web UI."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool

from . import __version__, system
from .duplicates import VerifyBusyError
from .indexer import IndexBusyError, IndexManager, NotIndexedError, local_drive_roots
from .settings import Settings
from .scanner import ScanBusyError, ScanManager, normalize_path, norm_key

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_METHODS = {"GET", "HEAD"}
CSRF_HEADER = "x-sizeseeker"
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class PathBody(BaseModel):
    path: str


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _checked_dir(path: str) -> str:
    if not path or not os.path.isabs(path):
        raise _error(400, "invalid_path", "Path must be absolute")
    path = normalize_path(path)
    if not os.path.isdir(path):
        raise _error(404, "not_found", "Folder not found")
    return path


class SettingsBody(BaseModel):
    scan_on_start: StrictBool  # no "yes"/"1" -> True coercion


def create_app(port: int, manager: ScanManager | None = None, index: IndexManager | None = None,
               settings: Settings | None = None, scan_roots=None) -> FastAPI:
    manager = manager or ScanManager()
    index = index or IndexManager(system.data_dir())
    settings = settings or Settings(system.data_dir() / "settings.json")
    scan_roots = scan_roots or local_drive_roots  # "scan all": the same disks as the search index
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    app = FastAPI(title="SizeSeekerWeb", version=__version__, docs_url=None, redoc_url=None)
    app.state.manager = manager
    app.state.index = index
    app.state.settings = settings
    app.state.scan_roots = scan_roots

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Blocks DNS rebinding: only requests addressed to our own loopback host.
        if request.headers.get("host", "") not in allowed_hosts:
            return JSONResponse({"detail": {"code": "forbidden_host"}}, status_code=403)
        if request.method not in SAFE_METHODS:
            # Other websites can neither send this custom header (it needs a CORS
            # preflight we never allow) nor fake the Origin.
            origin = request.headers.get("origin")
            if request.headers.get(CSRF_HEADER) != "1" or (origin and origin not in allowed_origins):
                return JSONResponse({"detail": {"code": "forbidden_origin"}}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            # Always revalidate (cheap via ETag), otherwise browsers keep the
            # JavaScript of the previous version after an update.
            response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # ------------------------------------------------------------------ API
    @app.get("/api/version")
    def version():
        return {"app": "SizeSeekerWeb", "version": __version__}

    @app.get("/api/drives")
    def drives():
        return system.list_drives()

    @app.post("/api/scans", status_code=202)
    def start_scan(body: PathBody):
        path = _checked_dir(body.path)
        try:
            scan = manager.start(path)
        except ScanBusyError as exc:
            raise _error(409, "scan_running", f"A scan of {exc} is already running") from None
        return scan.status()

    @app.get("/api/scans/current")
    def current_scan():
        scan = manager.current
        return scan.status() if scan else None

    @app.delete("/api/scans/current")
    def cancel_scan():
        return {"cancelled": manager.cancel()}

    @app.get("/api/scans/all")
    def scan_all_status():
        batch = manager.batch
        return {"batch": batch.status() if batch else None, "scanned": manager.scanned_roots(),
                "roots": scan_roots()}

    @app.post("/api/scans/all", status_code=202)
    def scan_all():
        roots = scan_roots()
        if not roots:
            raise _error(400, "no_drives", "No local drives found")
        try:
            manager.start_batch(roots)
        except ScanBusyError:
            raise _error(409, "scan_running", "All drives are already being scanned") from None
        return scan_all_status()

    @app.delete("/api/scans/all")
    def cancel_scan_all():
        return {"cancelled": manager.cancel_batch()}

    @app.get("/api/settings")
    def get_settings():
        return settings.as_dict()

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        return settings.update(scan_on_start=body.scan_on_start)

    @app.get("/api/folder")
    def folder(path: str = Query(...)):
        path = _checked_dir(path)
        scan = manager.scan_for(path)
        node = scan.find(path) if scan else None
        entries = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    entries.append(_entry(entry, node))
        except PermissionError:
            raise _error(403, "access_denied", "Access denied") from None
        except OSError as exc:
            raise _error(500, "read_error", str(exc)) from None

        known = sum(e["size"] for e in entries if e["size"] is not None)
        for e in entries:
            e["percent"] = round(e["size"] * 100 / known, 2) if known and e["size"] is not None else None

        parent = os.path.dirname(path)
        return {
            "path": path,
            "name": os.path.basename(path) or path,
            "parent": parent if parent != path else None,
            "scanned": node is not None,
            "scan": {"root": scan.root_path, "finished_at": scan.finished_at} if scan else None,
            "size": node.size if node else known,
            "files": node.files if node else None,
            "dirs": node.dirs if node else None,
            "errors": node.errors if node else None,
            "entries": entries,
        }

    @app.get("/api/largest")
    def largest(path: str = Query(...), limit: int = Query(50, ge=1, le=500)):
        path = _checked_dir(path)
        scan = manager.scan_for(path)
        if scan is None:
            raise _error(409, "not_scanned", "Folder has not been scanned yet")
        return [
            {"path": p, "name": os.path.basename(p), "kind": system.file_kind(p), "size": s}
            for s, p in scan.largest_files(path, limit)
        ]

    @app.get("/api/index")
    def index_status():
        return index.status()

    @app.post("/api/index", status_code=202)
    def start_index():
        try:
            index.start()
        except IndexBusyError:
            raise _error(409, "index_running", "Indexing is already running") from None
        except ValueError as exc:
            raise _error(400, "no_drives", str(exc)) from None
        return index.status()

    @app.delete("/api/index/build")
    def cancel_index():
        return {"cancelled": index.cancel()}

    @app.get("/api/search")
    def search(
        q: str = Query(..., min_length=1, max_length=300),
        kind: str = Query("all", pattern="^(all|dir|file)$"),
        limit: int = Query(200, ge=1, le=1000),
    ):
        try:
            found = index.search(q, kind, limit)
        except NotIndexedError:
            raise _error(409, "not_indexed", "Nothing indexed yet") from None
        for item in found["results"]:
            item["kind"] = "dir" if item.pop("dir") else system.file_kind(item["name"])
        found["index"] = index.info()
        return found

    @app.get("/api/duplicates")
    def duplicates(
        kind: str = Query("all", pattern="^(all|dir|file)$"),
        q: str = Query("", max_length=300),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
    ):
        return index.duplicates.groups(kind, q, offset, limit)

    @app.post("/api/duplicates/{group_id}/verify", status_code=202)
    def verify_duplicates(group_id: int):
        try:
            job = index.duplicates.verify(group_id)
        except VerifyBusyError:
            raise _error(409, "verify_running", "Another check is running") from None
        except KeyError:
            raise _error(404, "not_found", "Unknown duplicate group") from None
        return job.status()

    @app.get("/api/duplicates/verify")
    def verify_status():
        return index.duplicates.verification_status()

    @app.delete("/api/duplicates/verify")
    def cancel_verify():
        return {"cancelled": index.duplicates.cancel_verification()}

    @app.post("/api/reveal")
    def reveal(body: PathBody):
        try:
            system.reveal_in_explorer(body.path)
        except FileNotFoundError:
            raise _error(404, "not_found", "Path not found") from None
        except NotImplementedError as exc:
            raise _error(501, "unsupported", str(exc)) from None
        return {"ok": True}

    # ------------------------------------------------------------------ UI
    @app.get("/", include_in_schema=False)
    def ui_page():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def scan_on_start(app: FastAPI) -> bool:
    """Start "scan all drives" if the user switched that on. True if started."""
    if not app.state.settings.get("scan_on_start"):
        return False
    roots = app.state.scan_roots()
    if not roots:
        return False
    try:
        app.state.manager.start_batch(roots)
    except ScanBusyError:
        return False
    return True


def _entry(entry: os.DirEntry, node) -> dict:
    item = {"name": entry.name, "path": entry.path, "kind": "other", "size": None,
            "files": None, "dirs": None, "errors": None}
    try:
        if entry.is_symlink() or entry.is_junction():
            item["kind"] = "link"
        elif entry.is_dir(follow_symlinks=False):
            item["kind"] = "dir"
            child = node.children.get(norm_key(entry.name)) if node else None
            if child is not None:
                item.update(size=child.size, files=child.files, dirs=child.dirs, errors=child.errors)
        else:
            item["kind"] = system.file_kind(entry.name)
            item["size"] = entry.stat(follow_symlinks=False).st_size
    except OSError:
        item["kind"] = "other"
    return item
