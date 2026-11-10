"""System tray icon with "Open" and "Quit"."""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ICON = Path(__file__).resolve().parent / "static" / "icon.png"


def _is_german() -> bool:
    if sys.platform == "win32":
        import ctypes

        return ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x07  # LANG_GERMAN
    import locale

    return (locale.getlocale()[0] or "").lower().startswith("de")


def run_tray(url: str) -> None:
    import pystray
    from PIL import Image

    german = _is_german()

    def open_ui(icon, item) -> None:  # noqa: ARG001
        webbrowser.open(url)

    def quit_app(icon, item) -> None:  # noqa: ARG001
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("SizeSeekerWeb öffnen" if german else "Open SizeSeekerWeb", open_ui, default=True),
        pystray.MenuItem("Beenden" if german else "Quit", quit_app),
    )
    icon = pystray.Icon("SizeSeekerWeb", Image.open(ICON), f"SizeSeekerWeb – {url}", menu)
    icon.run()
