import json
import time

import pytest

from sizeseekerweb.app import scan_on_start
from sizeseekerweb.scanner import Scan, ScanBusyError, ScanManager
from sizeseekerweb.settings import Settings

from .conftest import WRITE_HEADERS, write


def make_roots(tmp_path, count: int) -> list[str]:
    roots = []
    for i in range(count):
        root = tmp_path / f"drive{i}"
        write(root / "dir" / f"file{i}.bin", 1000 * (i + 1))
        roots.append(str(root))
    return roots


def run_batch(manager, roots):
    batch = manager.start_batch(roots)
    for _ in range(3000):
        if batch.finished:
            break
        time.sleep(0.01)
    assert batch.state == "done", batch.status()
    return batch


def test_all_roots_are_scanned_and_kept(tmp_path):
    roots = make_roots(tmp_path, ScanManager.MAX_KEPT + 2)  # more than normal scans are kept
    manager = ScanManager(workers=2)
    run_batch(manager, roots)
    assert manager.scanned_roots() == roots
    for i, root in enumerate(roots):
        scan = manager.scan_for(root)
        assert scan is not None and scan.root.size == 1000 * (i + 1)


def test_a_finished_scan_is_kept_when_the_next_one_starts(tmp_path):
    a, b = make_roots(tmp_path, 2)
    manager = ScanManager(workers=2)
    manager.start(a).wait(30)
    manager.start(b).wait(30)  # nobody looked at a's result in between
    assert manager.scan_for(a) is not None
    assert manager.scan_for(b) is not None


def test_pinned_drive_scans_survive_many_folder_scans(tmp_path):
    roots = make_roots(tmp_path, 2)
    manager = ScanManager(workers=2)
    run_batch(manager, roots)
    folders = make_roots(tmp_path / "more", ScanManager.MAX_KEPT + 3)
    for folder in folders:
        manager.start(folder).wait(30)
    kept = manager.scanned_roots()
    assert roots[0] in kept and roots[1] in kept
    assert sum(f in kept for f in folders) == ScanManager.MAX_KEPT  # folder scans stay limited


def test_rescanning_a_drive_replaces_its_pinned_scan(tmp_path):
    roots = make_roots(tmp_path, 1)
    manager = ScanManager(workers=2)
    run_batch(manager, roots)
    first = manager.scan_for(roots[0])
    run_batch(manager, roots)
    assert manager.scan_for(roots[0]) is not first
    assert manager.scanned_roots() == roots


def test_cancel_stops_the_batch(tmp_path, monkeypatch):
    roots = make_roots(tmp_path, 3)
    manager = ScanManager(workers=1)
    started = []
    original = Scan.start

    def start_and_cancel(self):
        started.append(self.root_path)
        manager.batch.cancel()
        original(self)

    monkeypatch.setattr(Scan, "start", start_and_cancel)
    batch = manager.start_batch(roots)
    for _ in range(3000):
        if batch.finished:
            break
        time.sleep(0.01)
    assert batch.state == "cancelled"
    assert started == roots[:1]


def test_only_one_batch_at_a_time(tmp_path, monkeypatch):
    from sizeseekerweb.scanner import ScanBatch

    monkeypatch.setattr(ScanBatch, "run", lambda self: None)  # stays "pending"
    manager = ScanManager()
    manager.start_batch(make_roots(tmp_path, 1))
    with pytest.raises(ScanBusyError):
        manager.start_batch(make_roots(tmp_path / "x", 1))


def test_batch_waits_for_a_scan_the_user_started(tmp_path):
    a, b = make_roots(tmp_path, 2)
    manager = ScanManager(workers=1)
    user_scan = manager.start(b)
    batch = run_batch(manager, [a, b])
    assert user_scan.state == "done"
    assert batch.failed == []
    assert set(manager.scanned_roots()) == {a, b}


# ---------------------------------------------------------------- settings
def test_settings_default_and_persist(tmp_path):
    path = tmp_path / "data" / "settings.json"
    s = Settings(path)
    assert s.get("scan_on_start") is False
    s.update(scan_on_start=True)
    assert json.loads(path.read_text(encoding="utf-8"))["scan_on_start"] is True
    assert Settings(path).get("scan_on_start") is True


@pytest.mark.parametrize("content", ["not json", '{"scan_on_start": "yes"}', "[]"])
def test_broken_settings_fall_back_to_defaults(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert Settings(path).get("scan_on_start") is False


def test_settings_reject_unknown_keys_and_wrong_types(tmp_path):
    s = Settings(tmp_path / "settings.json")
    with pytest.raises(ValueError):
        s.update(evil=True)
    with pytest.raises(ValueError):
        s.update(scan_on_start=1)


# ---------------------------------------------------------------- API + start
def test_scan_all_api(client, tree):
    status = client.get("/api/scans/all").json()
    assert status["batch"] is None and status["scanned"] == [] and status["roots"] == [str(tree)]
    assert client.post("/api/scans/all").status_code == 403  # needs the header
    assert client.post("/api/scans/all", headers=WRITE_HEADERS).status_code == 202
    batch = client.app.state.manager.batch
    for _ in range(3000):
        if batch.finished:
            break
        time.sleep(0.01)
    status = client.get("/api/scans/all").json()
    assert status["batch"]["state"] == "done"
    assert status["scanned"] == [str(tree)]
    assert client.get("/api/folder", params={"path": str(tree)}).json()["scanned"] is True
    assert client.delete("/api/scans/all", headers=WRITE_HEADERS).json() == {"cancelled": False}


def test_settings_api(client):
    assert client.get("/api/settings").json() == {"scan_on_start": False}
    assert client.put("/api/settings", json={"scan_on_start": True}).status_code == 403
    r = client.put("/api/settings", json={"scan_on_start": True}, headers=WRITE_HEADERS)
    assert r.json() == {"scan_on_start": True}
    assert client.get("/api/settings").json() == {"scan_on_start": True}
    assert client.put("/api/settings", json={"scan_on_start": "yes"}, headers=WRITE_HEADERS).status_code == 422


def test_scan_on_start_follows_the_setting(client, tree):
    app = client.app
    assert scan_on_start(app) is False
    assert app.state.manager.batch is None
    app.state.settings.update(scan_on_start=True)
    assert scan_on_start(app) is True
    assert app.state.manager.batch.roots == [str(tree)]
