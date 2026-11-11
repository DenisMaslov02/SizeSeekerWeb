"""Bring the Explorer window that "Show in Explorer" opened to the front.

Windows does not let a background process (our server - the click happened in
the browser) put a window in front; the new Explorer window would open behind
the browser. We find that window and move it to the foreground by briefly
attaching to the input queue of the current foreground window, which is the
documented way to get past the foreground lock.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

log = logging.getLogger(__name__)

EXPLORER_CLASS = "CabinetWClass"
WAIT_SECONDS = 4.0
POLL_SECONDS = 0.05
SW_RESTORE = 9


def pick_window(before: dict[int, str], after: dict[int, str], folder: str) -> int | None:
    """The Explorer window showing ``folder``: a newly opened one if there is one,
    otherwise an existing window whose title is the folder (Explorer may reuse it)."""
    new = [hwnd for hwnd in after if hwnd not in before]
    if new:
        return new[-1]
    folder = os.path.normpath(folder)
    names = {folder.lower(), (os.path.basename(folder.rstrip("\\/")) or folder).lower()}
    for hwnd, title in after.items():
        # Windows 11 titles look like "packaging – Datei-Explorer" / "packaging - File Explorer".
        shown = title.lower()
        if any(shown == n or shown.startswith(n + " ") for n in names):
            return hwnd
    return None


def explorer_windows() -> dict[int, str]:
    """Visible Explorer windows: {hwnd: title}."""
    if sys.platform != "win32":
        return {}
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: dict[int, str] = {}
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == EXPLORER_CLASS and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            found[int(hwnd)] = title.value
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return found


def bring_to_front(hwnd: int) -> bool:
    """Make ``hwnd`` the foreground window. True if it worked."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    for fn in (user32.SetForegroundWindow, user32.BringWindowToTop, user32.IsIconic):
        fn.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    def is_front() -> bool:
        fg = user32.GetForegroundWindow()
        return fg is not None and int(fg) == hwnd

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.SetForegroundWindow(hwnd) and is_front():
        return True

    # Foreground lock: share the input queue of the current foreground thread for a moment.
    msg = wintypes.MSG()
    user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # a thread needs a message queue to attach
    own = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other) and other != own and user32.AttachThreadInput(own, other, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(own, other, False)
    return is_front()


def focus_explorer_async(before: dict[int, str], folder: str) -> None:
    """Wait for the Explorer window for ``folder`` in the background and bring it to front."""

    def run() -> None:
        deadline = time.monotonic() + WAIT_SECONDS
        hwnd = None
        while time.monotonic() < deadline:
            after = explorer_windows()
            new = [h for h in after if h not in before]
            if new:
                hwnd = pick_window(before, after, folder)
                break
            time.sleep(POLL_SECONDS)
        if hwnd is None:  # Explorer reused a window that was already open
            hwnd = pick_window(before, explorer_windows(), folder)
        if hwnd is None:
            log.info("no Explorer window found for %s", folder)
            return
        time.sleep(0.15)  # let Explorer finish showing the window
        if not bring_to_front(hwnd):
            log.info("could not bring Explorer to the front")

    threading.Thread(target=run, name="sizeseeker-explorer-focus", daemon=True).start()
