"""User settings stored as JSON in the data folder."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {"scan_on_start": False}


class Settings:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._values = dict(DEFAULTS)
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("settings must be an object")
            for key, default in DEFAULTS.items():
                if isinstance(stored.get(key), type(default)):
                    self._values[key] = stored[key]
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.warning("ignoring unreadable settings file %s", self.path)

    def get(self, key: str):
        with self._lock:
            return self._values[key]

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._values)

    def update(self, **changes) -> dict:
        with self._lock:
            for key, value in changes.items():
                if key not in DEFAULTS or not isinstance(value, type(DEFAULTS[key])):
                    raise ValueError(key)
            self._values.update(changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._values, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return dict(self._values)
