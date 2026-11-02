"""Regression tests for the streaming worker lifecycle.

A finished ``AIWorkerThread`` deletes its C++ object via ``deleteLater``.  If the
panel kept its Python wrapper around, closing the overlay afterwards raised
``Internal C++ object (AIWorkerThread) already deleted`` inside
``closeEvent``, which in turn left the app holding a deleted overlay.
"""

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from mystic_pointer.ai.mock import MockProvider
from mystic_pointer.config import AppConfig
from mystic_pointer.ui.floating_panel import AIWorkerThread, FloatingPanel
from mystic_pointer.ui.selection import SelectionManager

_app = QApplication.instance() or QApplication([])


class _InstantProvider(MockProvider):
    """Provider that emits a single chunk without sleeping."""

    def generate_response(self, prompt, images):  # type: ignore[override]
        yield "done"


def _make_panel() -> FloatingPanel:
    return FloatingPanel(SelectionManager(), _InstantProvider(), AppConfig())


def test_shutdown_tolerates_already_deleted_worker() -> None:
    panel = _make_panel()
    worker = AIWorkerThread(_InstantProvider(), "hi", [Image.new("RGB", (8, 8))])
    panel._worker = worker

    # Simulate the normal finish path: the C++ thread is gone but a stale
    # Python reference remains (the bug reported by users).
    worker.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    panel.shutdown()  # Must not raise RuntimeError.
    panel.deleteLater()


def test_finished_worker_reference_is_forgotten() -> None:
    panel = _make_panel()
    worker = AIWorkerThread(_InstantProvider(), "hi", [Image.new("RGB", (8, 8))])
    panel._worker = worker
    worker.start()
    assert worker.wait(2000)

    panel._on_worker_finished(worker)
    assert panel._worker is None

    panel.shutdown()  # No-op once the reference is cleared.
    panel.deleteLater()


def test_generated_text_normalizes_whitespace_without_losing_indentation():
    raw = "  First line  \r\n\r\n\r\n    indented code\r\n\r\n- one  \r\n- two\r\n"
    assert FloatingPanel._normalize_generated_text(raw) == (
        "  First line\n\n    indented code\n\n- one\n- two"
    )


def test_panel_can_be_dragged_and_stays_inside_parent():
    parent = QWidget()
    parent.resize(800, 600)
    panel = FloatingPanel(SelectionManager(), _InstantProvider(), AppConfig(), parent)
    panel.move(100, 100)

    start = panel.mapToGlobal(QPoint(120, 20))
    panel._begin_panel_drag(start)
    assert panel.user_positioned

    panel._move_panel_to(start + QPoint(80, 60))
    assert panel.pos() == QPoint(180, 160)

    # Dragging far past the edge must clamp to the overlay, not move offscreen.
    panel._move_panel_to(start + QPoint(2000, 2000))
    assert panel.x() <= parent.width() - panel.width() - 12
    assert panel.y() <= parent.height() - panel.height() - 12

    panel._end_panel_drag()
    assert not panel._dragging_panel
    panel.deleteLater()
    parent.deleteLater()


def test_add_button_toggles_add_area_mode() -> None:
    manager = SelectionManager()
    panel = FloatingPanel(manager, _InstantProvider(), AppConfig())
    try:
        assert not panel.add_content_btn.isChecked()
        assert panel.add_hint_frame.isHidden()
        assert not panel.chips_widget.isHidden()

        panel.add_content_btn.click()
        assert manager.is_adding_content
        assert panel.add_content_btn.isChecked()
        assert panel.add_content_btn.text() == "Selecting…"
        # The inline hint replaces the suggestion chips so the mode is visible.
        assert not panel.add_hint_frame.isHidden()
        assert panel.chips_widget.isHidden()

        QTest.keyClick(panel, Qt.Key.Key_Escape)
        assert not manager.is_adding_content
        assert not panel.add_content_btn.isChecked()
        assert panel.add_content_btn.text() == "+ Add"
        assert panel.add_hint_frame.isHidden()
        assert not panel.chips_widget.isHidden()
    finally:
        panel.deleteLater()


