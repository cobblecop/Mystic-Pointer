"""Floating AI prompt panel and response card for Mystic Pointer."""

from __future__ import annotations

import math

from PIL import Image
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QClipboard,
    QColor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPixmap,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mystic_pointer.ai.base import AIProvider
from mystic_pointer.config import AppConfig
from mystic_pointer.ui.response_markdown import render_markdown
from mystic_pointer.ui.selection import SelectionItem, SelectionManager
from mystic_pointer.ui.style import FLOATING_PANEL_STYLE, RESPONSE_DOCUMENT_STYLE


def _thumbnail_pixmap(source: QPixmap, size: int = 34, radius: float = 6.0) -> QPixmap:
    """Center-crop a selection thumbnail into a square with rounded corners."""
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size) // 2)
    y = max(0, (scaled.height() - size) // 2)
    cropped = scaled.copy(x, y, size, size)

    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return rounded


class AIWorkerThread(QThread):
    chunk_received = Signal(str)
    finished_stream = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        provider: AIProvider,
        prompt: str,
        images: list[Image.Image],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.provider = provider
        self.prompt = prompt
        self.images = images

    def run(self) -> None:
        try:
            for chunk in self.provider.generate_response(self.prompt, self.images):
                if self.isInterruptionRequested():
                    return
                self.chunk_received.emit(chunk)
            self.finished_stream.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))


class ThumbnailChip(QFrame):
    """Compact thumbnail representing an active selection item."""

    remove_requested = Signal(int)

    def __init__(self, item: SelectionItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_id = item.id
        self.setObjectName("ThumbnailChip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)

        image_label = QLabel()
        image_label.setObjectName("ThumbnailLabel")
        image_label.setFixedSize(34, 34)
        image_label.setPixmap(_thumbnail_pixmap(item.thumbnail))
        layout.addWidget(image_label)

        title = QLabel(item.label or "Selection")
        title.setObjectName("ThumbnailLabel")
        title.setMaximumWidth(74)
        layout.addWidget(title)

        remove_button = QPushButton("×")
        remove_button.setObjectName("RemoveButton")
        remove_button.setFixedSize(18, 18)
        remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_button.setToolTip("Remove selection")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self.item_id))
        layout.addWidget(remove_button)


