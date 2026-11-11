import sys

import pytest

from sizeseekerweb.foreground import bring_to_front, explorer_windows, pick_window

FOLDER = r"C:\Users\me\Videos"


def test_a_newly_opened_window_wins():
    before = {1: "Videos – Datei-Explorer"}
    after = {1: "Videos – Datei-Explorer", 7: ""}  # title may still be empty
    assert pick_window(before, after, FOLDER) == 7


@pytest.mark.parametrize(
    "title",
    ["Videos – Datei-Explorer", "Videos - File Explorer", "Videos", "videos", r"C:\Users\me\Videos"],
)
def test_an_existing_window_is_found_by_its_title(title):
    after = {3: "Downloads – Datei-Explorer", 5: title}
    assert pick_window(dict(after), after, FOLDER) == 5


def test_similar_folder_names_do_not_match():
    after = {3: "Videos-alt – Datei-Explorer", 4: "My Videos – Datei-Explorer"}
    assert pick_window(dict(after), after, FOLDER) is None


def test_drive_root_by_path_title():
    after = {9: "C:\\"}
    assert pick_window(dict(after), after, "C:\\") == 9


def test_nothing_open():
    assert pick_window({}, {}, FOLDER) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_win32_calls_work_without_errors():
    windows = explorer_windows()
    assert all(isinstance(h, int) and isinstance(t, str) for h, t in windows.items())
    assert bring_to_front(0) is False  # an invalid window is never reported as success
