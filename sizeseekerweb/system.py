"""Operating-system helpers: drives, file types, revealing paths in Explorer."""

from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg", ".webp", ".heic", ".ico",
}


def data_dir() -> Path:
    """Per-user folder for logs and the search index (override: SIZESEEKERWEB_DATA)."""
    override = os.environ.get("SIZESEEKERWEB_DATA")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        path = Path(base) / "SizeSeekerWeb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_drive_roots() -> list[str]:
    if hasattr(os, "listdrives"):  # Windows, Python 3.12+
        try:
            return sorted(os.listdrives())
        except OSError:
            pass
    if os.name == "nt":
        return [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
    return ["/"]


def volume_label(root: str) -> str:
    if os.name != "nt":
        return ""
    import ctypes

    buf = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root), buf, len(buf), None, None, None, None, 0
    )
    return buf.value if ok else ""


def list_drives() -> list[dict]:
    drives = []
    for root in list_drive_roots():
        try:
            usage = shutil.disk_usage(root)
        except OSError:  # e.g. empty card reader or DVD drive
            continue
        drives.append(
            {
                "path": root,
                "label": volume_label(root),
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            }
        )
    return drives


def file_kind(name: str) -> str:
    return "image" if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS else "file"


def reveal_in_explorer(path: str) -> None:
    """Show ``path`` in Windows Explorer. Files are selected, never opened/executed."""
    if not os.path.isabs(path) or not os.path.exists(path):
        raise FileNotFoundError(path)
    path = os.path.normpath(path)
    if sys.platform != "win32":
        raise NotImplementedError("Explorer is only available on Windows")
    from . import foreground

    # '"' is not allowed in Windows paths, so quoting cannot be broken out of.
    if os.path.isdir(path):
        command, folder = f'explorer "{path}"', path
    else:
        command, folder = f'explorer /select,"{path}"', os.path.dirname(path)
    before = foreground.explorer_windows()
    subprocess.Popen(command)  # noqa: S603 - fixed program, validated path
    foreground.focus_explorer_async(before, folder)
