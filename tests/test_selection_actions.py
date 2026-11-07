"""Tests for the screenshot and clipboard helpers behind the action bar."""

from __future__ import annotations

from datetime import datetime

from PIL import Image

from mystic_pointer.core.selection_actions import (
    compose_selection_image,
    save_clipboard_images,
    save_selection_images,
)


def _solid(width: int, height: int, color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def test_single_selection_is_copied_unchanged() -> None:
    source = _solid(30, 20, (200, 40, 40))
    result = compose_selection_image([source])

    assert result is not None
    assert result is not source
    assert result.size == source.size
    assert result.getpixel((0, 0)) == (200, 40, 40)


def test_multiple_selections_stack_vertically_with_a_gap() -> None:
    first = _solid(100, 40, (255, 0, 0))
    second = _solid(60, 30, (0, 0, 255))

    result = compose_selection_image([first, second], gap=8)

    assert result is not None
    assert result.size == (100, 78)
    # The first image fills the top band.
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)
    # The gap is the popover background, not transparent.
    assert result.getpixel((0, 45)) == (36, 36, 36, 255)
    # The narrower second image is centred.
    assert result.getpixel((0, 50)) == (36, 36, 36, 255)
    assert result.getpixel((50, 50)) == (0, 0, 255, 255)


def test_empty_selection_has_no_composite() -> None:
    assert compose_selection_image([]) is None
    assert compose_selection_image([Image.new("RGB", (0, 0))]) is None


def test_screenshot_saves_one_png_per_selected_area(tmp_path) -> None:
    first = _solid(20, 10, (10, 20, 30))
    second = _solid(12, 8, (40, 50, 60))

    paths = save_selection_images(
        [first, second],
        directory=tmp_path,
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert [path.name for path in paths] == [
        "Mystic Pointer 2026-01-02 03-04-05 - 1.png",
        "Mystic Pointer 2026-01-02 03-04-05 - 2.png",
    ]
    assert all(path.exists() for path in paths)
    assert Image.open(paths[0]).size == (20, 10)
    assert Image.open(paths[1]).size == (12, 8)


def test_single_screenshot_has_no_index_suffix(tmp_path) -> None:
    paths = save_selection_images(
        [_solid(20, 10, (10, 20, 30))],
        directory=tmp_path,
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert [path.name for path in paths] == ["Mystic Pointer 2026-01-02 03-04-05.png"]


def test_repeated_screenshots_do_not_overwrite(tmp_path) -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5)
    first = save_selection_images([_solid(10, 10, (1, 2, 3))], tmp_path, moment)
    second = save_selection_images([_solid(10, 10, (4, 5, 6))], tmp_path, moment)

    assert first[0] != second[0]
    assert second[0].name == "Mystic Pointer 2026-01-02 03-04-05 (2).png"
    assert second[0].exists()


def test_saving_no_images_writes_nothing(tmp_path) -> None:
    assert save_selection_images([], directory=tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_clipboard_images_are_saved_as_separate_pngs(tmp_path) -> None:
    paths = save_clipboard_images(
        [_solid(20, 10, (10, 20, 30)), _solid(12, 8, (40, 50, 60))],
        directory=tmp_path,
    )

    assert [path.name for path in paths] == [
        "Mystic Pointer Clipboard - 1.png",
        "Mystic Pointer Clipboard - 2.png",
    ]
    assert Image.open(paths[0]).size == (20, 10)
    assert Image.open(paths[1]).size == (12, 8)


def test_new_clipboard_copy_removes_stale_files(tmp_path) -> None:
    stale = tmp_path / "old.png"
    stale.write_bytes(b"old")

    save_clipboard_images([_solid(10, 10, (1, 2, 3))], directory=tmp_path)

    assert not stale.exists()
    assert len(list(tmp_path.glob("*.png"))) == 1
    assert save_clipboard_images([], directory=tmp_path) == []
