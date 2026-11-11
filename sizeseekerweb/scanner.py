"""Background directory scanner.

A scan walks a directory tree once and keeps an in-memory tree of *directories*
with their aggregated sizes. Individual files are not kept (that would cost far
too much memory for a whole drive) - only files of at least
``BIG_FILE_THRESHOLD`` bytes are remembered per directory, so that the
"largest files" view works without a second walk.

Symlinks and junctions are not followed, so nothing is counted twice through a
link and the scan cannot loop.
"""

from __future__ import annotations

import heapq
import logging
import os
import queue
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

log = logging.getLogger(__name__)

_NO_CHILDREN: Mapping[str, "DirNode"] = MappingProxyType({})

BIG_FILE_THRESHOLD = 1024 * 1024  # 1 MiB
DEFAULT_WORKERS = min(16, (os.cpu_count() or 4) * 2)


def norm_key(name: str) -> str:
    """Key for name lookups (case-insensitive on Windows)."""
    return os.path.normcase(name)


def normalize_path(path: str) -> str:
    """Absolute, normalized path. A drive root keeps its trailing separator."""
    return os.path.abspath(path)


class DirNode:
    """One scanned directory. Sizes are final once the scan is ``done``."""

    __slots__ = (
        "name",
        "parent",
        "children",
        "own_size",
        "own_files",
        "size",
        "files",
        "dirs",
        "big_files",
        "error",
        "errors",
    )

    def __init__(self, name: str, parent: "DirNode | None") -> None:
        self.name = name
        self.parent = parent
        # Shared empty defaults: most directories are leaves, and a dict/list per
        # node would cost ~100 bytes each on drives with hundreds of thousands of folders.
        self.children: Mapping[str, DirNode] = _NO_CHILDREN
        self.own_size = 0  # direct files only
        self.own_files = 0
        self.size = 0  # whole subtree
        self.files = 0
        self.dirs = 0
        self.big_files: tuple[tuple[int, str], ...] = ()  # (size, file name), direct files
        self.error = False  # this directory could not be read (completely)
        self.errors = 0  # unreadable directories in the subtree, including this one


@dataclass
class ScanProgress:
    dirs: int = 0
    files: int = 0
    bytes: int = 0
    current: str = ""


class Scan:
    """A single scan of ``root_path``. Run it with :meth:`start` or :meth:`run`."""

    def __init__(self, root_path: str, workers: int = DEFAULT_WORKERS) -> None:
        self.root_path = normalize_path(root_path)
        self.workers = max(1, workers)
        self.root = DirNode(self.root_path, None)
        self.state = "pending"  # pending | running | done | cancelled | error
        self.error_message: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.progress = ScanProgress()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="sizeseeker-scan", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is None:
            return self.state in ("done", "cancelled", "error")
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def finished(self) -> bool:
        return self.state in ("done", "cancelled", "error")

    def run(self) -> None:
        self.state = "running"
        self.started_at = time.time()
        try:
            if not os.path.isdir(self.root_path):
                raise NotADirectoryError(self.root_path)
            self._walk()
            if self._cancel.is_set():
                self.state = "cancelled"
            else:
                _aggregate(self.root)
                self.state = "done"
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            log.exception("scan of %s failed", self.root_path)
            self.state = "error"
            self.error_message = str(exc)
        finally:
            self.finished_at = time.time()

    # ------------------------------------------------------------------ walking
    def _walk(self) -> None:
        work: queue.Queue[tuple[DirNode, str] | None] = queue.Queue()
        work.put((self.root, self.root_path))

        def worker() -> None:
            while True:
                item = work.get()
                try:
                    if item is None:
                        return
                    if not self._cancel.is_set():
                        for sub in self._scan_dir(*item):
                            work.put(sub)
                finally:
                    work.task_done()

        threads = [
            threading.Thread(target=worker, name=f"sizeseeker-worker-{i}", daemon=True)
            for i in range(self.workers)
        ]
        for t in threads:
            t.start()
        work.join()
        for _ in threads:
            work.put(None)
        for t in threads:
            t.join()

    def _scan_dir(self, node: DirNode, path: str) -> list[tuple[DirNode, str]]:
        subdirs: list[tuple[DirNode, str]] = []
        big_files: list[tuple[int, str]] = []
        own_size = 0
        own_files = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._cancel.is_set():
                        break
                    try:
                        if entry.is_symlink() or entry.is_junction():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            subdirs.append((DirNode(entry.name, node), entry.path))
                            continue
                        size = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        node.error = True
                        continue
                    own_size += size
                    own_files += 1
                    if size >= BIG_FILE_THRESHOLD:
                        big_files.append((size, entry.name))
        except OSError:
            node.error = True

        node.own_size = own_size
        node.own_files = own_files
        if big_files:
            node.big_files = tuple(big_files)
        if subdirs:
            node.children = {norm_key(child.name): child for child, _ in subdirs}
        with self._lock:
            self.progress.dirs += 1
            self.progress.files += own_files
            self.progress.bytes += own_size
            self.progress.current = path
        return subdirs

    # ------------------------------------------------------------------ queries
    def covers(self, path: str) -> bool:
        path = normalize_path(path)
        try:
            common = os.path.commonpath([norm_key(self.root_path), norm_key(path)])
        except ValueError:  # different drives
            return False
        return common == norm_key(self.root_path)

    def find(self, path: str) -> DirNode | None:
        """Node for ``path`` (must be inside the scanned tree), or ``None``."""
        path = normalize_path(path)
        if not self.covers(path):
            return None
        rel = os.path.relpath(path, self.root_path)
        node = self.root
        if rel == os.curdir:
            return node
        for part in rel.split(os.sep):
            child = node.children.get(norm_key(part))
            if child is None:
                return None
            node = child
        return node

    def largest_files(self, path: str, limit: int) -> list[tuple[int, str]]:
        """Largest files (>= BIG_FILE_THRESHOLD) below ``path``: [(size, full path)]."""
        start = self.find(path)
        if start is None:
            return []
        heap: list[tuple[int, str]] = []
        for dir_path, node in _iter_with_paths(start, normalize_path(path)):
            for size, name in node.big_files:
                item = (size, os.path.join(dir_path, name))
                if len(heap) < limit:
                    heapq.heappush(heap, item)
                elif item > heap[0]:
                    heapq.heapreplace(heap, item)
        return sorted(heap, reverse=True)

    def status(self) -> dict:
        with self._lock:
            progress = {
                "dirs": self.progress.dirs,
                "files": self.progress.files,
                "bytes": self.progress.bytes,
                "current": self.progress.current,
            }
        return {
            "root": self.root_path,
            "state": self.state,
            "error": self.error_message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": progress,
            "errors": self.root.errors if self.state == "done" else None,
        }