class FloatingPanel(QFrame):
    """Dark Adwaita-style popover for asking about a screen selection."""

    close_requested = Signal()
    panel_resized = Signal()

    def __init__(
        self,
        selection_manager: SelectionManager,
        provider: AIProvider,
        config: AppConfig,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("MysticFloatingPanel")
        self.selection_manager = selection_manager
        self.provider = provider
        self.config = config
        self.user_positioned = False
        self._dragging_panel = False
        self._drag_offset = QPoint()
        self._worker: AIWorkerThread | None = None
        self._awaiting_first_chunk = False
        self._response_raw = ""
        self._response_fit_timer = QTimer(self)
        self._response_fit_timer.setSingleShot(True)
        self._response_fit_timer.timeout.connect(self._fit_response_text)
        self._panel_resize_timer = QTimer(self)
        self._panel_resize_timer.setSingleShot(True)
        self._panel_resize_timer.setInterval(16)
        self._panel_resize_timer.timeout.connect(self._finalize_panel_size)
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._reset_copy_button)
        self._reveal_anim: QVariantAnimation | None = None

        self.setStyleSheet(FLOATING_PANEL_STYLE)
        self.setFixedWidth(560)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self._setup_ui()
        self.selection_manager.selection_changed.connect(self._on_selection_changed)
        self.selection_manager.adding_content_changed.connect(self._on_adding_content_changed)
        if self.selection_manager.items:
            self._on_selection_changed()

        self._apply_shadow()

    def _apply_shadow(self) -> None:
        """Restore the popover shadow after the reveal fade finishes."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 9)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

    def reveal(self) -> None:
        """Show the popover with a short fade rather than a hard pop.

        The panel has a drop-shadow effect, and Qt only allows one graphics
        effect per widget, so the shadow is swapped for an opacity effect during
        the fade and restored immediately afterwards.
        """
        if self._reveal_anim is not None:
            self.raise_()
            return
        if self.isVisible():
            self.raise_()
            return

        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.0)
        self.setGraphicsEffect(opacity)
        self.show()
        self.raise_()
        self._fit_to_layout()

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(150)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda value: opacity.setOpacity(float(value)))
        anim.finished.connect(self._finish_reveal)
        self._reveal_anim = anim
        anim.start()

    def _finish_reveal(self) -> None:
        self._reveal_anim = None
        self._apply_shadow()

    def _fit_to_layout(self) -> None:
        """Adopt the polished layout height once the panel is shown.

        Qt only resolves stylesheet-dependent size hints after a widget has
        been polished.  The panel is built hidden, so the first ``adjustSize``
        can cache a height that is a dozen pixels too short; the layout then
        squeezes the prompt input and clips its bottom border.  Re-activate the
        layout after showing and resize to its real hint.
        """
        layout = self.layout()
        if layout is None:
            return
        self.ensurePolished()
        layout.activate()
        target = max(layout.sizeHint().height(), layout.minimumSize().height())
        if target > 0 and self.height() != target:
            self.resize(self.width(), target)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().resizeEvent(event)
        self.panel_resized.emit()

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        super().showEvent(event)
        self._schedule_response_fit()

    # --- Moving the dialog ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_panel_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_panel and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_panel_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging_panel and event.button() == Qt.MouseButton.LeftButton:
            self._end_panel_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_panel_drag(self, global_pos: QPoint) -> None:
        self._dragging_panel = True
        self.user_positioned = True
        self._drag_offset = global_pos - self.mapToGlobal(QPoint(0, 0))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.header_widget.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _move_panel_to(self, global_pos: QPoint) -> None:
        if not self._dragging_panel:
            return
        target = global_pos - self._drag_offset
        parent = self.parentWidget()
        if parent is not None:
            target = parent.mapFromGlobal(target)
            margin = 12
            max_x = max(margin, parent.width() - self.width() - margin)
            max_y = max(margin, parent.height() - self.height() - margin)
            target.setX(max(margin, min(target.x(), max_x)))
            target.setY(max(margin, min(target.y(), max_y)))
        self.move(target)

    def _end_panel_drag(self) -> None:
        self._dragging_panel = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header_widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)

        self.header_widget = QWidget()
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(8)

        self.thumbs_container = QWidget()
        self.thumbs_layout = QHBoxLayout(self.thumbs_container)
        self.thumbs_layout.setContentsMargins(4, 0, 0, 0)
        self.thumbs_layout.setSpacing(6)
        self.header_layout.addWidget(self.thumbs_container)

        self.add_content_btn = QPushButton("+ Add")
        self.add_content_btn.setObjectName("AddButton")
        self.add_content_btn.setCheckable(True)
        self.add_content_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_content_btn.setToolTip("Add another area from the screen")
        self.add_content_btn.toggled.connect(self._on_add_toggled)
        self.header_layout.addWidget(self.add_content_btn)
        self.header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseButton")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.close_requested.emit)
        self.header_layout.addWidget(close_btn)

        self.main_layout.addWidget(self.header_widget)

        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.prompt_input = QLineEdit()
        self.prompt_input.setObjectName("PromptInput")
        self.prompt_input.setPlaceholderText("Ask about your selection…")
        self.prompt_input.returnPressed.connect(self._on_submit_prompt)
        input_layout.addWidget(self.prompt_input, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._on_submit_prompt)
        input_layout.addWidget(self.send_btn)

        self.main_layout.addWidget(input_container)

        # The prompt field has a visible rounded border; the suggestion chips
        # need a little more air below it than the layout's default rhythm so
        # the input's bottom edge does not look clipped into the chip row.
        self.main_layout.addSpacing(6)

        self.chips_widget = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_widget)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(6)
        self.main_layout.addWidget(self.chips_widget)
        self._populate_chips()

        # Shown while the user is picking an additional area.  It occupies the
        # suggestion-chip slot so the rest of the panel stays put.
        self.add_hint_frame = QFrame()
        self.add_hint_frame.setObjectName("AddHint")
        add_hint_layout = QHBoxLayout(self.add_hint_frame)
        add_hint_layout.setContentsMargins(10, 5, 10, 5)
        add_hint_layout.setSpacing(7)
        add_hint_dot = QLabel("●")
        add_hint_dot.setObjectName("AddHintDot")
        add_hint_layout.addWidget(add_hint_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.add_hint_label = QLabel("Click or drag on the screen to add it  ·  Esc to cancel")
        self.add_hint_label.setObjectName("AddHintLabel")
        add_hint_layout.addWidget(self.add_hint_label, 1)
        self.add_hint_frame.hide()
        self.main_layout.addWidget(self.add_hint_frame)

        self.response_card = QFrame()
        self.response_card.setObjectName("ResponseCard")
        self.response_layout = QVBoxLayout(self.response_card)
        self.response_layout.setContentsMargins(0, 10, 0, 0)
        self.response_layout.setSpacing(6)

        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        self.provider_tag = QLabel("RESPONSE")
        self.provider_tag.setObjectName("ResponseMeta")
        meta_layout.addWidget(self.provider_tag)
        meta_layout.addStretch()

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("CopyButton")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_response)
        meta_layout.addWidget(self.copy_btn)
        self.response_layout.addLayout(meta_layout)

        self.response_text = QTextEdit()
        self.response_text.setObjectName("ResponseText")
        self.response_text.setReadOnly(True)
        self.response_text.setFrameShape(QFrame.Shape.NoFrame)
        self.response_text.setContentsMargins(0, 0, 0, 0)
        self.response_text.document().setDocumentMargin(0)
        self.response_text.document().setDefaultStyleSheet(RESPONSE_DOCUMENT_STYLE)
        self.response_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.response_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.response_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.response_text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.response_text.setFixedHeight(24)
        self.response_text.document().documentLayout().documentSizeChanged.connect(
            self._schedule_response_fit
        )
        self.response_layout.addWidget(self.response_text)

        self.main_layout.addWidget(self.response_card)
        self.response_card.hide()

        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.main_layout.addWidget(self.error_label)

        # The header and empty panel space are drag handles.  Interactive
        # children (buttons, inputs, response text) keep their own cursors and
        # mouse behaviour.
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header_widget.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header_widget.setToolTip("Drag to move this window")

    def _populate_chips(self) -> None:
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        count = len(self.selection_manager.items)
        if count > 2:
            suggestions = [
                "Compare items",
                "Summarize all",
                "Extract text",
                "List differences",
            ]
        elif count == 2:
            suggestions = [
                "Compare items",
                "Summarize both",
                "Extract text",
                "What's the difference?",
            ]
        else:
            suggestions = ["Summarize", "Explain", "Extract text", "Translate", "What is this?"]

        for suggestion in suggestions:
            button = QPushButton(suggestion)
            button.setObjectName("SuggestionChip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, text=suggestion: self._on_chip_clicked(text)
            )
            self.chips_layout.addWidget(button)
        self.chips_layout.addStretch()

    def _on_selection_changed(self) -> None:
        while self.thumbs_layout.count():
            item = self.thumbs_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        for selection_item in self.selection_manager.items[:2]:
            chip = ThumbnailChip(selection_item)
            chip.remove_requested.connect(self.selection_manager.remove_item)
            self.thumbs_layout.addWidget(chip)

        hidden_count = len(self.selection_manager.items) - 2
        if hidden_count > 0:
            more = QLabel(f"+{hidden_count}")
            more.setObjectName("ThumbnailMore")
            more.setToolTip(f"{hidden_count} more selection{'s' if hidden_count != 1 else ''}")
            self.thumbs_layout.addWidget(more)

        self._populate_chips()
        self.adjustSize()

    def _on_add_toggled(self, checked: bool) -> None:
        self.selection_manager.set_adding_content(checked)

    def _on_adding_content_changed(self, adding: bool) -> None:
        """Reflect add-area mode in the button and the inline hint."""
        self.add_content_btn.blockSignals(True)
        self.add_content_btn.setChecked(adding)
        self.add_content_btn.blockSignals(False)
        self.add_content_btn.setText("Selecting…" if adding else "+ Add")
        self.add_content_btn.setToolTip(
            "Click the button or press Esc to stop adding"
            if adding
            else "Add another area from the screen"
        )
        self.add_hint_frame.setVisible(adding)
        self.chips_widget.setVisible(not adding)
        self.adjustSize()
        self._panel_resize_timer.start()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001 - Qt virtual signature
        if event.key() == Qt.Key.Key_Escape and self.selection_manager.is_adding_content:
            self.selection_manager.set_adding_content(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_chip_clicked(self, prompt: str) -> None:
        self.prompt_input.setText(prompt)
        self._on_submit_prompt()

    def _on_submit_prompt(self) -> None:
        text = self.prompt_input.text().strip()
        if not text:
            return
        self._run_prompt(text)

    def _run_prompt(self, text: str) -> None:
        images = self.selection_manager.images
        if not images:
            self.response_card.show()
            self.error_label.hide()
            self._awaiting_first_chunk = False
            self._response_raw = ""
            self._set_response_text("Select something on screen first.")
            return

        self.response_card.show()
        self.error_label.hide()
        self._awaiting_first_chunk = True
        self._response_raw = ""
        self._set_response_text("Thinking…")
        self.prompt_input.clear()

        self._stop_worker()

        owner = QGuiApplication.instance() or self
        worker = AIWorkerThread(self.provider, text, images, owner)
        self._worker = worker
        worker.chunk_received.connect(self._append_chunk)
        worker.error_occurred.connect(self._on_ai_error)
        worker.finished_stream.connect(self._on_ai_finished)
        worker.finished.connect(self._on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        worker.start()

    def _on_worker_finished(self, worker: AIWorkerThread | None = None) -> None:
        target = worker if worker is not None else self.sender()
        if target is self._worker:
            self._worker = None
        if target is not None:
            try:
                target.deleteLater()
            except RuntimeError:
                pass

    def _stop_worker(self, wait_ms: int = 1500) -> None:
        """Stop and forget the current streaming worker, if any."""
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            if not worker.isRunning():
                return
            worker.requestInterruption()
        except RuntimeError:
            return

        for signal, slot in (
            (worker.chunk_received, self._append_chunk),
            (worker.error_occurred, self._on_ai_error),
            (worker.finished_stream, self._on_ai_finished),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

        try:
            worker.wait(wait_ms)
        except RuntimeError:
            pass

    def shutdown(self) -> None:
        """Stop streaming before the panel (and overlay) is destroyed."""
        self._stop_worker()

    @staticmethod
    def _normalize_generated_text(text: str) -> str:
        """Tidy streamed model output without destroying intentional indentation.

        Model chunks often contain CRLF, trailing spaces and runs of blank
        lines.  Those create awkward gaps in the response popover, so trim them
        here while preserving leading indentation used by code snippets.
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]

        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        collapsed: list[str] = []
        previous_blank = False
        for line in lines:
            blank = not line.strip()
            if blank and previous_blank:
                continue
            collapsed.append(line)
            previous_blank = blank
        return "\n".join(collapsed)

    def _set_response_text(self, text: str) -> None:
        self.response_text.setHtml(render_markdown(text))
        cursor = self.response_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.response_text.setTextCursor(cursor)
        self.response_text.ensureCursorVisible()
        self._schedule_response_fit()

    def _render_streaming_response(self) -> None:
        normalized = self._normalize_generated_text(self._response_raw)
        if not normalized.strip():
            return
        self._awaiting_first_chunk = False
        self._set_response_text(normalized)

    def _schedule_response_fit(self, *_args: object) -> None:
        if self.response_card.isVisible():
            self._response_fit_timer.start(0)

    def _fit_response_text(self) -> None:
        """Size the response editor to its content, up to a scrollable maximum."""
        if not self.response_card.isVisible() or not self.response_text.isVisible():
            return

        viewport_width = self.response_text.viewport().width()
        if viewport_width <= 20:
            return

        document = self.response_text.document()
        document.setTextWidth(viewport_width)
        content_height = int(math.ceil(document.size().height())) + 2
        target_height = max(24, min(content_height, 280))
        if self.response_text.height() != target_height:
            self.response_text.setFixedHeight(target_height)
        layout = self.layout()
        if layout is not None:
            layout.activate()
            target_panel_height = layout.sizeHint().height()
            # Grow immediately so streamed text is never clipped.  Shrinking
            # waits for Qt to settle its cached layout minimum, otherwise the
            # panel keeps the previous, taller size.
            if target_panel_height > self.height():
                self.resize(self.width(), target_panel_height)
        self._panel_resize_timer.start()

    def _finalize_panel_size(self) -> None:
        if not self.response_card.isVisible():
            return
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        target_panel_height = max(
            layout.sizeHint().height(),
            layout.minimumSize().height(),
        )
        if self.height() != target_panel_height:
            self.resize(self.width(), target_panel_height)

    def _append_chunk(self, chunk: str) -> None:
        self._response_raw += chunk
        self._render_streaming_response()

    def _on_ai_error(self, err: str) -> None:
        self._awaiting_first_chunk = False
        if not self._normalize_generated_text(self._response_raw).strip():
            self._set_response_text("The request could not be completed.")
        else:
            self._render_streaming_response()
        self.error_label.setText(err)
        self.error_label.show()
        self.adjustSize()

    def _on_ai_finished(self) -> None:
        self._awaiting_first_chunk = False
        if not self._normalize_generated_text(self._response_raw).strip():
            self._set_response_text("No response was returned.")
        else:
            self._render_streaming_response()
        self.adjustSize()

    def _copy_response(self) -> None:
        text = self.response_text.toPlainText()
        clipboard: QClipboard | None = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            self.copy_btn.setText("Copied")
            self._copy_timer.start(1500)

    def _reset_copy_button(self) -> None:
        self.copy_btn.setText("Copy")
