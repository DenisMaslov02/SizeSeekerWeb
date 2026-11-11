"""Duplicate finder on top of the search index.

Analysis (automatic after indexing, reads no file contents)
    * Folders are duplicates when their *contents* match: every folder gets a
      signature built bottom-up from the names, sizes and signatures of
      everything inside it. A folder's own name does not count, so
      "Project" and "Project - Kopie" match. Size and number of entries must
      match as well.
    * Files are duplicates when name and size match.
    * Only items of at least ``min_size`` bytes; the recycle bin is skipped.
    * A group is left out when all its members lie inside an already listed
      duplicate folder, so a copied folder shows up once and not with all of
      its files.

Verification (on demand, per group)
    Reads the files and compares BLAKE2 checksums. Hard links (same file on
    disk under two names) are recognised and do not cost extra space.
"""

from __future__ import annotations

import array
import hashlib
import json
import logging
import os
import struct
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

FORMAT_VERSION = 2  # 2: BLAKE2 child hashes (1 had signature collisions)
MIN_SIZE = 1024 * 1024
MAX_GROUPS = 5000
EXCLUDED_DIR_NAMES = {b"$recycle.bin"}
MASK = 2**64 - 1
CHUNK = 1024 * 1024


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------- analysis
def analyze(reader, min_size: int = MIN_SIZE, cancel: threading.Event | None = None,
            progress=None, max_groups: int = MAX_GROUPS) -> dict:
    """Find duplicate groups in an :class:`~sizeseekerweb.indexer.IndexReader`."""
    parent = reader.arrays["parent.bin"]
    size = reader.arrays["size.bin"]
    flags = reader.arrays["flags.bin"]
    loff = reader.arrays["lower.off"]
    blob = reader.lower
    n = reader.count

    def check(i: int) -> None:
        if i % 65536 == 0:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if progress is not None:
                progress(i, n)

    # 1) recycle bin (parents always come before their children)
    excluded = bytearray(n)
    for i in range(n):
        check(i)
        p = parent[i]
        if p >= 0 and excluded[p]:
            excluded[i] = 1
        elif flags[i] & 1 and bytes(blob[loff[i]: loff[i + 1] - 1]) in EXCLUDED_DIR_NAMES:
            excluded[i] = 1

    # 2) content signatures and entry counts of all folders, bottom-up.
    # Children are combined by adding their hashes (order does not matter), so the
    # per-child hash must be a real one: Python's built-in tuple hash is nearly
    # linear and made "a 2 MB + c 1 MB" collide with "a 1 MB + c 2 MB".
    sig = array.array("Q", bytes(8 * n))
    count = array.array("I", bytes(4 * n))
    pack = struct.Struct("<BqQI").pack
    for i in range(n - 1, -1, -1):
        check(n - 1 - i)
        p = parent[i]
        if p < 0:
            continue
        name = bytes(blob[loff[i]: loff[i + 1] - 1])
        digest = hashlib.blake2b(pack(flags[i] & 1, size[i], sig[i], count[i]) + name, digest_size=8).digest()
        sig[p] = (sig[p] + int.from_bytes(digest, "little")) & MASK
        count[p] += 1 + count[i]

    # 3) candidate groups
    dir_keys: dict[tuple, list[int]] = {}
    file_keys: dict[tuple, list[int]] = {}
    for i in range(n):
        check(i)
        if parent[i] < 0 or excluded[i] or size[i] < min_size:
            continue
        if flags[i] & 1:
            if count[i]:
                dir_keys.setdefault((sig[i], size[i], count[i]), []).append(i)
        else:
            file_keys.setdefault((size[i], bytes(blob[loff[i]: loff[i + 1] - 1])), []).append(i)

    # 4) drop groups that live completely inside an already listed duplicate folder
    covered: set[int] = set()

    def inside_covered(i: int) -> bool:
        p = parent[i]
        while p >= 0:
            if p in covered:
                return True
            p = parent[p]
        return False

    groups = []
    dir_groups = sorted((ids for ids in dir_keys.values() if len(ids) > 1),
                        key=lambda ids: (-size[ids[0]], -count[ids[0]]))
    for ids in dir_groups:
        if all(inside_covered(i) for i in ids):
            continue
        covered.update(ids)
        groups.append(("dir", ids))
    for ids in file_keys.values():
        if len(ids) > 1 and not all(inside_covered(i) for i in ids):
            groups.append(("file", ids))

    result_groups = []
    for kind, ids in groups:
        s = size[ids[0]]
        result_groups.append({
            "kind": kind,
            "name": reader.name(ids[0]),
            "size": s,
            "entries": count[ids[0]] if kind == "dir" else None,
            "wasted": s * (len(ids) - 1),
            "members": sorted(reader.path(i) for i in ids),
        })
    result_groups.sort(key=lambda g: (-g["wasted"], g["name"].lower()))
    for number, g in enumerate(result_groups):
        g["id"] = number
    return {
        "version": FORMAT_VERSION,
        "min_size": min_size,
        "index_created_at": reader.meta.get("created_at"),
        "analyzed_at": time.time(),
        "total_groups": len(result_groups),
        "dir_groups": sum(g["kind"] == "dir" for g in result_groups),
        "file_groups": sum(g["kind"] == "file" for g in result_groups),
        "total_wasted": sum(g["wasted"] for g in result_groups),
        "truncated": len(result_groups) > max_groups,
        "groups": result_groups[:max_groups],
    }


