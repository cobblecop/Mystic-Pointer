"""Settings dialog for Mystic Pointer."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mystic_pointer.config import AppConfig
from mystic_pointer.core.screen_capture import is_wayland_session
from mystic_pointer.ui.style import (
    settings_palette,
    settings_stylesheet,
    system_is_dark,
)
from mystic_pointer.ui.widgets import ComboBox, ToggleSwitch

if TYPE_CHECKING:
    from mystic_pointer.ai.model_catalog import ModelCatalog


class _ConnectionTestSignals(QObject):
    """Relay for a connection test running on a worker thread."""

    finished = Signal(bool, str)


class _ConnectionTestTask(QRunnable):
    """Validate a provider without blocking the GUI thread.

    The network calls can take up to several seconds (or hit a timeout), so they
    must not run on the GUI thread.  The signals relay is kept alive by this
    task; if the dialog is closed meanwhile the queued signal is discarded.
    """

    def __init__(
        self,
        factory: Callable[[], Any],
        signals: _ConnectionTestSignals,
    ):
        super().__init__()
        self._factory = factory
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            provider = self._factory()
            ok, message = provider.validate_connection()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            ok, message = False, str(exc)

        try:
            self._signals.finished.emit(ok, message)
        except RuntimeError:
            # The dialog (and this relay) were destroyed while the test ran.
            pass


class _ModelFetchSignals(QObject):
    """Relay for a model-discovery request running on a worker thread."""

    finished = Signal(object)  # ModelCatalog


class _ModelFetchTask(QRunnable):
    """Fetch the provider's model catalog without blocking the dialog."""

    def __init__(
        self,
        factory: Callable[[], Any],
        signals: _ModelFetchSignals,
    ):
        super().__init__()
        self._factory = factory
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            catalog = self._factory()
        except Exception as exc:  # noqa: BLE001 - surfaced in the dialog
            from mystic_pointer.ai.model_catalog import ModelCatalog

            catalog = ModelCatalog(error=str(exc))

        try:
            self._signals.finished.emit(catalog)
        except RuntimeError:
            # The dialog (and this relay) were destroyed while fetching.
            pass


