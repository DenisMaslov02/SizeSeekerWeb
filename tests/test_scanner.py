import os

import pytest

from sizeseekerweb.scanner import BIG_FILE_THRESHOLD, Scan, ScanBusyError, ScanManager

from .conftest import make_junction, write

MB = BIG_FILE_THRESHOLD
TOTAL = 100 + 50 + 2 * MB + 10 + 3 * MB + 5


def run_scan(path, workers=4) -> Scan:
    scan = Scan(str(path), workers)
    scan.run()
    assert scan.state == "done", scan.error_message
    return scan


@pytest.mark.parametrize("workers", [1, 4])
def test_sizes_are_aggregated_over_the_whole_subtree(tree, workers):
    scan = run_scan(tree, workers)
    assert scan.root.size == TOTAL
    assert scan.root.files == 6
    assert scan.root.dirs == 3  # docs, docs/deep, empty
    docs = scan.find(str(tree / "docs"))
    assert docs.size == 2 * MB + 10 + 3 * MB + 5
    assert docs.files == 4
    assert scan.find(str(tree / "docs" / "deep")).size == 3 * MB + 5
    assert scan.find(str(tree / "empty")).size == 0


def test_progress_counts_everything(tree):
    scan = run_scan(tree)
    status = scan.status()
    assert status["progress"]["dirs"] == 4
    assert status["progress"]["files"] == 6
    assert status["progress"]["bytes"] == TOTAL
    assert status["errors"] == 0


def test_find_is_case_insensitive_on_windows(tree):
    scan = run_scan(tree)
    node = scan.find(str(tree / "DOCS" / "Deep"))
    if os.name == "nt":
        assert node is not None and node.name == "deep"
    else:
        assert node is None


def test_find_outside_the_scan_returns_none(tree, tmp_path):
    scan = run_scan(tree / "docs")
    assert scan.find(str(tree)) is None
    assert scan.find(str(tmp_path / "other")) is None
    assert scan.find(str(tree / "docs" / "missing")) is None
    assert scan.covers(str(tree / "docs" / "deep"))
    assert not scan.covers(str(tree / "docsextra"))


def test_largest_files_are_sorted_and_limited(tree):
    scan = run_scan(tree)
    assert scan.largest_files(str(tree), 10) == [
        (3 * MB, str(tree / "docs" / "deep" / "huge.iso")),
        (2 * MB, str(tree / "docs" / "big.bin")),
    ]
    assert scan.largest_files(str(tree), 1) == [(3 * MB, str(tree / "docs" / "deep" / "huge.iso"))]
    assert scan.largest_files(str(tree / "docs" / "deep"), 10) == [
        (3 * MB, str(tree / "docs" / "deep" / "huge.iso"))
    ]


def test_links_and_junctions_are_not_followed(tree, tmp_path):
    outside = tmp_path / "outside"
    write(outside / "far.bin", 4 * MB)
    if not make_junction(tree / "link", outside):
        pytest.skip("cannot create junction/symlink here")
    scan = run_scan(tree)
    assert scan.root.size == TOTAL
    assert scan.find(str(tree / "link")) is None


def test_missing_root_is_an_error(tmp_path):
    scan = Scan(str(tmp_path / "nope"))
    scan.run()
    assert scan.state == "error"


def test_cancel_stops_the_scan(tmp_path):
    for i in range(50):
        write(tmp_path / f"d{i}" / "f.txt", 1)
    scan = Scan(str(tmp_path), workers=1)
    scan.cancel()
    scan.run()
    assert scan.state == "cancelled"


def test_manager_allows_only_one_running_scan(tree, monkeypatch):
    manager = ScanManager(workers=1)
    started = []
    monkeypatch.setattr(Scan, "start", lambda self: started.append(self))  # never runs
    manager.start(str(tree))
    with pytest.raises(ScanBusyError):
        manager.start(str(tree))
    assert len(started) == 1


def test_manager_prefers_the_newest_covering_scan(tree):
    manager = ScanManager(workers=2)
    first = manager.start(str(tree))
    first.wait(30)
    assert manager.scan_for(str(tree / "docs")) is first

    write(tree / "docs" / "new.bin", 7)
    second = manager.start(str(tree / "docs"))
    second.wait(30)
    assert manager.scan_for(str(tree / "docs")) is second
    assert manager.scan_for(str(tree)) is first  # the sub-scan does not cover the root


def test_manager_drops_scans_inside_a_newer_scan(tree):
    manager = ScanManager(workers=2)
    inner = manager.start(str(tree / "docs"))
    inner.wait(30)
    assert manager.scan_for(str(tree / "docs")) is inner
    outer = manager.start(str(tree))
    outer.wait(30)
    assert manager.scan_for(str(tree / "docs")) is outer
    assert inner not in manager._done


def test_leaf_directories_share_empty_containers(tree):
    scan = run_scan(tree)
    empty = scan.find(str(tree / "empty"))
    deep = scan.find(str(tree / "docs" / "deep"))
    assert len(empty.children) == 0 and empty.big_files == ()
    assert empty.children is deep.children  # one shared object, no per-node dict
