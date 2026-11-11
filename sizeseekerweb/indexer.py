"""Search index over every folder and file of the local drives.

Building
    All roots are walked once with a pool of worker threads (like :mod:`scanner`).
    Entries are streamed straight into flat files, so building needs little RAM:

    ``names.bin``        original names, UTF-8, one per line
    ``lower.bin``        lowercased names, UTF-8, one per line (searched)
    ``names.off`` / ``lower.off``  uint32 start offsets (n + 1 values)
    ``parent.bin``       int32 index of the parent entry (-1 for a root)
    ``size.bin``         int64 size (folders: whole subtree, filled in at the end)
    ``flags.bin``        uint8, bit 0 = folder
    ``meta.json``        roots, counts, creation time

    A parent always gets a smaller index than its children, which makes the
    final folder-size pass a single backwards loop.

Searching
    The files are memory-mapped. A query is split into words; every word must
    match the name (substring, or a ``*``/``?`` pattern that must match the whole
    name). Candidates come from ``bytes.find`` of the longest literal piece in
    the lowercased name blob, so typical searches over millions of names take
    milliseconds.
"""

from __future__ import annotations

import array
import fnmatch
import json
import logging
import mmap
import os
import queue
import shutil
import sys
import threading
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from .scanner import DEFAULT_WORKERS

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
FLAG_DIR = 1
INDEXABLE_FILESYSTEMS = {"NTFS", "REFS", "EXFAT"}
DRIVE_FIXED = 3
MAX_BLOB = 2**32 - 1
CANDIDATE_LIMIT = 2000  # matches collected before ranking
ARRAYS = {"names.off": "I", "lower.off": "I", "parent.bin": "i", "size.bin": "q", "flags.bin": "B"}


def is_indexable(drive_type: int, filesystem: str) -> bool:
    """Fixed local disks only. Cloud drives (Google Drive pretends to be a fixed
    FAT32 disk) as well as network, USB and optical drives are skipped."""
    return drive_type == DRIVE_FIXED and filesystem.upper() in INDEXABLE_FILESYSTEMS


def local_drive_roots() -> list[str]:
    if sys.platform != "win32":
        return ["/"]
    import ctypes

    from .system import list_drive_roots

    kernel32 = ctypes.windll.kernel32
    roots = []
    for root in list_drive_roots():
        fs = ctypes.create_unicode_buffer(261)
        ok = kernel32.GetVolumeInformationW(ctypes.c_wchar_p(root), None, 0, None, None, None, fs, len(fs))
        if ok and is_indexable(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)), fs.value):
            roots.append(root)
    return roots


# ---------------------------------------------------------------------- building
@dataclass
class BuildProgress:
    entries: int = 0
    dirs: int = 0
    current: str = ""


