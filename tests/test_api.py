import os
from unittest import mock

from fastapi.testclient import TestClient

from sizeseekerweb.app import create_app
from sizeseekerweb.scanner import BIG_FILE_THRESHOLD

from .conftest import PORT, WRITE_HEADERS, scan_and_wait

MB = BIG_FILE_THRESHOLD


# ---------------------------------------------------------------- security
def test_foreign_host_header_is_rejected(manager):
    # DNS rebinding: evil.example resolves to 127.0.0.1, but the Host header gives it away.
    client = TestClient(create_app(PORT, manager), base_url=f"http://evil.example:{PORT}")
    assert client.get("/api/drives").status_code == 403
    assert client.get("/").status_code == 403


def test_wrong_port_in_host_is_rejected(manager):
    client = TestClient(create_app(PORT, manager), base_url="http://127.0.0.1:9999")
    assert client.get("/api/version").status_code == 403


def test_localhost_name_is_allowed(manager):
    client = TestClient(create_app(PORT, manager), base_url=f"http://localhost:{PORT}")
    assert client.get("/api/version").json()["app"] == "SizeSeekerWeb"


def test_write_requests_need_the_custom_header(client, tree):
    r = client.post("/api/scans", json={"path": str(tree)})
    assert r.status_code == 403
    assert client.app.state.manager.current is None


def test_write_requests_from_a_foreign_origin_are_rejected(client, tree):
    headers = {**WRITE_HEADERS, "Origin": "https://evil.example"}
    assert client.post("/api/scans", json={"path": str(tree)}, headers=headers).status_code == 403
    assert client.delete("/api/scans/current", headers=headers).status_code == 403


def test_cors_preflight_is_not_granted(client):
    r = client.options(
        "/api/scans",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers


# ---------------------------------------------------------------- API
def test_index_and_static_are_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "SizeSeekerWeb" in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200


def test_drives(client):
    drives = client.get("/api/drives").json()
    assert drives, "at least one drive expected"
    d = drives[0]
    assert d["total"] >= d["used"] >= 0 and d["free"] >= 0
    assert os.path.isabs(d["path"])


def test_relative_and_missing_paths_are_rejected(client, tree):
    assert client.get("/api/folder", params={"path": "relative/dir"}).status_code == 400
    assert client.get("/api/folder", params={"path": str(tree / "missing")}).status_code == 404
    r = client.post("/api/scans", json={"path": str(tree / "a.txt")}, headers=WRITE_HEADERS)
    assert r.status_code == 404


def test_folder_before_scan_lists_entries_without_dir_sizes(client, tree):
    data = client.get("/api/folder", params={"path": str(tree)}).json()
    assert data["scanned"] is False
    by_name = {e["name"]: e for e in data["entries"]}
    assert by_name["docs"]["kind"] == "dir" and by_name["docs"]["size"] is None
    assert by_name["a.txt"]["size"] == 100


def test_folder_after_scan(client, tree):
    scan_and_wait(client, tree)
    data = client.get("/api/folder", params={"path": str(tree)}).json()
    assert data["scanned"] is True
    assert data["size"] == 100 + 50 + 5 * MB + 15
    assert data["parent"] == str(tree.parent)
    by_name = {e["name"]: e for e in data["entries"]}
    assert set(by_name) == {"a.txt", "pic.PNG", "docs", "empty"}
    assert by_name["docs"]["size"] == 5 * MB + 15
    assert by_name["docs"]["files"] == 4
    assert by_name["pic.PNG"]["kind"] == "image"
    assert by_name["a.txt"]["kind"] == "file"
    assert by_name["empty"]["size"] == 0
    assert abs(sum(e["percent"] for e in data["entries"]) - 100) < 0.05
    assert by_name["docs"]["percent"] > 99


def test_drive_root_has_no_parent(client):
    root = os.path.abspath(os.sep)
    assert client.get("/api/folder", params={"path": root}).json()["parent"] is None


def test_largest(client, tree):
    r = client.get("/api/largest", params={"path": str(tree)})
    assert r.status_code == 409  # not scanned yet
    scan_and_wait(client, tree)
    files = client.get("/api/largest", params={"path": str(tree), "limit": 5}).json()
    assert [f["name"] for f in files] == ["huge.iso", "big.bin"]
    assert files[0]["size"] == 3 * MB


def test_second_scan_while_running_is_rejected(client, tree, monkeypatch):
    from sizeseekerweb.scanner import Scan

    monkeypatch.setattr(Scan, "start", lambda self: None)  # stays "pending"
    assert client.post("/api/scans", json={"path": str(tree)}, headers=WRITE_HEADERS).status_code == 202
    r = client.post("/api/scans", json={"path": str(tree)}, headers=WRITE_HEADERS)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "scan_running"


def test_cancel_without_scan(client):
    assert client.delete("/api/scans/current", headers=WRITE_HEADERS).json() == {"cancelled": False}
    assert client.get("/api/scans/current").json() is None


def test_reveal_selects_files_and_opens_folders(client, tree):
    with mock.patch("sizeseekerweb.system.sys.platform", "win32"), \
         mock.patch("sizeseekerweb.system.subprocess.Popen") as popen:
        r = client.post("/api/reveal", json={"path": str(tree / "a.txt")}, headers=WRITE_HEADERS)
        assert r.status_code == 200
        popen.assert_called_once_with(f'explorer /select,"{tree / "a.txt"}"')
        popen.reset_mock()
        client.post("/api/reveal", json={"path": str(tree / "docs")}, headers=WRITE_HEADERS)
        popen.assert_called_once_with(f'explorer "{tree / "docs"}"')


def test_reveal_rejects_missing_and_relative_paths(client, tree):
    with mock.patch("sizeseekerweb.system.subprocess.Popen") as popen:
        for path in ["a.txt", str(tree / "missing.txt"), "/select,C:\\Windows"]:
            r = client.post("/api/reveal", json={"path": path}, headers=WRITE_HEADERS)
            assert r.status_code == 404, path
        popen.assert_not_called()