def _iter_with_paths(node: DirNode, path: str) -> Iterator[tuple[str, DirNode]]:
    stack = [(path, node)]
    while stack:
        p, n = stack.pop()
        yield p, n
        stack.extend((os.path.join(p, c.name), c) for c in n.children.values())


def _aggregate(root: DirNode) -> None:
    """Compute subtree totals bottom-up (iterative: trees can be very deep)."""
    order: list[DirNode] = []
    stack = [root]
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(node.children.values())
    for node in reversed(order):
        size, files, dirs, errors = node.own_size, node.own_files, 0, int(node.error)
        for child in node.children.values():
            size += child.size
            files += child.files
            dirs += 1 + child.dirs
            errors += child.errors
        node.size, node.files, node.dirs, node.errors = size, files, dirs, errors


class ScanManager:
    """Runs one scan at a time and keeps finished scans for browsing."""

    # A fully scanned system drive needs roughly 150-200 MB, so keep only a few.
    MAX_KEPT = 4

    def __init__(self, workers: int = DEFAULT_WORKERS) -> None:
        self.workers = workers
        self._lock = threading.Lock()
        self.current: Scan | None = None
        self._done: list[Scan] = []

    def start(self, path: str) -> Scan:
        with self._lock:
            if self.current is not None and not self.current.finished:
                raise ScanBusyError(self.current.root_path)
            scan = Scan(path, self.workers)
            self.current = scan
        scan.start()
        return scan

    def cancel(self) -> bool:
        with self._lock:
            scan = self.current
        if scan is None or scan.finished:
            return False
        scan.cancel()
        return True

    def _collect(self) -> None:
        scan = self.current
        if scan is not None and scan.state == "done" and scan not in self._done:
            # Older scans that lie completely inside the new one are outdated.
            self._done = [s for s in self._done if not scan.covers(s.root_path)]
            self._done.append(scan)
            del self._done[: -self.MAX_KEPT]

    def scan_for(self, path: str) -> Scan | None:
        """Most recently finished scan that contains ``path``."""
        with self._lock:
            self._collect()
            candidates = [s for s in self._done if s.covers(path) and s.find(path) is not None]
        # _done is in completion order (scans run one at a time). Timestamps are
        # not used: on Windows two scans can finish within the same clock tick.
        return candidates[-1] if candidates else None


class ScanBusyError(RuntimeError):
    """A scan is already running."""