# ---------------------------------------------------------------------- verification
def _walk_files(root: str) -> list[tuple[str, str, int]]:
    """(relative path, absolute path, size) of every file below ``root``; links are skipped."""
    files = []
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as it:
            for entry in it:
                if entry.is_symlink() or entry.is_junction():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                else:
                    files.append((os.path.relpath(entry.path, root).lower(), entry.path,
                                  entry.stat(follow_symlinks=False).st_size))
    files.sort()
    return files


class Verification:
    """Compares the contents of the members of one duplicate group."""

    def __init__(self, group: dict) -> None:
        self.group = group
        self.state = "pending"  # pending | running | done | cancelled | error
        self.error: str | None = None
        self.bytes_done = 0
        self.bytes_total = 0
        self.result: dict | None = None
        self._cancel = threading.Event()
        self._digests: dict[tuple[int, int], str] = {}  # (dev, inode) -> digest

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def finished(self) -> bool:
        return self.state in ("done", "cancelled", "error")

    def status(self) -> dict:
        return {"group": self.group["id"], "state": self.state, "error": self.error,
                "bytes_done": self.bytes_done, "bytes_total": self.bytes_total}

    def run(self) -> None:
        self.state = "running"
        try:
            self.result = self._verify_files() if self.group["kind"] == "file" else self._verify_dirs()
            self.result["verified_at"] = time.time()
            self.state = "done"
        except Cancelled:
            self.state = "cancelled"
        except Exception as exc:  # noqa: BLE001 - shown in the UI
            log.exception("verification failed")
            self.state = "error"
            self.error = str(exc)

    def _digest(self, path: str, st: os.stat_result) -> str:
        key = (st.st_dev, st.st_ino)
        if st.st_ino and key in self._digests:  # hard link: same data, read once
            return self._digests[key]
        h = hashlib.blake2b(digest_size=20)
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                if self._cancel.is_set():
                    raise Cancelled()
                h.update(chunk)
                self.bytes_done += len(chunk)
        digest = h.hexdigest()
        if st.st_ino:
            self._digests[key] = digest
        return digest

    def _clusters(self, digests: dict[str, str]) -> list[list[str]]:
        by_digest: dict[str, list[str]] = {}
        for path, digest in digests.items():
            by_digest.setdefault(digest, []).append(path)
        return sorted((sorted(paths) for paths in by_digest.values()), key=lambda c: (-len(c), c))

    def _outcome(self, clusters, missing, hardlinked, unreadable) -> dict:
        identical = [c for c in clusters if len(c) > 1]
        if not identical and (missing or unreadable):
            state = "unreadable" if unreadable else "missing"
        elif len(clusters) == 1 and not missing and not unreadable:
            state = "identical"
        elif identical:
            state = "partial"
        else:
            state = "different"
        return {"state": state, "clusters": clusters, "missing": sorted(missing),
                "unreadable": sorted(unreadable), "hardlinked": sorted(hardlinked)}

    def _verify_files(self) -> dict:
        members, missing, stats = self.group["members"], [], {}
        for path in members:
            try:
                stats[path] = os.stat(path)
            except OSError:
                missing.append(path)
        unique = {(st.st_dev, st.st_ino) if st.st_ino else path: st.st_size for path, st in stats.items()}
        self.bytes_total = sum(unique.values())  # hard links are read once
        inode_count: dict[tuple[int, int], int] = {}
        for st in stats.values():
            if st.st_ino:
                inode_count[(st.st_dev, st.st_ino)] = inode_count.get((st.st_dev, st.st_ino), 0) + 1
        hardlinked = [p for p, st in stats.items() if st.st_ino and inode_count[(st.st_dev, st.st_ino)] > 1]
        digests, unreadable = {}, []
        for path, st in stats.items():
            try:
                digests[path] = self._digest(path, st)
            except OSError:  # locked by Windows (e.g. hiberfil.sys) or no permission
                unreadable.append(path)
        return self._outcome(self._clusters(digests), missing, hardlinked, unreadable)

    def _verify_dirs(self) -> dict:
        trees, stats, missing, unreadable = {}, {}, [], []
        for root in self.group["members"]:
            if not os.path.isdir(root):
                missing.append(root)
                continue
            try:
                files = _walk_files(root)
                stats[root] = [os.stat(path) for _, path, _ in files]
                trees[root] = files
            except OSError:
                unreadable.append(root)
        unique = {}
        for root, files in trees.items():
            for (_, path, size), st in zip(files, stats[root]):
                unique[(st.st_dev, st.st_ino) if st.st_ino else path] = size
        self.bytes_total = sum(unique.values())  # hard links are read once
        digests, inodes = {}, {}
        for root, files in trees.items():
            h = hashlib.blake2b(digest_size=20)
            try:
                for (rel, path, _), st in zip(files, stats[root]):
                    h.update(rel.encode("utf-8", "surrogatepass") + b"\0" + self._digest(path, st).encode() + b"\n")
            except OSError:  # a locked or protected file somewhere inside
                unreadable.append(root)
                continue
            digests[root] = h.hexdigest()
            inodes[root] = {(st.st_dev, st.st_ino) for st in stats[root] if st.st_ino}
        # A folder whose files all are hard links into another member costs no extra space.
        hardlinked = [root for root, own in inodes.items() if own and trees[root]
                      and len(own) == len(trees[root])
                      and any(own == other for r, other in inodes.items() if r != root)]
        return self._outcome(self._clusters(digests), missing, hardlinked, unreadable)


