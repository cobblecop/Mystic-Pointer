"""Compact actions shown next to the current screen selection."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from mystic_pointer.ui.icons import make_action_pixmap
from mystic_pointer.ui.style import SELECTION_ACTION_BAR_STYLE


def choose_action_bar_position(
    anchor: QRect,
    bar_size: QSize,
    bounds: QRect,
    obstacles: list[QRect] | None = None,
    margin: int = 12,
    gap: int = 12,
) -> QPoint:
    """Pick a spot next to ``anchor`` that avoids selections and other panels.

    Candidates are tried above, below, right and left of the selection union.
    A candidate that overlaps the selection or a visible panel is penalised, so
    the toolbar moves out of the way when a selection touches the screen edge.
    """
    width = bar_size.width()
    height = bar_size.height()
    candidates = [
        QPoint(anchor.center().x() - width // 2, anchor.top() - height - gap),
        QPoint(anchor.center().x() - width // 2, anchor.bottom() + gap + 1),
        QPoint(anchor.right() + gap + 1, anchor.center().y() - height // 2),
        QPoint(anchor.left() - width - gap, anchor.center().y() - height // 2),
    ]

    max_x = max(bounds.left() + margin, bounds.right() - width - margin + 1)
    max_y = max(bounds.top() + margin, bounds.bottom() - height - margin + 1)
    anchor_zone = anchor.adjusted(-2, -2, 2, 2)
    blocked = [rect for rect in (obstacles or []) if not rect.isNull()]

    best = QPoint(bounds.left() + margin, bounds.top() + margin)
    best_score: int | None = None
    for index, candidate in enumerate(candidates):
        x = max(bounds.left() + margin, min(candidate.x(), max_x))
        y = max(bounds.top() + margin, min(candidate.y(), max_y))
        rect = QRect(x, y, width, height)

        overlap = rect.intersected(anchor_zone)
        score = overlap.width() * overlap.height() * 100
        for obstacle in blocked:
            intersection = rect.intersected(obstacle)
            score += intersection.width() * intersection.height() * 100
        # Candidate order is a stable tie-breaker: above, below, right, left.
        score += index

        if best_score is None or score < best_score:
            best_score = score
            best = QPoint(x, y)
    return best


class SelectionActionBar(QFrame):
    """One pill with Screenshot and Copy for all selections."""

    screenshot_requested = Signal()
    copy_requested = Signal()
    resized = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SelectionActionBar")
        self.setStyleSheet(SELECTION_ACTION_BAR_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(2)

        self.screenshot_button = self._make_button(
            "Screenshot",
            "screenshot",
            "Save the selected area(s) as PNG files",
        )
        self.screenshot_button.clicked.connect(
            lambda checked=False: self.screenshot_requested.emit()
        )
        layout.addWidget(self.screenshot_button)

        self.copy_button = self._make_button(
            "Copy",
            "copy",
            "Copy the selected area(s) to the clipboard",
        )
        self.copy_button.clicked.connect(lambda checked=False: self.copy_requested.emit())
        layout.addWidget(self.copy_button)

        self.status_label = QLabel()
        self.status_label.setObjectName("ActionStatus")
        self.status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

    def _make_button(self, text: str, kind: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("ActionButton")
        button.setIcon(QIcon(make_action_pixmap(kind)))
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(tooltip)
        return button

    def show_status(self, text: str, timeout_ms: int = 2400) -> None:
        """Show a short confirmation next to the action buttons."""
        self.status_label.setText(text)
        self.status_label.show()
        self._fit()
        self._status_timer.start(timeout_ms)

    def _clear_status(self) -> None:
        self.status_label.hide()
        self.status_label.clear()
        self._fit()

    def _fit(self) -> None:
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self.adjustSize()
        self.resized.emit()
