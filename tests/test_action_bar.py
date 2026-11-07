"""Tests for the compact selection action pill and its placement."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication

from mystic_pointer.ui.action_bar import SelectionActionBar, choose_action_bar_position

_app = QApplication.instance() or QApplication([])


def test_action_buttons_emit_their_requests() -> None:
    bar = SelectionActionBar()
    received: list[str] = []
    bar.screenshot_requested.connect(lambda: received.append("screenshot"))
    bar.copy_requested.connect(lambda: received.append("copy"))

    bar.screenshot_button.click()
    bar.copy_button.click()

    assert received == ["screenshot", "copy"]
    assert bar.screenshot_button.toolTip()
    assert bar.copy_button.toolTip()
    bar.deleteLater()


def test_status_message_can_be_shown_and_cleared() -> None:
    bar = SelectionActionBar()
    bar.show_status("Saved 2 screenshots")

    assert not bar.status_label.isHidden()
    assert bar.status_label.text() == "Saved 2 screenshots"

    bar._clear_status()

    assert bar.status_label.isHidden()
    assert bar.status_label.text() == ""
    bar.deleteLater()


def test_position_prefers_above_the_selection() -> None:
    anchor = QRect(200, 150, 100, 80)
    position = choose_action_bar_position(
        anchor,
        QSize(180, 36),
        QRect(0, 0, 500, 400),
    )

    assert position == QPoint(159, 102)


def test_position_moves_below_when_the_top_edge_is_blocked() -> None:
    anchor = QRect(200, 8, 100, 80)
    position = choose_action_bar_position(
        anchor,
        QSize(180, 36),
        QRect(0, 0, 500, 400),
    )

    assert position.y() >= anchor.bottom()
    assert position.y() + 36 <= 400


def test_position_avoids_the_floating_panel() -> None:
    anchor = QRect(200, 150, 100, 80)
    panel = QRect(150, 90, 300, 60)
    position = choose_action_bar_position(
        anchor,
        QSize(180, 36),
        QRect(0, 0, 500, 400),
        obstacles=[panel],
    )

    bar_rect = QRect(position, QSize(180, 36))
    assert not bar_rect.intersects(panel)
    assert position.y() > anchor.bottom()


def test_position_stays_inside_the_overlay() -> None:
    anchor = QRect(2, 2, 20, 20)
    position = choose_action_bar_position(
        anchor,
        QSize(240, 36),
        QRect(0, 0, 260, 120),
    )

    assert position.x() >= 12
    assert position.y() >= 12
    assert position.x() + 240 <= 260
    assert position.y() + 36 <= 120
