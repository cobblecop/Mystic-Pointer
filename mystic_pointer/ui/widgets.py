"""Reusable Adwaita-style widgets used by the preferences window."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QWidget

from mystic_pointer.ui.style import ACCENT


class ComboBox(QComboBox):
    """Combo box with a painted Adwaita chevron instead of a native arrow."""

    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        window = self.palette().color(QPalette.ColorRole.Window)
        dark = window.lightness() < 128
        if not self.isEnabled():
            color = QColor("#77767b" if dark else "#9a9996")
        else:
            color = QColor("#b5b3b0" if dark else "#5e5c64")

        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        x = self.width() - 15.0
        y = self.height() / 2.0
        if self.view().isVisible():
            painter.drawLine(QPointF(x - 4.0, y + 2.0), QPointF(x, y - 2.0))
            painter.drawLine(QPointF(x, y - 2.0), QPointF(x + 4.0, y + 2.0))
        else:
            painter.drawLine(QPointF(x - 4.0, y - 2.0), QPointF(x, y + 2.0))
            painter.drawLine(QPointF(x, y + 2.0), QPointF(x + 4.0, y - 2.0))
        painter.end()

    def showPopup(self) -> None:  # noqa: N802 - Qt API
        super().showPopup()
        self.update()

    def hidePopup(self) -> None:  # noqa: N802 - Qt API
        super().hidePopup()
        self.update()


class ToggleSwitch(QCheckBox):
    """A compact GNOME-style switch with a short, smooth slide animation."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(130)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def hitButton(self, pos) -> bool:  # noqa: ANN001 - Qt virtual signature
        return self.rect().contains(pos)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate_to_state(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self._animation.stop()
            self._set_offset(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        window = self.palette().color(QPalette.ColorRole.Window)
        dark = window.lightness() < 128

        checked = self.isChecked()
        enabled = self.isEnabled()
        hovered = self.underMouse()
        focused = self.hasFocus()

        track_rect = QRectF(1.0, 2.0, 44.0, 22.0)
        radius = track_rect.height() / 2.0

        if not enabled:
            track = QColor("#3d3d3d" if dark else "#deddda")
        elif checked:
            track = QColor(ACCENT)
        elif hovered:
            track = QColor("#6e6c74" if dark else "#b0afac")
        else:
            track = QColor("#5e5c64" if dark else "#c0bfbc")

        if focused:
            focus_pen = QPen(QColor(53, 132, 228, 110))
            focus_pen.setWidthF(2.0)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(0.0, 0.0, self.width() - 1.0, self.height() - 1.0),
                13.0,
                13.0,
            )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(track_rect, radius, radius)

        knob_x = 4.0 + self._offset * 20.0
        knob_rect = QRectF(knob_x, 4.0, 18.0, 18.0)
        painter.setBrush(QColor(0, 0, 0, 34))
        painter.drawEllipse(knob_rect.translated(0.0, 1.0))

        knob = QColor("#ffffff" if enabled else ("#77767b" if dark else "#f6f5f4"))
        border = QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 24)
        painter.setBrush(knob)
        painter.setPen(QPen(border, 1.0))
        painter.drawEllipse(knob_rect.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        if not self.isVisible():
            self._set_offset(1.0 if checked else 0.0)

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().showEvent(event)
        self._set_offset(1.0 if self.isChecked() else 0.0)

    def enterEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().leaveEvent(event)
        self.update()