class SettingsDialog(QDialog):
    """Configuration dialog for Mystic Pointer."""

    settings_saved = Signal(AppConfig)

    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._test_signals: _ConnectionTestSignals | None = None
        self._testing = False
        self._ui_ready = False

        # Model discovery state (one in-flight request per provider).
        self._model_generation = {"gemini": 0, "openai": 0}
        self._model_fetch_signals: dict[tuple[str, int], _ModelFetchSignals] = {}
        self._model_query: dict[str, tuple[str, ...]] = {}
        self._model_timers: dict[str, QTimer] = {}
        for provider in ("gemini", "openai"):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(1000)
            timer.timeout.connect(lambda p=provider: self._refresh_models(p))
            self._model_timers[provider] = timer

        self.setWindowTitle("Preferences")
        self._dark = system_is_dark()
        self.setStyleSheet(settings_stylesheet(self._dark))
        self.setPalette(settings_palette(self._dark))
        self.resize(820, 700)
        self.setMinimumSize(720, 540)

        self._setup_ui()
        self._load_values()

        if is_wayland_session():
            # No compositor exposes global cursor position to Wayland clients.
            self.wiggle_enable_cb.setChecked(False)
            self.wiggle_enable_cb.setEnabled(False)
            self.wiggle_enable_cb.setToolTip("Cursor wiggle is unavailable on Wayland.")
            self.sens_slider.setEnabled(False)
            self.sens_slider.setToolTip("Cursor wiggle is unavailable on Wayland.")
            self.sens_val_label.setEnabled(False)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Preferences")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(196)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.sidebar.addItem("General")
        self.sidebar.addItem("AI Providers")
        body.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_general_page())
        self.pages.addWidget(self._build_ai_page())
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setProperty("suggested", True)
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_and_close)
        footer.addWidget(save_btn)

        root.addLayout(footer)

    def _create_scroll_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("PageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page, layout

    def _add_section(
        self,
        layout: QVBoxLayout,
        title: str,
    ) -> tuple[QWidget, QVBoxLayout]:
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(7)

        section_title = QLabel(title)
        section_title.setObjectName("SectionTitle")
        wrapper_layout.addWidget(section_title)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        wrapper_layout.addWidget(card)

        layout.addWidget(wrapper)
        return wrapper, card_layout

    def _add_row(
        self,
        card_layout: QVBoxLayout,
        title: str,
        subtitle: str,
        control: QWidget,
        last: bool = False,
    ) -> QLabel | None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 12, 16, 12)
        row_layout.setSpacing(16)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("RowTitle")
        text_layout.addWidget(title_label)

        subtitle_label: QLabel | None = None
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("RowSubtitle")
            subtitle_label.setWordWrap(True)
            text_layout.addWidget(subtitle_label)

        row_layout.addLayout(text_layout, 1)
        row_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(row)

        if not last:
            self._add_separator(card_layout)
        return subtitle_label

    def _add_field_block(
        self,
        card_layout: QVBoxLayout,
        title: str,
        subtitle: str,
        field: QWidget,
        last: bool = False,
    ) -> tuple[QVBoxLayout, QLabel | None]:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName("RowTitle")
        layout.addWidget(title_label)

        subtitle_label: QLabel | None = None
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("RowSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)

        layout.addWidget(field)
        card_layout.addWidget(block)

        if not last:
            self._add_separator(card_layout)
        return layout, subtitle_label

    def _add_slider_block(
        self,
        card_layout: QVBoxLayout,
        title: str,
        subtitle: str,
        slider: QSlider,
        value_label: QLabel,
        hint_left: str | None = None,
        hint_right: str | None = None,
        last: bool = False,
    ) -> QVBoxLayout:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("RowTitle")
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(value_label)
        layout.addLayout(header)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("RowSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)

        layout.addWidget(slider)

        if hint_left or hint_right:
            hints = QHBoxLayout()
            hints.setSpacing(8)
            if hint_left:
                left = QLabel(hint_left)
                left.setObjectName("HintLabel")
                hints.addWidget(left)
            hints.addStretch()
            if hint_right:
                right = QLabel(hint_right)
                right.setObjectName("HintLabel")
                hints.addWidget(right)
            layout.addLayout(hints)

        card_layout.addWidget(block)
        if not last:
            self._add_separator(card_layout)
        return layout

    def _add_separator(self, card_layout: QVBoxLayout) -> None:
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(16, 0, 16, 0)
        wrapper_layout.setSpacing(0)
        separator = QFrame()
        separator.setObjectName("Separator")
        separator.setFixedHeight(1)
        wrapper_layout.addWidget(separator)
        card_layout.addWidget(wrapper)

    def _add_note(self, card_layout: QVBoxLayout, text: str) -> None:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(16, 10, 16, 12)
        note = QLabel(text)
        note.setObjectName("WarningLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        card_layout.addWidget(wrapper)

    @staticmethod
    def _make_model_field(combo: QComboBox, refresh_button: QPushButton) -> QWidget:
        field = QWidget()
        layout = QHBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(combo, 1)
        layout.addWidget(refresh_button)
        return field

    def _build_general_page(self) -> QWidget:
        page, layout = self._create_scroll_page()

        _, activation_card = self._add_section(layout, "Activation")

        self.wiggle_enable_cb = ToggleSwitch()
        self.wiggle_enable_cb.setAccessibleName("Allow cursor wiggle")
        self.wiggle_enable_cb.setToolTip(
            "Quickly move your cursor left and right for a moment to activate."
        )
        self._add_row(
            activation_card,
            "Cursor wiggle",
            "Quickly move the pointer left and right to activate.",
            self.wiggle_enable_cb,
        )

        self.sens_val_label = QLabel("5")
        self.sens_val_label.setObjectName("ValueLabel")
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(1, 10)
        self.sens_slider.setValue(5)
        self.sens_slider.valueChanged.connect(lambda value: self.sens_val_label.setText(str(value)))
        self._add_slider_block(
            activation_card,
            "Wiggle sensitivity",
            "Higher values trigger the gesture sooner.",
            self.sens_slider,
            self.sens_val_label,
            hint_left="Less sensitive",
            hint_right="More sensitive",
            last=not is_wayland_session(),
        )
        if is_wayland_session():
            self._add_note(
                activation_card,
                "Cursor wiggle is unavailable on Wayland because apps cannot read "
                "the global pointer position. Use the system shortcut instead.",
            )

        _, interface_card = self._add_section(layout, "Interface")

        self.hotkey_input = QLineEdit("Ctrl+Alt+G")
        self.hotkey_input.setFixedWidth(188)
        self.hotkey_input.setPlaceholderText("Ctrl+Alt+G")
        self._add_row(
            interface_card,
            "Activation shortcut",
            "Global shortcut on X11 and Windows. On Wayland, bind it in system settings.",
            self.hotkey_input,
        )

        self.smart_detect_cb = ToggleSwitch()
        self.smart_detect_cb.setAccessibleName("Highlight images")
        self._add_row(
            interface_card,
            "Highlight images",
            "Brighten images as you move across the screen; text and UI stay dimmed.",
            self.smart_detect_cb,
        )

        self.opacity_val_label = QLabel("45%")
        self.opacity_val_label.setObjectName("ValueLabel")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 80)
        self.opacity_slider.setValue(45)
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_val_label.setText(f"{value}%")
        )
        self._add_slider_block(
            interface_card,
            "Background dimming",
            "Control how much the desktop is dimmed behind your selection.",
            self.opacity_slider,
            self.opacity_val_label,
            last=True,
        )

        footer_note = QLabel("Your configuration is stored locally on this device.")
        footer_note.setObjectName("HintLabel")
        footer_note.setWordWrap(True)
        layout.addWidget(footer_note)
        return page

    def _build_ai_page(self) -> QWidget:
        page, layout = self._create_scroll_page()

        _, provider_card = self._add_section(layout, "Provider")

        self.provider_combo = ComboBox()
        self.provider_combo.addItem("Gemini", "gemini")
        self.provider_combo.addItem("OpenAI-compatible / Ollama", "openai")
        self.provider_combo.addItem("Demo (offline)", "mock")
        self.provider_combo.setMinimumWidth(250)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.provider_hint = self._add_row(
            provider_card,
            "AI provider",
            "Cloud models from the Gemini API. Requires an API key.",
            self.provider_combo,
            last=True,
        )

        self.gemini_group, gemini_card = self._add_section(layout, "Gemini")

        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key_input.setPlaceholderText("Gemini API key")
        self.gemini_key_input.textChanged.connect(lambda: self._schedule_model_refresh("gemini"))
        self.gemini_key_input.editingFinished.connect(lambda: self._refresh_models("gemini"))
        gemini_key_field = QWidget()
        gemini_key_layout = QHBoxLayout(gemini_key_field)
        gemini_key_layout.setContentsMargins(0, 0, 0, 0)
        gemini_key_layout.setSpacing(8)
        gemini_key_layout.addWidget(self.gemini_key_input, 1)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setProperty("flat", True)
        self.show_key_btn.setFixedWidth(58)
        self.show_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_key_btn.clicked.connect(
            lambda: self._toggle_key_visibility(self.gemini_key_input, self.show_key_btn)
        )
        gemini_key_layout.addWidget(self.show_key_btn)
        self._add_field_block(
            gemini_card,
            "API key",
            "Stored locally in your configuration.",
            gemini_key_field,
        )

        self.gemini_model_combo = ComboBox()
        self.gemini_model_combo.setToolTip(
            "Vision-capable models available to the configured API key."
        )
        self.gemini_refresh_btn = QPushButton("Refresh")
        self.gemini_refresh_btn.setProperty("flat", True)
        self.gemini_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_refresh_btn.setToolTip("Refresh available multimodal models")
        self.gemini_refresh_btn.clicked.connect(lambda: self._refresh_models("gemini", force=True))
        gemini_model_layout, _ = self._add_field_block(
            gemini_card,
            "Model",
            "Only models that accept image input are listed.",
            self._make_model_field(self.gemini_model_combo, self.gemini_refresh_btn),
        )
        self.gemini_model_status = self._create_status_label()
        gemini_model_layout.addWidget(self.gemini_model_status)

        self.test_gemini_btn = QPushButton("Test connection")
        self.test_gemini_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_gemini_btn.clicked.connect(self._test_gemini)
        self._add_row(
            gemini_card,
            "Connection",
            "Verify the key and the selected model.",
            self.test_gemini_btn,
            last=True,
        )

        self.openai_group, openai_card = self._add_section(layout, "OpenAI-compatible endpoint")

        self.openai_url_input = QLineEdit()
        self.openai_url_input.setPlaceholderText("http://localhost:11434/v1")
        self.openai_url_input.textChanged.connect(lambda: self._schedule_model_refresh("openai"))
        self.openai_url_input.editingFinished.connect(lambda: self._refresh_models("openai"))
        self._add_field_block(
            openai_card,
            "Base URL",
            "The endpoint root, including /v1 where required.",
            self.openai_url_input,
        )

        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_input.setPlaceholderText("Optional for local endpoints")
        self.openai_key_input.textChanged.connect(lambda: self._schedule_model_refresh("openai"))
        self.openai_key_input.editingFinished.connect(lambda: self._refresh_models("openai"))
        openai_key_field = QWidget()
        openai_key_layout = QHBoxLayout(openai_key_field)
        openai_key_layout.setContentsMargins(0, 0, 0, 0)
        openai_key_layout.setSpacing(8)
        openai_key_layout.addWidget(self.openai_key_input, 1)
        self.openai_show_key_btn = QPushButton("Show")
        self.openai_show_key_btn.setProperty("flat", True)
        self.openai_show_key_btn.setFixedWidth(58)
        self.openai_show_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.openai_show_key_btn.clicked.connect(
            lambda: self._toggle_key_visibility(self.openai_key_input, self.openai_show_key_btn)
        )
        openai_key_layout.addWidget(self.openai_show_key_btn)
        self._add_field_block(
            openai_card,
            "API key",
            "Optional for local models; required by most cloud endpoints.",
            openai_key_field,
        )

        self.openai_model_combo = ComboBox()
        self.openai_model_combo.setEditable(True)
        self.openai_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.openai_model_combo.setPlaceholderText("llama3.2-vision or gpt-4o")
        self.openai_model_combo.setToolTip(
            "Vision-capable models offered by the endpoint. You can also type a "
            "model name that is not listed."
        )
        self.openai_refresh_btn = QPushButton("Refresh")
        self.openai_refresh_btn.setProperty("flat", True)
        self.openai_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.openai_refresh_btn.setToolTip("Refresh available multimodal models")
        self.openai_refresh_btn.clicked.connect(lambda: self._refresh_models("openai", force=True))
        openai_model_layout, _ = self._add_field_block(
            openai_card,
            "Model",
            "Vision-capable models offered by this endpoint.",
            self._make_model_field(self.openai_model_combo, self.openai_refresh_btn),
        )
        self.openai_model_status = self._create_status_label()
        openai_model_layout.addWidget(self.openai_model_status)

        self.test_openai_btn = QPushButton("Test connection")
        self.test_openai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_openai_btn.clicked.connect(self._test_openai)
        self._add_row(
            openai_card,
            "Connection",
            "Verify the endpoint and the selected model.",
            self.test_openai_btn,
            last=True,
        )

        footer_note = QLabel("Requests go directly from this device to the provider you choose.")
        footer_note.setObjectName("HintLabel")
        footer_note.setWordWrap(True)
        layout.addWidget(footer_note)
        return page

    def _load_values(self) -> None:
        self.wiggle_enable_cb.setChecked(self.config.wiggle_enabled)
        self.sens_slider.setValue(self.config.wiggle_sensitivity)
        self.sens_val_label.setText(str(self.config.wiggle_sensitivity))
        self.hotkey_input.setText(self.config.hotkey)
        self.smart_detect_cb.setChecked(self.config.smart_detection)
        self.opacity_slider.setValue(int(self.config.dim_opacity * 100))
        self.opacity_val_label.setText(f"{int(self.config.dim_opacity * 100)}%")

        idx = self.provider_combo.findData(self.config.provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        self.gemini_key_input.setText(self.config.gemini_api_key)
        self._seed_gemini_models(self.config.gemini_model)

        self.openai_url_input.setText(self.config.openai_base_url)
        self.openai_key_input.setText(self.config.openai_api_key)
        self.openai_model_combo.setCurrentText(self.config.openai_model)

        self._on_provider_changed()

        self._ui_ready = True
        QTimer.singleShot(0, self._refresh_models_if_ready)

    def _on_provider_changed(self) -> None:
        provider = self.provider_combo.currentData()
        self.gemini_group.setVisible(provider == "gemini")
        self.openai_group.setVisible(provider == "openai")
        if self.provider_hint is not None:
            hints = {
                "gemini": "Cloud models from the Gemini API. Requires an API key.",
                "openai": "Any OpenAI-compatible endpoint, including a local Ollama server.",
                "mock": "Sample responses for exploring the interface without a provider.",
            }
            self.provider_hint.setText(hints.get(provider, ""))
        if self._ui_ready and provider in self._model_generation:
            self._refresh_models(provider)

    def _toggle_key_visibility(self, field: QLineEdit, button: QPushButton) -> None:
        if field.echoMode() == QLineEdit.EchoMode.Password:
            field.setEchoMode(QLineEdit.EchoMode.Normal)
            button.setText("Hide")
        else:
            field.setEchoMode(QLineEdit.EchoMode.Password)
            button.setText("Show")

    # --- Model discovery ---

    @staticmethod
    def _create_status_label() -> QLabel:
        label = QLabel("")
        label.setObjectName("StatusLabel")
        label.setWordWrap(True)
        return label

    def _seed_gemini_models(self, selected: str) -> None:
        from mystic_pointer.ai.model_catalog import DEFAULT_GEMINI_MODELS

        items = [(model_id, name, "") for model_id, name in DEFAULT_GEMINI_MODELS]
        self._fill_gemini_models(items, selected)

    def _fill_gemini_models(
        self,
        items: list[tuple[str, str, str]],
        selected: str,
    ) -> None:
        from mystic_pointer.ai.model_catalog import gemini_model_is_legacy

        combo = self.gemini_model_combo
        combo.blockSignals(True)
        combo.clear()
        for model_id, display_name, description in items:
            label = display_name if display_name and display_name != model_id else model_id
            tooltip = model_id if not description else f"{model_id}\n{description}"
            if gemini_model_is_legacy(model_id):
                label = f"{label} (legacy)"
                tooltip += "\nMay no longer be available to new API keys; prefer a -latest model."
            combo.addItem(label, model_id)
            combo.setItemData(combo.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)

        # Keep a saved model selectable even if the provider no longer lists it;
        # silently switching the user's configuration would be worse.
        if selected and combo.findData(selected) < 0:
            label = selected
            tooltip = "Saved model (not reported as vision-capable by the provider)"
            if gemini_model_is_legacy(selected):
                label = f"{selected} (legacy)"
                tooltip += "\nMay no longer be available to new API keys; prefer a -latest model."
            combo.insertItem(0, label, selected)
            combo.setItemData(0, tooltip, Qt.ItemDataRole.ToolTipRole)

        index = combo.findData(selected) if selected else -1
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _schedule_model_refresh(self, provider: str) -> None:
        timer = self._model_timers.get(provider)
        if timer is not None:
            timer.start()

    def _refresh_models_if_ready(self) -> None:
        provider = self.provider_combo.currentData()
        if provider in self._model_generation:
            self._refresh_models(provider)

    def _refresh_models(self, provider: str, force: bool = False) -> None:
        """Start a background discovery request for the active provider."""
        if provider != self.provider_combo.currentData():
            return

        if provider == "gemini":
            api_key = self.gemini_key_input.text().strip()
            if not api_key:
                self._set_model_status("gemini", "Enter a Gemini API key to load available models.")
                return
            token = (api_key,)
            if not force and self._model_query.get("gemini") == token:
                return
            self._model_query["gemini"] = token
            from mystic_pointer.ai.model_catalog import fetch_gemini_models

            factory: Callable[[], Any] = partial(fetch_gemini_models, api_key)
        else:
            base_url = self.openai_url_input.text().strip()
            api_key = self.openai_key_input.text().strip()
            if not base_url:
                self._set_model_status("openai", "Enter a base URL to load available models.")
                return
            token = (base_url, api_key)
            if not force and self._model_query.get("openai") == token:
                return
            self._model_query["openai"] = token
            from mystic_pointer.ai.model_catalog import fetch_openai_models

            factory = partial(fetch_openai_models, base_url, api_key)

        generation = self._model_generation[provider] + 1
        self._model_generation[provider] = generation
        self._set_model_loading(provider, True)

        signals = _ModelFetchSignals()
        signals.finished.connect(
            lambda catalog, p=provider, g=generation: self._on_models_loaded(p, g, catalog)
        )
        self._model_fetch_signals[(provider, generation)] = signals
        QThreadPool.globalInstance().start(_ModelFetchTask(factory, signals))

    def _on_models_loaded(
        self,
        provider: str,
        generation: int,
        catalog: ModelCatalog,
    ) -> None:
        signals = self._model_fetch_signals.pop((provider, generation), None)
        if signals is not None:
            try:
                signals.finished.disconnect()
            except RuntimeError:
                pass

        if generation != self._model_generation[provider]:
            # A newer request for this provider is already in flight.
            return

        self._set_model_loading(provider, False)
        if provider == "gemini":
            self._apply_gemini_catalog(catalog)
        else:
            self._apply_openai_catalog(catalog)

    def _apply_gemini_catalog(self, catalog: ModelCatalog) -> None:
        selected = self.gemini_model_combo.currentData()
        if not isinstance(selected, str) or not selected:
            selected = self.config.gemini_model

        if catalog.models:
            items = [(model.id, model.display_name, model.description) for model in catalog.models]
            self._fill_gemini_models(items, selected)

        if catalog.error:
            self._set_model_status("gemini", f"Could not load models: {catalog.error}", error=True)
        elif catalog.models:
            count = len(catalog.models)
            self._set_model_status(
                "gemini",
                f"{count} vision-capable model{'s' if count != 1 else ''} available.",
            )
        else:
            self._set_model_status(
                "gemini",
                "No vision-capable models were found for this API key.",
                error=True,
            )

    def _apply_openai_catalog(self, catalog: ModelCatalog) -> None:
        combo = self.openai_model_combo
        current = combo.currentText().strip() or self.config.openai_model

        combo.blockSignals(True)
        combo.clear()
        for model in catalog.models:
            combo.addItem(model.id)
            combo.setItemData(combo.count() - 1, model.id, Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentText(current)
        if not current and combo.count():
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

        if catalog.error:
            self._set_model_status("openai", f"Could not load models: {catalog.error}", error=True)
        elif catalog.models:
            count = len(catalog.models)
            self._set_model_status(
                "openai",
                f"{count} vision-capable model{'s' if count != 1 else ''} available.",
            )
        else:
            self._set_model_status(
                "openai", "No vision-capable models were found at this endpoint.", error=True
            )

    def _set_model_loading(self, provider: str, loading: bool) -> None:
        if provider == "gemini":
            combo = self.gemini_model_combo
            button = self.gemini_refresh_btn
        else:
            combo = self.openai_model_combo
            button = self.openai_refresh_btn
        combo.setEnabled(not loading)
        button.setEnabled(not loading)
        if loading:
            self._set_model_status(provider, "Loading models…")

    def _set_model_status(self, provider: str, text: str, error: bool = False) -> None:
        label = self.gemini_model_status if provider == "gemini" else self.openai_model_status
        label.setProperty("error", error)
        label.setText(text)
        label.style().unpolish(label)
        label.style().polish(label)

    # --- Connection tests ---

    def _test_gemini(self) -> None:
        key = self.gemini_key_input.text().strip()
        model = str(self.gemini_model_combo.currentData() or "gemini-flash-latest")
        if not key:
            QMessageBox.warning(
                self,
                "API Key Missing",
                "Enter a Gemini API key before testing the connection.",
            )
            return

        from mystic_pointer.ai.gemini import GeminiProvider

        self._start_connection_test(
            self.test_gemini_btn,
            lambda: GeminiProvider(api_key=key, model=model),
            "Could not reach Gemini",
        )

    def _test_openai(self) -> None:
        url = self.openai_url_input.text().strip()
        key = self.openai_key_input.text().strip()
        model = self.openai_model_combo.currentText().strip()
        if not url:
            QMessageBox.warning(
                self,
                "Base URL Missing",
                "Enter the base URL of your OpenAI-compatible endpoint.",
            )
            return

        from mystic_pointer.ai.openai_compat import OpenAICompatProvider

        self._start_connection_test(
            self.test_openai_btn,
            lambda: OpenAICompatProvider(base_url=url, api_key=key, model=model),
            "Could not reach endpoint",
        )

    def _start_connection_test(
        self,
        button: QPushButton,
        factory: Callable[[], Any],
        error_title: str,
    ) -> None:
        """Run ``factory().validate_connection()`` without blocking the dialog."""
        if self._testing:
            return
        self._testing = True

        default_text = button.text()
        button.setText("Testing…")
        for btn in (self.test_gemini_btn, self.test_openai_btn):
            btn.setEnabled(False)

        signals = _ConnectionTestSignals()
        signals.finished.connect(
            lambda ok, message: self._on_connection_test_finished(
                button, signals, default_text, ok, message, error_title
            )
        )
        # Keep a reference: QThreadPool only owns the runnable, not the relay.
        self._test_signals = signals
        QThreadPool.globalInstance().start(_ConnectionTestTask(factory, signals))

    def _on_connection_test_finished(
        self,
        button: QPushButton,
        signals: _ConnectionTestSignals,
        default_text: str,
        ok: bool,
        message: str,
        error_title: str,
    ) -> None:
        self._testing = False
        self._test_signals = None

        # Break the closure -> signals -> connection cycle.
        try:
            signals.finished.disconnect()
        except RuntimeError:
            pass

        button.setText(default_text)
        for btn in (self.test_gemini_btn, self.test_openai_btn):
            btn.setEnabled(True)

        if ok:
            if button is self.test_gemini_btn:
                self._refresh_models("gemini", force=True)
            elif button is self.test_openai_btn:
                self._refresh_models("openai", force=True)

        if not self.isVisible():
            return
        if ok:
            QMessageBox.information(self, "Connection successful", message)
        else:
            QMessageBox.warning(self, "Connection failed", f"{error_title}: {message}")

    def _save_and_close(self) -> None:
        if not is_wayland_session():
            # The switch is disabled on Wayland; preserve the user's saved
            # preference so it still applies when running under X11.
            self.config.wiggle_enabled = self.wiggle_enable_cb.isChecked()
        self.config.wiggle_sensitivity = self.sens_slider.value()
        self.config.hotkey = self.hotkey_input.text().strip()
        self.config.smart_detection = self.smart_detect_cb.isChecked()
        self.config.dim_opacity = self.opacity_slider.value() / 100.0

        self.config.provider = self.provider_combo.currentData()
        self.config.gemini_api_key = self.gemini_key_input.text().strip()
        gemini_model = self.gemini_model_combo.currentData()
        self.config.gemini_model = str(
            gemini_model or self.gemini_model_combo.currentText()
        ).strip()
        self.config.openai_base_url = self.openai_url_input.text().strip()
        self.config.openai_api_key = self.openai_key_input.text().strip()
        self.config.openai_model = self.openai_model_combo.currentText().strip()

        self.config.save()
        self.settings_saved.emit(self.config)
        self.accept()
