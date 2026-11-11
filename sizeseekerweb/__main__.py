"""Starts the local server, opens the browser and shows the tray icon."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from . import __version__
from .system import data_dir

DEFAULT_PORT = 38765
HOST = "127.0.0.1"  # never reachable from the network

log = logging.getLogger("sizeseekerweb")


def setup_logging(to_console: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            data_dir() / "sizeseekerweb.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    ]
    if to_console and sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers
    )


def running_instance(port: int) -> bool:
    """True if SizeSeekerWeb already answers on this port."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/version", timeout=1.5) as r:
            return json.load(r).get("app") == "SizeSeekerWeb"
    except Exception:  # noqa: BLE001
        return False


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def show_error(text: str) -> None:
    log.error(text)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "SizeSeekerWeb", 0x10)
    elif sys.stderr is not None:
        print(text, file=sys.stderr)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sizeseekerweb", description="Local disk usage analyzer in your browser.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SIZESEEKERWEB_PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser on start")
    parser.add_argument("--no-tray", action="store_true", help="no tray icon; stop with Ctrl+C")
    parser.add_argument("--version", action="version", version=f"SizeSeekerWeb {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(to_console=args.no_tray)
    url = f"http://{HOST}:{args.port}/"

    if running_instance(args.port):
        log.info("already running, opening %s", url)
        webbrowser.open(url)
        return 0
    if not port_free(args.port):
        show_error(f"Port {args.port} is used by another program.\nStart with --port <number> or set SIZESEEKERWEB_PORT.")
        return 1

    import uvicorn

    from .app import create_app, scan_on_start

    app = create_app(args.port)
    config = uvicorn.Config(app, host=HOST, port=args.port, log_config=None, access_log=False, lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="sizeseeker-server", daemon=True)
    thread.start()

    deadline = time.time() + 15
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        show_error("SizeSeekerWeb could not start the local server. See sizeseekerweb.log for details.")
        return 1
    log.info("SizeSeekerWeb %s listening on %s", __version__, url)
    if scan_on_start(app):
        log.info("scanning all drives on start")

    if not args.no_browser:
        webbrowser.open(url)

    if args.no_tray:
        try:
            while thread.is_alive():
                thread.join(0.5)
        except KeyboardInterrupt:
            pass
    else:
        from .tray import run_tray

        run_tray(url)  # blocks until "Quit"

    server.should_exit = True
    thread.join(10)
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
