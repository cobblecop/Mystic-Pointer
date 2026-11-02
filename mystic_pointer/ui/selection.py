"""Selection state and models for Mystic Pointer."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QPixmap

from mystic_pointer.core.screen_capture import ScreenCapture


@dataclass
class SelectionItem:
    id: int
    rect: QRect
    image: Image.Image
    thumbnail: QPixmap
    label: str = ""


class SelectionManager(QObject):
    """Manages the set of selected regions and multi-item additions."""

    selection_changed = Signal()
    adding_content_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.items: list[SelectionItem] = []
        self._next_id = 1
        self.is_adding_content = False

    def _set_adding_content(self, adding: bool) -> None:
        if self.is_adding_content == adding:
            return
        self.is_adding_content = adding
        self.adding_content_changed.emit(adding)

    def add_selection(
        self,
        rect: QRect,
        full_image: Image.Image | None,
        screen_geometry: QRect,
        device_pixel_ratio: float = 1.0,
    ) -> SelectionItem | None:
        cropped = ScreenCapture.capture_area(rect, full_image, screen_geometry, device_pixel_ratio)
        if cropped is None or cropped.width <= 0 or cropped.height <= 0:
            self._set_adding_content(False)
            return None

        # Generate thumbnail
        thumb_img = cropped.copy()
        thumb_img.thumbnail((80, 80), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        thumb_img.save(buf, format="PNG")
        qpix = QPixmap()
        qpix.loadFromData(buf.getvalue())

        item = SelectionItem(
            id=self._next_id,
            rect=rect,
            image=cropped,
            thumbnail=qpix,
            label=f"Item {self._next_id}",
        )
        self._next_id += 1
        self.items.append(item)
        self._set_adding_content(False)
        self.selection_changed.emit()
        return item

    def remove_item(self, item_id: int) -> None:
        self.items = [it for it in self.items if it.id != item_id]
        self.selection_changed.emit()

    def clear(self) -> None:
        self.items.clear()
        self._next_id = 1
        self._set_adding_content(False)
        self.selection_changed.emit()

    def set_adding_content(self, adding: bool = True) -> None:
        self._set_adding_content(adding)

    @property
    def has_selection(self) -> bool:
        return len(self.items) > 0

    @property
    def images(self) -> list[Image.Image]:
        return [it.image for it in self.items]
