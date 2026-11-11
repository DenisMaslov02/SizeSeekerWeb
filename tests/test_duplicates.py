import os

import pytest

from sizeseekerweb.duplicates import MIN_SIZE, VerifyBusyError
from sizeseekerweb.indexer import IndexManager

MB = MIN_SIZE


def put(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def blob(seed: int, size: int) -> bytes:
    return bytes([seed % 251]) * size


@pytest.fixture
def dup_tree(tmp_path):
    """
    root/
      A/            film.mp4 (2 MB), notes.txt, sub/big.bin (3 MB)
      A - Kopie/    identical copy of A           -> one folder group
      other/        film.mp4 (same as A's), different.mp4 (2 MB, other name)
      B/            film.mp4 (2 MB, other content) -> same name+size, differs on verify
      small/        tiny.txt + small2/tiny.txt (below 1 MB) -> ignored
      $Recycle.Bin/ film.mp4 (same as A's)        -> ignored
    """
    root = tmp_path / "root"
    for top in ("A", "A - Kopie"):
        put(root / top / "film.mp4", blob(1, 2 * MB))
        put(root / top / "notes.txt", b"hello")
        put(root / top / "sub" / "big.bin", blob(2, 3 * MB))
    put(root / "other" / "film.mp4", blob(1, 2 * MB))
    put(root / "other" / "different.mp4", blob(1, 2 * MB))
    put(root / "B" / "film.mp4", blob(9, 2 * MB))
    put(root / "small" / "tiny.txt", b"x" * 100)
    put(root / "small2" / "tiny.txt", b"x" * 100)
    put(root / "$Recycle.Bin" / "S-1" / "film.mp4", blob(1, 2 * MB))
    return root


def analysed(tmp_path, root) -> IndexManager:
    m = IndexManager(tmp_path / "data", roots_provider=lambda: [str(root)], workers=2)
    m.start()
    m.wait()
    m.duplicates.wait()
    assert m.duplicates.state == "ready", m.duplicates.error
    return m


def by_kind(m) -> dict:
    groups = m.duplicates.groups("all", "", 0, 100)["groups"]
    return {(g["kind"], g["name"]): g for g in groups}


def test_copied_folder_is_one_group_even_with_another_name(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    groups = by_kind(m)
    folder = [g for g in groups.values() if g["kind"] == "dir"]
    assert len(folder) == 1
    assert folder[0]["members"] == [str(dup_tree / "A"), str(dup_tree / "A - Kopie")]
    assert folder[0]["size"] == 5 * MB + 5
    assert folder[0]["entries"] == 4  # film.mp4, notes.txt, sub, sub/big.bin
    assert folder[0]["wasted"] == 5 * MB + 5


def test_files_inside_a_listed_folder_copy_are_not_repeated(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    names = {name for _, name in by_kind(m)}
    assert "big.bin" not in names  # only inside A and its copy
    assert "sub" not in names


def test_same_name_and_size_outside_the_copy_is_listed_with_all_members(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    film = by_kind(m)[("file", "film.mp4")]
    assert film["members"] == sorted(str(dup_tree / d / "film.mp4") for d in ("A", "A - Kopie", "B", "other"))
    assert film["wasted"] == 3 * 2 * MB


def test_small_files_other_names_and_recycle_bin_are_ignored(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    names = {name for _, name in by_kind(m)}
    assert "tiny.txt" not in names and "different.mp4" not in names
    film = by_kind(m)[("file", "film.mp4")]
    assert not any("$Recycle.Bin" in p for p in film["members"])


def test_summary_and_sorting(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    s = m.duplicates.summary()
    assert (s["total_groups"], s["dir_groups"], s["file_groups"]) == (2, 1, 1)
    assert s["total_wasted"] == (5 * MB + 5) + 6 * MB
    groups = m.duplicates.groups("all", "", 0, 10)["groups"]
    assert [g["wasted"] for g in groups] == sorted((g["wasted"] for g in groups), reverse=True)


def test_filters_and_paging(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    assert [g["kind"] for g in m.duplicates.groups("dir", "", 0, 10)["groups"]] == ["dir"]
    assert [g["kind"] for g in m.duplicates.groups("file", "", 0, 10)["groups"]] == ["file"]
    found = m.duplicates.groups("all", "kopie", 0, 10)
    assert found["matching"] == 2  # both groups have a member below "A - Kopie"
    assert m.duplicates.groups("all", "", 1, 10)["groups"][0]["id"] == 1


def verify(m, group) -> dict:
    m.duplicates.verify(group["id"])
    m.duplicates.wait_verification()
    status = m.duplicates.verification_status()
    assert status["state"] == "done", status
    return m.duplicates.groups("all", "", 0, 100)["groups"][group["id"]]["verified"]


def test_verify_identical_folder_copy(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    folder = by_kind(m)[("dir", "A")] if ("dir", "A") in by_kind(m) else by_kind(m)[("dir", "A - Kopie")]
    result = verify(m, folder)
    assert result["state"] == "identical"
    assert result["clusters"] == [[str(dup_tree / "A"), str(dup_tree / "A - Kopie")]]


def test_verify_finds_the_file_with_other_content(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    result = verify(m, by_kind(m)[("file", "film.mp4")])
    assert result["state"] == "partial"
    assert result["clusters"] == [
        sorted(str(dup_tree / d / "film.mp4") for d in ("A", "A - Kopie", "other")),
        [str(dup_tree / "B" / "film.mp4")],
    ]


def test_verify_detects_changed_folder_contents(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    folder = next(g for g in by_kind(m).values() if g["kind"] == "dir")
    put(dup_tree / "A - Kopie" / "notes.txt", b"HELLO")  # same size, other content
    assert verify(m, folder)["state"] == "different"


def test_verify_reports_missing_files(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    film = by_kind(m)[("file", "film.mp4")]
    os.remove(dup_tree / "other" / "film.mp4")
    result = verify(m, film)
    assert result["missing"] == [str(dup_tree / "other" / "film.mp4")]
    assert result["state"] == "partial"


def lock(monkeypatch, locked_path) -> None:
    """Simulate a file Windows keeps locked (like hiberfil.sys)."""
    import builtins

    from sizeseekerweb import duplicates

    def fake_open(path, *args, **kwargs):
        if os.path.normcase(str(path)) == os.path.normcase(str(locked_path)):
            raise PermissionError(13, "Permission denied", str(path))
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(duplicates, "open", fake_open, raising=False)


def test_a_locked_file_does_not_stop_the_check(tmp_path, dup_tree, monkeypatch):
    m = analysed(tmp_path, dup_tree)
    film = by_kind(m)[("file", "film.mp4")]
    lock(monkeypatch, dup_tree / "A" / "film.mp4")
    result = verify(m, film)
    assert result["unreadable"] == [str(dup_tree / "A" / "film.mp4")]
    assert result["state"] == "partial"  # A - Kopie and other still compared
    assert [str(dup_tree / "A - Kopie" / "film.mp4"), str(dup_tree / "other" / "film.mp4")] in result["clusters"]


def test_nothing_comparable_is_reported_as_unreadable(tmp_path, monkeypatch):
    root = tmp_path / "root"
    put(root / "p" / "sys.bin", blob(1, 2 * MB))
    put(root / "q" / "sys.bin", blob(2, 2 * MB))
    put(root / "q" / "other.txt", b"q")
    m = analysed(tmp_path, root)
    lock(monkeypatch, root / "p" / "sys.bin")
    result = verify(m, by_kind(m)[("file", "sys.bin")])
    assert result["state"] == "unreadable"


def test_a_locked_file_inside_a_folder_copy(tmp_path, dup_tree, monkeypatch):
    m = analysed(tmp_path, dup_tree)
    folder = next(g for g in by_kind(m).values() if g["kind"] == "dir")
    lock(monkeypatch, dup_tree / "A - Kopie" / "sub" / "big.bin")
    result = verify(m, folder)
    assert result["unreadable"] == [str(dup_tree / "A - Kopie")]
    assert result["state"] == "unreadable"


def link(src, dst) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        pytest.skip("hard links not supported here")


def test_hard_linked_files_are_recognised(tmp_path):
    root = tmp_path / "root"
    put(root / "x" / "linked.bin", blob(5, 2 * MB))
    link(root / "x" / "linked.bin", root / "y" / "linked.bin")
    put(root / "y" / "only-in-y.txt", b"y")  # the folders themselves differ
    m = analysed(tmp_path, root)
    result = verify(m, by_kind(m)[("file", "linked.bin")])
    assert result["state"] == "identical"
    assert result["hardlinked"] == [str(root / "x" / "linked.bin"), str(root / "y" / "linked.bin")]
    assert m.duplicates.verification.bytes_total == 2 * MB  # read once
    assert m.duplicates.verification.bytes_done == 2 * MB


def test_folders_with_other_file_names_are_not_duplicates(tmp_path):
    root = tmp_path / "root"
    put(root / "p" / "a.bin", blob(1, 2 * MB))
    put(root / "q" / "b.bin", blob(1, 2 * MB))  # same size and count, other name
    m = analysed(tmp_path, root)
    assert by_kind(m) == {}


def test_folders_with_differently_sized_files_are_not_duplicates(tmp_path):
    root = tmp_path / "root"
    put(root / "p" / "a.bin", blob(1, 2 * MB))
    put(root / "p" / "c.bin", blob(1, 1 * MB))
    put(root / "q" / "a.bin", blob(1, 1 * MB))  # same names, same total, sizes swapped
    put(root / "q" / "c.bin", blob(1, 2 * MB))
    m = analysed(tmp_path, root)
    assert [k for k, _ in by_kind(m)] == []


def test_subfolders_with_other_contents_are_not_duplicates(tmp_path):
    root = tmp_path / "root"
    put(root / "p" / "sub" / "a.bin", blob(1, 2 * MB))
    put(root / "q" / "sub" / "b.bin", blob(1, 2 * MB))  # same subfolder name, size and count
    m = analysed(tmp_path, root)
    assert by_kind(m) == {}


def test_swapped_sizes_never_collide(tmp_path):
    # Several independent pairs, so a weak (nearly linear) hash shows up reliably.
    root = tmp_path / "root"
    for k in range(8):
        put(root / f"p{k}" / f"first{k}.bin", blob(1, (2 + k) * MB))
        put(root / f"p{k}" / f"second{k}.bin", blob(1, 1 * MB))
        put(root / f"q{k}" / f"first{k}.bin", blob(1, 1 * MB))
        put(root / f"q{k}" / f"second{k}.bin", blob(1, (2 + k) * MB))
    m = analysed(tmp_path, root)
    assert [k for k, _ in by_kind(m)] == []


def test_verify_notices_a_renamed_file(tmp_path):
    root = tmp_path / "root"
    for top in ("x", "y"):
        put(root / top / "a.bin", blob(1, 2 * MB))
        put(root / top / "b.bin", blob(2, 2 * MB))
    m = analysed(tmp_path, root)
    folder = next(g for g in by_kind(m).values() if g["kind"] == "dir")
    os.rename(root / "y" / "b.bin", root / "y" / "c.bin")  # same contents in the same order
    assert verify(m, folder)["state"] == "different"


def test_hard_linked_folder_copy_is_recognised(tmp_path):
    root = tmp_path / "root"
    put(root / "x" / "a.bin", blob(5, 2 * MB))
    put(root / "x" / "b.bin", blob(6, 1 * MB))
    link(root / "x" / "a.bin", root / "y" / "a.bin")
    link(root / "x" / "b.bin", root / "y" / "b.bin")
    put(root / "z" / "a.bin", blob(5, 2 * MB))  # a real copy
    put(root / "z" / "b.bin", blob(6, 1 * MB))
    m = analysed(tmp_path, root)
    folder = next(g for g in by_kind(m).values() if g["kind"] == "dir")
    assert len(folder["members"]) == 3
    result = verify(m, folder)
    assert result["state"] == "identical"
    assert result["hardlinked"] == [str(root / "x"), str(root / "y")]  # z costs real space
    assert m.duplicates.verification.bytes_total == 2 * (3 * MB)  # x/y read once, z once


def test_results_and_checks_survive_a_restart(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    verify(m, by_kind(m)[("file", "film.mp4")])
    m.close()
    again = IndexManager(tmp_path / "data", roots_provider=lambda: [str(dup_tree)])
    assert again.duplicates.state == "ready"  # loaded, not analysed again
    film = by_kind(again)[("file", "film.mp4")]
    assert film["verified"]["state"] == "partial"
    again.close()


def test_reindex_analyses_again_and_drops_old_checks(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    verify(m, by_kind(m)[("file", "film.mp4")])
    put(dup_tree / "C" / "film.mp4", blob(1, 2 * MB))
    m.start()
    m.wait()
    m.duplicates.wait()
    film = by_kind(m)[("file", "film.mp4")]
    assert len(film["members"]) == 5
    assert film["verified"] is None
    m.close()


def test_only_one_check_at_a_time(tmp_path, dup_tree, monkeypatch):
    from sizeseekerweb.duplicates import Verification

    m = analysed(tmp_path, dup_tree)
    monkeypatch.setattr(Verification, "run", lambda self: None)  # stays "pending"
    m.duplicates.verify(0)
    with pytest.raises(VerifyBusyError):
        m.duplicates.verify(1)
    m.close()


def test_unknown_group(tmp_path, dup_tree):
    m = analysed(tmp_path, dup_tree)
    with pytest.raises(KeyError):
        m.duplicates.verify(99)
    m.close()
