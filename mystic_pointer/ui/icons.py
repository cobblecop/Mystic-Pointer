"""Small, dependency-free icons drawn with QPainter."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform

from mystic_pointer.ui.style import ACCENT


def _pointer_path() -> QPainterPath:
    """A classic mouse pointer outline in a 24x24 coordinate space."""
    path = QPainterPath()
    path.moveTo(7.0, 3.0)
    path.lineTo(7.0, 19.0)
    path.lineTo(11.0, 15.2)
    path.lineTo(14.2, 21.2)
    path.lineTo(17.0, 19.8)
    path.lineTo(13.8, 13.8)
    path.lineTo(19.0, 13.8)
    path.closeSubpath()
    return path


def make_pointer_pixmap(
    size: int,
    color: str = "#ffffff",
    background: str | None = None,
    radius: float = 0.0,
) -> QPixmap:
    """Render the pointer mark, optionally on a rounded background."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if background:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        inset = 1.0
        painter.drawRoundedRect(
            QRectF(inset, inset, size - inset * 2, size - inset * 2),
            radius,
            radius,
        )

    glyph_size = size * 0.58
    offset = (size - glyph_size) / 2.0
    transform = QTransform()
    transform.translate(offset, offset)
    transform.scale(glyph_size / 24.0, glyph_size / 24.0)
    path = transform.map(_pointer_path())

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)
    painter.end()
    return pixmap


def make_pointer_icon(size: int = 18, color: str = "#f6f5f4") -> QPixmap:
    """Transparent pointer glyph used in the floating panel header."""
    return make_pointer_pixmap(size, color=color)


def _draw_action_glyph(painter: QPainter, kind: str) -> None:
    """Draw one 24x24 outline glyph for the selection action bar."""
    if kind == "screenshot":
        # A small camera: body, viewfinder hump and lens.
        painter.drawRoundedRect(QRectF(3.5, 7.0, 17.0, 12.5), 2.8, 2.8)
        painter.drawPolyline(
            [
                QPointF(8.5, 7.0),
                QPointF(9.6, 4.6),
                QPointF(14.4, 4.6),
                QPointF(15.5, 7.0),
            ]
        )
        painter.drawEllipse(QPointF(12.0, 13.25), 3.4, 3.4)
        return

    if kind == "copy":
        # Two offset sheets read as "copy" at small sizes.
        painter.drawRoundedRect(QRectF(8.0, 8.0, 11.5, 12.0), 2.2, 2.2)
        painter.drawRoundedRect(QRectF(4.5, 4.0, 11.5, 12.0), 2.2, 2.2)


def make_action_pixmap(kind: str, size: int = 16, color: str = "#f6f5f4") -> QPixmap:
    """Render one of the action-bar glyphs at the requested pixel size."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw_action_glyph(painter, kind)
    painter.end()
    return pixmap


def create_tray_icon_pixmap(enabled: bool = True) -> QPixmap:
    """A neutral GNOME-style app mark for the status area."""
    return make_pointer_pixmap(
        32,
        color="#ffffff",
        background=ACCENT if enabled else "#77767b",
        radius=8.0,
    )
