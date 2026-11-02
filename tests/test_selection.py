"""Tests for selection manager and items."""

from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from mystic_pointer.ui.selection import SelectionManager

# Ensure QApplication exists for QPixmap
_app = QApplication.instance() or QApplication([])


def test_selection_lifecycle():
    manager = SelectionManager()
    assert not manager.has_selection
    assert len(manager.items) == 0

    full_image = Image.new("RGBA", (1920, 1080), (255, 0, 0, 255))
    virtual_geom = QRect(0, 0, 1920, 1080)

    # Add item 1
    rect1 = QRect(100, 100, 200, 150)
    item1 = manager.add_selection(rect1, full_image, virtual_geom)
    assert item1 is not None
    assert item1.id == 1
    assert item1.rect == rect1
    assert item1.image.size == (200, 150)
    assert manager.has_selection
    assert len(manager.items) == 1

    # Add item 2
    rect2 = QRect(400, 300, 100, 100)
    item2 = manager.add_selection(rect2, full_image, virtual_geom)
    assert item2 is not None
    assert item2.id == 2
    assert len(manager.items) == 2
    assert len(manager.images) == 2

    # Remove item 1
    manager.remove_item(item1.id)
    assert len(manager.items) == 1
    assert manager.items[0].id == 2

    # Clear
    manager.clear()
    assert not manager.has_selection
    assert len(manager.items) == 0


def test_adding_content_signal_tracks_lifecycle() -> None:
    manager = SelectionManager()
    seen: list[bool] = []
    manager.adding_content_changed.connect(seen.append)

    manager.set_adding_content(True)
    manager.set_adding_content(True)  # Duplicate updates stay silent.
    assert manager.is_adding_content
    assert seen == [True]

    full_image = Image.new("RGBA", (200, 200), (255, 0, 0, 255))
    geometry = QRect(0, 0, 200, 200)
    item = manager.add_selection(QRect(10, 10, 50, 50), full_image, geometry)
    assert item is not None
    # Adding an area ends add-mode and tells the panel to reset its button.
    assert not manager.is_adding_content
    assert seen == [True, False]

    manager.set_adding_content(True)
    manager.clear()
    assert not manager.is_adding_content
    assert seen == [True, False, True, False]
