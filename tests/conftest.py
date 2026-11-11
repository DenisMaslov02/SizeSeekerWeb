import os

import pytest
from fastapi.testclient import TestClient

from sizeseekerweb.app import create_app
from sizeseekerweb.indexer import IndexManager
from sizeseekerweb.scanner import BIG_FILE_THRESHOLD, ScanManager
from sizeseekerweb.settings import Settings

PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"
WRITE_HEADERS = {"X-SizeSeeker": "1"}


def write(path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.truncate(size)  # sparse where possible, st_size is what counts


@pytest.fixture
def tree(tmp_path):
    """
    root/
      a.txt              100
      pic.PNG            50
      docs/
        big.bin          BIG (2 MiB)
        note.txt         10
        deep/
          huge.iso       3 MiB
          x.txt          5
      empty/
    """
    root = tmp_path / "root"
    write(root / "a.txt", 100)
    write(root / "pic.PNG", 50)
    write(root / "docs" / "big.bin", 2 * BIG_FILE_THRESHOLD)
    write(root / "docs" / "note.txt", 10)
    write(root / "docs" / "deep" / "huge.iso", 3 * BIG_FILE_THRESHOLD)
    write(root / "docs" / "deep" / "x.txt", 5)
    (root / "empty").mkdir()
    return root


@pytest.fixture
def manager():
    return ScanManager(workers=4)


@pytest.fixture
def index(tmp_path):
    # Never the real %LOCALAPPDATA% or the real drives in tests.
    manager = IndexManager(tmp_path / "data", roots_provider=lambda: [str(tmp_path / "root")], workers=2)
    yield manager
    manager.close()


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "data" / "settings.json")


@pytest.fixture
def scan_roots(tmp_path):
    return lambda: [str(tmp_path / "root")]


@pytest.fixture
def client(manager, index, settings, scan_roots):
    return TestClient(create_app(PORT, manager, index, settings, scan_roots), base_url=BASE_URL)


def scan_and_wait(client, path) -> dict:
    r = client.post("/api/scans", json={"path": str(path)}, headers=WRITE_HEADERS)
    assert r.status_code == 202, r.text
    client.app.state.manager.current.wait(30)
    status = client.get("/api/scans/current").json()
    assert status["state"] == "done", status
    return status


def make_junction(link, target) -> bool:
    """Create a directory junction (Windows) or symlink. False if not possible."""
    if os.name == "nt":
        import subprocess

        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False
