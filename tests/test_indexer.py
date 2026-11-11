import os
import sys

import pytest

from sizeseekerweb.indexer import (
    CANDIDATE_LIMIT,
    IndexBuild,
    IndexBusyError,
    IndexManager,
    NotIndexedError,
    is_indexable,
    local_drive_roots,
)
from sizeseekerweb.scanner import BIG_FILE_THRESHOLD

from .conftest import make_junction, write

MB = BIG_FILE_THRESHOLD


def build(tmp_path, root) -> IndexManager:
    manager = IndexManager(tmp_path / "data", roots_provider=lambda: [str(root)], workers=4)
    manager.start()
    manager.wait()
    assert manager.build.state == "done", manager.build.error_message
    return manager


def names(result) -> list[str]:
    return sorted(r["name"] for r in result["results"])


def test_index_counts_every_folder_and_file(tmp_path, tree):
    m = build(tmp_path, tree)
    info = m.info()
    assert info["entries"] == 10  # the root + 9 folders/files of the fixture
    assert info["dirs"] == 4
    assert info["roots"] == [str(tree)]
    assert info["errors"] == 0


def test_paths_and_sizes(tmp_path, tree):
    m = build(tmp_path, tree)
    [hit] = m.search("huge", "all", 10)["results"]
    assert hit == {"path": str(tree / "docs" / "deep" / "huge.iso"), "name": "huge.iso", "dir": False, "size": 3 * MB}
    [docs] = m.search("docs", "all", 10)["results"]
    assert docs["dir"] is True
    assert docs["size"] == 5 * MB + 15  # folder size = whole subtree


def test_all_words_must_match(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("big bin", "all", 10)) == ["big.bin"]
    assert names(m.search("big txt", "all", 10)) == []


def test_search_ignores_case_but_returns_original_names(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("PIC", "all", 10)) == ["pic.PNG"]


def test_wildcards_must_match_the_whole_name(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("*.txt", "all", 10)) == ["a.txt", "note.txt", "x.txt"]
    assert names(m.search("?.TXT", "all", 10)) == ["a.txt", "x.txt"]
    assert names(m.search("n*e.txt", "all", 10)) == ["note.txt"]
    assert names(m.search("*.tx", "all", 10)) == []  # no implicit trailing *
    assert names(m.search("* bin", "all", 10)) == ["big.bin"]


def test_kind_filter(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("e", "dir", 10)) == ["deep", "empty"]
    assert names(m.search("e", "file", 10)) == ["huge.iso", "note.txt"]


def test_roots_are_not_results(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("root", "all", 10)) == []


def test_limit_and_more_flag(tmp_path):
    root = tmp_path / "many"
    for i in range(30):
        write(root / f"file{i:02}.log", 1)
    m = build(tmp_path, root)
    result = m.search("file", "all", 10)
    assert len(result["results"]) == 10 and result["more"] is True
    result = m.search("file", "all", 30)
    assert len(result["results"]) == 30 and result["more"] is False


def test_ranking_prefers_exact_and_prefix_matches(tmp_path):
    root = tmp_path / "rank"
    write(root / "my-report-final.pdf", 1)
    write(root / "report.pdf", 1)
    write(root / "reports-2024" / "x.txt", 1)
    m = build(tmp_path, root)
    assert [r["name"] for r in m.search("report", "all", 10)["results"]] == [
        "report.pdf", "reports-2024", "my-report-final.pdf"]


def test_unicode_names(tmp_path):
    root = tmp_path / "uni"
    write(root / "Übersicht Größe.txt", 1)
    m = build(tmp_path, root)
    assert names(m.search("übersicht größe", "all", 10)) == ["Übersicht Größe.txt"]
    assert names(m.search("ÜBERSICHT", "all", 10)) == ["Übersicht Größe.txt"]


def test_index_survives_a_restart(tmp_path, tree):
    build(tmp_path, tree).close()
    reopened = IndexManager(tmp_path / "data", roots_provider=lambda: [str(tree)])
    assert names(reopened.search("huge", "all", 10)) == ["huge.iso"]
    reopened.close()


def test_reindex_replaces_the_old_index(tmp_path, tree):
    m = build(tmp_path, tree)
    assert names(m.search("fresh", "all", 10)) == []
    write(tree / "fresh.txt", 3)
    m.start()
    m.wait()
    assert names(m.search("fresh", "all", 10)) == ["fresh.txt"]
    assert not (tmp_path / "data" / "index.new").exists()
    assert not (tmp_path / "data" / "index.old").exists()
    m.close()


def test_cancel_keeps_the_old_index(tmp_path, tree):
    m = build(tmp_path, tree)
    b = IndexBuild([str(tree)], tmp_path / "data" / "index.new", workers=1)
    b.cancel()
    b.run()
    assert b.state == "cancelled"
    assert names(m.search("huge", "all", 10)) == ["huge.iso"]


def test_search_without_index(tmp_path, tree):
    m = IndexManager(tmp_path / "data", roots_provider=lambda: [str(tree)])
    with pytest.raises(NotIndexedError):
        m.search("x", "all", 10)
    assert m.info() is None


def test_only_one_build_at_a_time(tmp_path, tree, monkeypatch):
    m = IndexManager(tmp_path / "data", roots_provider=lambda: [str(tree)])
    monkeypatch.setattr(IndexBuild, "run", lambda self: None)  # stays "pending"
    m.start()
    with pytest.raises(IndexBusyError):
        m.start()


def test_links_are_not_followed(tmp_path, tree):
    outside = tmp_path / "outside"
    write(outside / "secret-far.bin", 1)
    if not make_junction(tree / "link", outside):
        pytest.skip("cannot create junction/symlink here")
    m = build(tmp_path, tree)
    assert names(m.search("secret", "all", 10)) == []
    assert names(m.search("link", "all", 10)) == []


def test_candidate_limit_stops_early(tmp_path):
    root = tmp_path / "huge"
    for i in range(CANDIDATE_LIMIT + 50):
        write(root / f"a{i}", 0)
    m = build(tmp_path, root)
    result = m.search("a", "all", 5)
    assert len(result["results"]) == 5 and result["more"] is True


@pytest.mark.parametrize(
    ("drive_type", "fs", "expected"),
    [
        (3, "NTFS", True),
        (3, "ReFS", True),
        (3, "exFAT", True),
        (3, "FAT32", False),  # how Google Drive for desktop shows up
        (2, "NTFS", False),  # removable (USB stick)
        (4, "NTFS", False),  # network share
        (5, "CDFS", False),  # optical
    ],
)
def test_which_drives_are_indexed(drive_type, fs, expected):
    assert is_indexable(drive_type, fs) is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive detection")
def test_local_drive_roots_are_fixed_ntfs_like_disks():
    from sizeseekerweb.system import list_drive_roots

    roots = local_drive_roots()
    assert set(roots) <= set(list_drive_roots())
    assert os.environ.get("SystemDrive", "C:") + "\\" in roots