def test_suggestion_chips_match_the_number_of_selections() -> None:
    manager = SelectionManager()
    panel = FloatingPanel(manager, _InstantProvider(), AppConfig())
    image = Image.new("RGB", (200, 200), (200, 40, 40))
    screen = QRect(0, 0, 200, 200)
    try:

        def chips() -> list[str]:
            texts: list[str] = []
            for index in range(panel.chips_layout.count()):
                item = panel.chips_layout.itemAt(index)
                widget = item.widget() if item is not None else None
                if isinstance(widget, QPushButton):
                    texts.append(widget.text())
            return texts

        assert "Summarize" in chips()

        manager.add_selection(QRect(10, 10, 40, 30), image, screen)
        manager.add_selection(QRect(60, 10, 40, 30), image, screen)
        assert "Summarize both" in chips()
        assert "Summarize all" not in chips()

        manager.add_selection(QRect(110, 10, 40, 30), image, screen)
        assert "Summarize all" in chips()
        assert "Summarize both" not in chips()
    finally:
        panel.deleteLater()


def test_response_text_renders_markdown_instead_of_literal_markers() -> None:
    panel = _make_panel()
    try:
        panel._set_response_text("**Updates**\n\n* one\n* two\n\n---\n\nDone")

        plain = panel.response_text.toPlainText()
        assert "**" not in plain
        assert "---" not in plain
        assert "Updates" in plain
        assert "one" in plain and "two" in plain

        html = panel.response_text.toHtml().lower()
        assert "font-weight:700" in html or "<strong" in html
        assert "<li" in html or "list" in html
    finally:
        panel.deleteLater()


def test_first_reveal_adopts_polished_layout_height() -> None:
    """The panel is laid out while hidden, so its first show must re-fit.

    Qt resolves stylesheet-dependent size hints only after polish.  A height
    cached before that is ~18 px short; showing the panel at that height
    squeezes the prompt input and clips its bottom border until a later
    resize (which is why the bug disappeared after generating a response).
    """
    parent = QWidget()
    parent.resize(900, 700)
    parent.show()

    manager = SelectionManager()
    panel = FloatingPanel(manager, _InstantProvider(), AppConfig(), parent)
    try:
        panel.hide()
        manager.add_selection(
            QRect(10, 10, 40, 30),
            Image.new("RGB", (200, 200), (200, 40, 40)),
            QRect(0, 0, 200, 200),
        )
        # Reproduce the stale height cached while the panel was hidden.
        panel.resize(panel.width(), 147)

        panel.reveal()
        QTest.qWait(50)
        layout = panel.layout()
        assert layout is not None
        layout.activate()

        input_container = panel.prompt_input.parentWidget()
        assert input_container is not None
        assert input_container.height() >= panel.prompt_input.height()
        assert panel.prompt_input.height() >= 38
        assert panel.height() >= layout.sizeHint().height()
        # The input's bottom border needs breathing room above the chip row.
        assert panel.height() - panel.chips_widget.geometry().bottom() - 1 >= 10
    finally:
        panel.deleteLater()
        parent.deleteLater()


def test_add_mode_ends_after_adding_another_area() -> None:
    manager = SelectionManager()
    panel = FloatingPanel(manager, _InstantProvider(), AppConfig())
    try:
        manager.set_adding_content(True)
        assert panel.add_content_btn.isChecked()

        item = manager.add_selection(
            QRect(10, 10, 40, 30),
            Image.new("RGB", (200, 200), (200, 40, 40)),
            QRect(0, 0, 200, 200),
        )
        assert item is not None
        assert not manager.is_adding_content
        assert not panel.add_content_btn.isChecked()
        assert panel.add_hint_frame.isHidden()
    finally:
        panel.deleteLater()