class _Writer:
    """Appends entries to the flat files and hands out their indexes."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.names = open(folder / "names.bin", "wb", buffering=1 << 20)
        self.lower = open(folder / "lower.bin", "wb", buffering=1 << 20)
        self.names_off = array.array("I", [0])
        self.lower_off = array.array("I", [0])
        self.parent = array.array("i")
        self.size = array.array("q")
        self.flags = array.array("B")

    @property
    def count(self) -> int:
        return len(self.parent)

    def add(self, name: str, parent: int, is_dir: bool, size: int) -> int:
        raw = name.encode("utf-8", "surrogatepass") + b"\n"
        low = name.lower().encode("utf-8", "surrogatepass") + b"\n"
        names_end = self.names_off[-1] + len(raw)
        lower_end = self.lower_off[-1] + len(low)
        if names_end > MAX_BLOB or lower_end > MAX_BLOB:
            raise OverflowError("index too large")
        self.names.write(raw)
        self.lower.write(low)
        self.names_off.append(names_end)
        self.lower_off.append(lower_end)
        self.parent.append(parent)
        self.size.append(size)
        self.flags.append(FLAG_DIR if is_dir else 0)
        return len(self.parent) - 1

    def finish(self, meta: dict) -> None:
        self.names.close()
        self.lower.close()
        # Folder sizes: children always come after their parent.
        size, parent = self.size, self.parent
        for i in range(len(parent) - 1, -1, -1):
            p = parent[i]
            if p >= 0:
                size[p] += size[i]
        for fname, arr in (("names.off", self.names_off), ("lower.off", self.lower_off),
                           ("parent.bin", parent), ("size.bin", size), ("flags.bin", self.flags)):
            with open(self.folder / fname, "wb") as fh:
                arr.tofile(fh)
        (self.folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def abort(self) -> None:
        self.names.close()
        self.lower.close()


class IndexBuild:
    """One run of "index everything" into ``target`` (a fresh folder)."""

    def __init__(self, roots: list[str], target: Path, workers: int = DEFAULT_WORKERS) -> None:
        self.roots = [os.path.abspath(r) for r in roots]
        self.target = target
        self.workers = max(1, workers)
        self.state = "pending"  # pending | running | done | cancelled | error
        self.error_message: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.errors = 0
        self.progress = BuildProgress()
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def finished(self) -> bool:
        return self.state in ("done", "cancelled", "error")

    def run(self) -> None:
        self.state = "running"
        self.started_at = time.time()
        writer = None
        try:
            if self.target.exists():
                shutil.rmtree(self.target)
            self.target.mkdir(parents=True)
            writer = _Writer(self.target)
            self._walk(writer)
            if self._cancel.is_set():
                writer.abort()
                self.state = "cancelled"
                return
            self.finished_at = time.time()
            writer.finish({
                "version": FORMAT_VERSION,
                "roots": self.roots,
                "entries": writer.count,
                "dirs": self.progress.dirs,
                "errors": self.errors,
                "created_at": self.finished_at,
                "duration": self.finished_at - self.started_at,
            })
            self.state = "done"
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            log.exception("indexing failed")
            if writer is not None:
                writer.abort()
            self.state = "error"
            self.error_message = str(exc)
        finally:
            self.finished_at = self.finished_at or time.time()

    def _walk(self, writer: _Writer) -> None:
        work: queue.Queue[tuple[int, str] | None] = queue.Queue()
        for root in self.roots:
            work.put((writer.add(root, -1, True, 0), root))

        def worker() -> None:
            while True:
                item = work.get()
                try:
                    if item is None:
                        return
                    if not self._cancel.is_set():
                        for sub in self._scan_dir(writer, *item):
                            work.put(sub)
                except Exception:  # noqa: BLE001 - e.g. index too large: stop everything
                    log.exception("indexing worker failed")
                    self.error_message = self.error_message or "indexing failed"
                    self._cancel.set()
                finally:
                    work.task_done()

        threads = [threading.Thread(target=worker, daemon=True, name=f"sizeseeker-index-{i}") for i in range(self.workers)]
        for t in threads:
            t.start()
        work.join()
        for _ in threads:
            work.put(None)
        for t in threads:
            t.join()
        if self.error_message:
            raise RuntimeError(self.error_message)

    def _scan_dir(self, writer: _Writer, index: int, path: str) -> list[tuple[int, str]]:
        found: list[tuple[str, bool, int, str]] = []
        failed = False
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._cancel.is_set():
                        break
                    try:
                        if entry.is_symlink() or entry.is_junction():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            found.append((entry.name, True, 0, entry.path))
                        else:
                            found.append((entry.name, False, entry.stat(follow_symlinks=False).st_size, ""))
                    except OSError:
                        failed = True
        except OSError:
            failed = True

        subdirs = []
        with self._lock:
            for name, is_dir, size, sub_path in found:
                child = writer.add(name, index, is_dir, size)
                if is_dir:
                    subdirs.append((child, sub_path))
            self.progress.entries = writer.count
            self.progress.dirs += 1
            self.progress.current = path
            self.errors += failed
        return subdirs

    def status(self) -> dict:
        with self._lock:
            progress = {"entries": self.progress.entries, "dirs": self.progress.dirs, "current": self.progress.current}
        return {
            "state": self.state,
            "error": self.error_message,
            "roots": self.roots,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": progress,
        }


# ---------------------------------------------------------------------- searching
class IndexReader:
    """Read-only, memory-mapped view of a finished index."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        if self.meta.get("version") != FORMAT_VERSION:
            raise ValueError("unsupported index version")
        self._maps: list[mmap.mmap] = []
        self.names = self._map("names.bin")
        self.lower = self._map("lower.bin")
        self.arrays = {name: self._map(name, typecode) for name, typecode in ARRAYS.items()}
        self.count = len(self.arrays["parent.bin"])

    def _map(self, name: str, typecode: str | None = None):
        path = self.folder / name
        if path.stat().st_size == 0:
            return memoryview(b"").cast(typecode) if typecode else b""
        with open(path, "rb") as fh:
            mapped = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        self._maps.append(mapped)
        return memoryview(mapped).cast(typecode) if typecode else mapped

    def close(self) -> None:
        for view in self.arrays.values():
            if isinstance(view, memoryview):
                view.release()
        self.arrays = {}
        for mapped in self._maps:
            mapped.close()
        self._maps = []

    # -- entry access
    def name(self, i: int) -> str:
        off = self.arrays["names.off"]
        return bytes(self.names[off[i]: off[i + 1] - 1]).decode("utf-8", "surrogatepass")

    def lower_name(self, i: int) -> str:
        off = self.arrays["lower.off"]
        return bytes(self.lower[off[i]: off[i + 1] - 1]).decode("utf-8", "surrogatepass")

    def path(self, i: int) -> str:
        parent = self.arrays["parent.bin"]
        parts = []
        while i >= 0:
            parts.append(self.name(i))
            i = parent[i]
        parts.reverse()
        return os.path.join(*parts)

    def is_dir(self, i: int) -> bool:
        return bool(self.arrays["flags.bin"][i] & FLAG_DIR)

    # -- search
    def search(self, query: str, kind: str = "all", limit: int = 200) -> tuple[list[int], bool]:
        """Indexes of matching entries (ranked) and whether there were more."""
        words = query.lower().split()
        if not words:
            return [], False
        literals = [_longest_literal(w) for w in words]
        anchor = max(literals, key=len)
        patterns = [w for w in words if "*" in w or "?" in w]
        substrings = [w for w in words if w not in patterns]

        def matches(i: int) -> bool:
            if self.arrays["parent.bin"][i] < 0:
                return False  # drive roots themselves
            if kind != "all" and self.is_dir(i) != (kind == "dir"):
                return False
            name = self.lower_name(i)
            return all(s in name for s in substrings) and all(fnmatch.fnmatchcase(name, p) for p in patterns)

        found: list[int] = []
        for i in self._candidates(anchor):
            if matches(i):
                found.append(i)
                if len(found) > CANDIDATE_LIMIT:
                    break
        more = len(found) > CANDIDATE_LIMIT or len(found) > limit
        found = found[:CANDIDATE_LIMIT]

        def rank(i: int):
            name = self.lower_name(i)
            stem = name.rsplit(".", 1)[0]
            exact = name == query.lower().strip() or stem == query.lower().strip()
            return (not exact, not name.startswith(words[0].strip("*?")), len(name), i)

        found.sort(key=rank)
        return found[:limit], more

    def _candidates(self, literal: str):
        """Entry indexes whose lowercased name contains ``literal`` (all if empty)."""
        if not literal:
            yield from range(self.count)
            return
        needle = literal.encode("utf-8", "surrogatepass")
        off = self.arrays["lower.off"]
        blob = self.lower
        pos = blob.find(needle)
        while pos != -1:
            i = bisect_right(off, pos) - 1
            yield i
            pos = blob.find(needle, off[i + 1])