# ---------------------------------------------------------------------- manager
class DuplicateStore:
    """Analysis result + verifications of the current index, persisted next to it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.data: dict | None = None
        self.verified: dict[int, dict] = {}
        self.folder: Path | None = None
        self.state = "none"  # none | analyzing | ready | error
        self.progress = 0.0
        self.error: str | None = None
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.verification: Verification | None = None

    # -- analysis lifecycle (driven by IndexManager)
    def attach(self, reader) -> None:
        """Use the duplicates of ``reader``'s index; analyse if not done yet."""
        self.stop()
        with self._lock:
            self.folder = reader.folder
            self.data, self.verified = None, {}
            self.error = None
            try:
                data = json.loads((self.folder / "duplicates.json").read_text(encoding="utf-8"))
                if data.get("version") == FORMAT_VERSION and data.get("index_created_at") == reader.meta.get("created_at"):
                    self.data = data
                    self.verified = {int(k): v for k, v in json.loads(
                        (self.folder / "verified.json").read_text(encoding="utf-8")).items()} \
                        if (self.folder / "verified.json").exists() else {}
                    self.state = "ready"
                    return
            except (OSError, ValueError):
                pass
            self.state = "analyzing"
            self.progress = 0.0
            self._cancel = threading.Event()
            self._thread = threading.Thread(target=self._analyze, args=(reader, self._cancel),
                                            daemon=True, name="sizeseeker-duplicates")
            self._thread.start()

    def detach(self) -> None:
        self.stop()
        with self._lock:
            self.folder, self.data, self.verified, self.state = None, None, {}, "none"

    def stop(self) -> None:
        """Stop a running analysis (before its index is closed)."""
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._cancel.set()
            thread.join(60)
        self._thread = None

    def wait(self, timeout: float = 60) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _analyze(self, reader, cancel: threading.Event) -> None:
        def progress(done: int, total: int) -> None:
            self.progress = done / max(total, 1)

        try:
            started = time.time()
            data = analyze(reader, cancel=cancel, progress=progress)
            data["duration"] = time.time() - started
            (reader.folder / "duplicates.json").write_text(json.dumps(data), encoding="utf-8")
            (reader.folder / "verified.json").unlink(missing_ok=True)
            with self._lock:
                if self.folder == reader.folder:  # attach() already reset old checks
                    self.data, self.state = data, "ready"
            log.info("duplicate analysis: %s groups in %.1fs", data["total_groups"], data["duration"])
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001 - shown in the UI
            log.exception("duplicate analysis failed")
            with self._lock:
                self.state, self.error = "error", str(exc)

    # -- queries
    def summary(self) -> dict:
        with self._lock:
            d = self.data
            base = {"state": self.state, "progress": round(self.progress, 3), "error": self.error}
            if d:
                base.update({k: d[k] for k in ("total_groups", "dir_groups", "file_groups", "total_wasted",
                                               "truncated", "min_size", "analyzed_at")})
            return base

    def groups(self, kind: str, query: str, offset: int, limit: int) -> dict:
        with self._lock:
            groups = (self.data or {}).get("groups", [])
            needle = query.lower().strip()
            selected = [g for g in groups
                        if (kind == "all" or g["kind"] == kind)
                        and (not needle or any(needle in m.lower() for m in g["members"]))]
            page = [dict(g, verified=self.verified.get(g["id"])) for g in selected[offset: offset + limit]]
            return {**self.summary(), "matching": len(selected), "groups": page}

    # -- verification
    def verify(self, group_id: int) -> Verification:
        with self._lock:
            if self.verification is not None and not self.verification.finished:
                raise VerifyBusyError()
            groups = (self.data or {}).get("groups", [])
            if not 0 <= group_id < len(groups):
                raise KeyError(group_id)
            job = Verification(groups[group_id])
            self.verification = job
            analysis = self.data  # group ids belong to this analysis

        def run() -> None:
            job.run()
            if job.state == "done":
                with self._lock:
                    if self.data is analysis and self.folder is not None:
                        self.verified[group_id] = job.result
                        (self.folder / "verified.json").write_text(json.dumps(self.verified), encoding="utf-8")

        threading.Thread(target=run, daemon=True, name="sizeseeker-verify").start()
        return job

    def verification_status(self) -> dict | None:
        job = self.verification
        return job.status() if job else None

    def wait_verification(self, timeout: float = 60) -> None:
        deadline = time.time() + timeout
        while self.verification is not None and time.time() < deadline:
            with self._lock:
                job = self.verification
                if job.finished and (job.state != "done" or job.group["id"] in self.verified
                                     or self.data is None):
                    return
            time.sleep(0.02)

    def cancel_verification(self) -> bool:
        job = self.verification
        if job is None or job.finished:
            return False
        job.cancel()
        return True


class VerifyBusyError(RuntimeError):
    """Another verification is running."""
