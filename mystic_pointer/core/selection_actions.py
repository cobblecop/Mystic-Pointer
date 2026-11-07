"""Image helpers behind the selection action bar.

The screenshot action writes one PNG per selected area.  The copy action can
either expose every selection as its own PNG file on the clipboard (the
default) or combine them into a single image when the merge preference is on.
Keeping these operations independent of the overlay makes them easy to test and
reuse.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

# The same near-black used by the floating panel, so gaps between stacked
# selections look intentional on any desktop background.
_COMPOSITE_BACKGROUND = (36, 36, 36, 255)
_DEFAULT_GAP = 8


def _valid_images(images: list[Image.Image]) -> list[Image.Image]:
    return [image for image in images if image is not None and image.width > 0 and image.height > 0]


def compose_selection_image(
    images: list[Image.Image],
    gap: int = _DEFAULT_GAP,
) -> Image.Image | None:
    """Combine all selections into one image for the clipboard.

    A single selection is copied unchanged.  Multiple selections are stacked
    vertically, centred, with a small gap so each region stays distinguishable.
    """
    valid = _valid_images(images)
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0].copy()

    width = max(image.width for image in valid)
    height = sum(image.height for image in valid) + gap * (len(valid) - 1)
    composite = Image.new("RGBA", (width, height), _COMPOSITE_BACKGROUND)

    y = 0
    for image in valid:
        rgba = image.convert("RGBA")
        x = (width - rgba.width) // 2
        composite.alpha_composite(rgba, (x, y))
        y += rgba.height + gap
    return composite


def default_screenshot_directory() -> Path:
    """Return the user's Pictures folder with a Mystic Pointer subfolder."""
    try:
        from PySide6.QtCore import QStandardPaths

        pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        base = Path(pictures) if pictures else Path.home() / "Pictures"
    except Exception:
        base = Path.home() / "Pictures"
    return base / "Mystic Pointer"


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


def clipboard_image_directory() -> Path:
    """Return a temporary folder that holds images referenced by the clipboard."""
    try:
        from PySide6.QtCore import QStandardPaths

        temp = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
        base = Path(temp) if temp else Path(tempfile.gettempdir())
    except Exception:
        base = Path(tempfile.gettempdir())
    return base / "mystic_pointer_clipboard"


def save_clipboard_images(
    images: list[Image.Image],
    directory: Path | None = None,
) -> list[Path]:
    """Write each selected area to its own PNG for a multi-file clipboard.

    Desktop clipboards hold one image item at a time, so separate selections are
    exposed as a file list.  File managers, chat apps and image editors that
    accept dropped or pasted files then receive every area individually.
    """
    valid = _valid_images(images)
    if not valid:
        return []

    target = directory or clipboard_image_directory()
    target.mkdir(parents=True, exist_ok=True)

    # The previous clipboard payload is being replaced; its files are no longer
    # referenced and can be removed.
    for stale in target.glob("*.png"):
        try:
            stale.unlink()
        except OSError:
            pass

    paths: list[Path] = []
    for index, image in enumerate(valid, start=1):
        path = target / f"Mystic Pointer Clipboard - {index}.png"
        image.save(path, format="PNG")
        paths.append(path)
    return paths


def save_selection_images(
    images: list[Image.Image],
    directory: Path | None = None,
    timestamp: datetime | None = None,
) -> list[Path]:
    """Save each selected area as its own PNG and return the written paths."""
    valid = _valid_images(images)
    if not valid:
        return []

    target = directory or default_screenshot_directory()
    target.mkdir(parents=True, exist_ok=True)

    moment = timestamp or datetime.now()
    stamp = moment.strftime("%Y-%m-%d %H-%M-%S")
    multiple = len(valid) > 1
    paths: list[Path] = []

    for index, image in enumerate(valid, start=1):
        stem = f"Mystic Pointer {stamp}"
        if multiple:
            stem += f" - {index}"
        path = _unique_path(target, stem, ".png")
        image.save(path, format="PNG")
        paths.append(path)
    return paths