def _longest_literal(word: str) -> str:
    pieces = word.replace("?", "*").split("*")
    return max(pieces, key=len)


# ---------------------------------------------------------------------- manager
class IndexManager:
    """Owns the on-disk index: builds a new one next to the old and swaps."""

    def __init__(self, base: Path, roots_provider=local_drive_roots, workers: int = DEFAULT_WORKERS) -> None:
        self.base = Path(base)
        self.roots_provider = roots_provider
        self.workers = workers
        self._lock = threading.RLock()
        self.build: IndexBuild | None = None
        self.reader: IndexReader | None = None
        self._open_current()

    @property
    def current_dir(self) -> Path:
        return self.base / "index"

    def _open_current(self) -> None:
        if (self.current_dir / "meta.json").exists():
            try:
                self.reader = IndexReader(self.current_dir)
            except Exception:  # noqa: BLE001 - broken/old index: behave as if none
                log.exception("could not open index")
                self.reader = None

    def start(self) -> IndexBuild:
        with self._lock:
            if self.build is not None and not self.build.finished:
                raise IndexBusyError()
            roots = self.roots_provider()
            if not roots:
                raise ValueError("no local drives found")
            build = IndexBuild(roots, self.base / "index.new", self.workers)
            self.build = build
        threading.Thread(target=self._run, args=(build,), daemon=True, name="sizeseeker-index").start()
        return build

    def _run(self, build: IndexBuild) -> None:
        build.run()
        if build.state != "done":
            shutil.rmtree(build.target, ignore_errors=True)
            return
        with self._lock:
            if self.reader is not None:
                self.reader.close()  # Windows cannot replace mapped files
                self.reader = None
            old = self.base / "index.old"
            shutil.rmtree(old, ignore_errors=True)
            if self.current_dir.exists():
                self.current_dir.rename(old)
            build.target.rename(self.current_dir)
            shutil.rmtree(old, ignore_errors=True)
            self._open_current()

    def cancel(self) -> bool:
        build = self.build
        if build is None or build.finished:
            return False
        build.cancel()
        return True

    def wait(self, timeout: float = 60) -> None:
        deadline = time.time() + timeout
        while self.build is not None and not self.build.finished and time.time() < deadline:
            time.sleep(0.02)
        # the swap happens right after the build finished
        while time.time() < deadline:
            with self._lock:
                if self.build is None or self.build.state != "done" or (
                    self.reader is not None and self.reader.meta.get("created_at") == self.build.finished_at
                ):
                    return
            time.sleep(0.02)

    def info(self) -> dict | None:
        with self._lock:
            if self.reader is None:
                return None
            m = self.reader.meta
            return {k: m.get(k) for k in ("roots", "entries", "dirs", "errors", "created_at", "duration")}

    def status(self) -> dict:
        return {
            "index": self.info(),
            "build": self.build.status() if self.build else None,
            "roots": self.roots_provider(),
        }

    def search(self, query: str, kind: str, limit: int) -> dict:
        with self._lock:
            reader = self.reader
            if reader is None:
                raise NotIndexedError()
            ids, more = reader.search(query, kind, limit)
            results = [
                {"path": reader.path(i), "name": reader.name(i), "dir": reader.is_dir(i), "size": reader.arrays["size.bin"][i]}
                for i in ids
            ]
        return {"results": results, "more": more}

    def close(self) -> None:
        with self._lock:
            if self.reader is not None:
                self.reader.close()
                self.reader = None


class IndexBusyError(RuntimeError):
    """Indexing is already running."""


class NotIndexedError(RuntimeError):
    """No index has been built yet."""
