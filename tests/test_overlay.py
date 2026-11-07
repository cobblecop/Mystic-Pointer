"""Tests for the seamless activation reveal and hidden prompt panel."""

from __future__ import annotations

import time
from pathlib import Path
from typing import cast

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mystic_pointer.ai.mock import MockProvider
from mystic_pointer.config import AppConfig
from mystic_pointer.core import selection_actions
from mystic_pointer.core.capture_service import CaptureService
from mystic_pointer.core.screen_capture import ScreenCaptureResult
from mystic_pointer.ui.action_bar import SelectionActionBar
from mystic_pointer.ui.overlay import MysticPointerOverlay

_app = cast(QApplication, QApplication.instance() or QApplication([]))


def _make_overlay(
    provider: MockProvider | None = None,
    config: AppConfig | None = None,
) -> MysticPointerOverlay:
    screen = _app.primaryScreen()
    assert screen is not None
    return MysticPointerOverlay(
        config or AppConfig(),
        provider or MockProvider(),
        screen,
        CaptureService(),
    )


def test_prompt_panel_is_hidden_during_activation() -> None:
    overlay = _make_overlay()
    overlay._ensure_panel()

    assert overlay.panel is not None
    # The panel is a child of the overlay.  It must be explicitly hidden so Qt
    # does not map it together with the overlay and make it "pop up" from the
    # bottom of the screen before the user has selected anything.
    assert overlay.panel.isHidden()
    overlay.deleteLater()


def test_activation_reveal_reaches_full_strength() -> None:
    overlay = _make_overlay()
    overlay._start_reveal()

    assert overlay._active
    assert overlay._reveal == 0.0
    assert overlay._reveal_anim is not None

    QTest.qWait(350)

    assert overlay._reveal == 1.0
    assert overlay._reveal_anim is None
    overlay.deleteLater()


def test_activation_waits_for_capture_before_fading() -> None:
    overlay = _make_overlay()
    overlay._map_guard_ms = 180
    overlay._shown_at = time.monotonic() - 0.5
    try:
        # The capture is still in flight: the overlay must stay fully
        # transparent, because the screenshot would otherwise contain the dim
        # layer and the hint pill.
        overlay._capture_ready = False
        overlay._maybe_start_reveal()
        assert not overlay._active
        assert overlay._reveal_anim is None

        # A finished capture starts the fade as soon as the map guard is over.
        overlay._capture_ready = True
        overlay._maybe_start_reveal()
        assert overlay._active
        assert overlay._reveal_anim is not None
    finally:
        overlay.dismiss()
        overlay.deleteLater()


def test_activation_waits_for_map_guard_after_capture() -> None:
    overlay = _make_overlay()
    overlay._map_guard_ms = 180
    overlay._capture_ready = True
    overlay._shown_at = time.monotonic()
    try:
        overlay._maybe_start_reveal()
        assert not overlay._active
        assert overlay._guard_timer.isActive()
        assert 0 < overlay._reveal_delay_ms() <= 180

        overlay._shown_at = time.monotonic() - 0.5
        overlay._maybe_start_reveal()
        assert overlay._active
    finally:
        overlay.dismiss()
        overlay.deleteLater()


def test_work_area_origin_accounts_for_the_top_bar() -> None:
    overlay = _make_overlay()
    overlay._work_area_mode = True
    overlay.screen_geometry = QRect(0, 0, 1920, 1080)
    try:
        # GNOME places a maximized surface below the top bar but Qt reports
        # (0, 0) for it; the missing height is the offset.
        overlay.resize(1920, 1048)
        overlay._update_origin()
        assert overlay._origin == QPoint(0, 32)

        # A second monitor starts further right; its own origin is respected.
        overlay.screen_geometry = QRect(1920, 0, 1920, 1080)
        overlay.resize(1920, 1048)
        overlay._update_origin()
        assert overlay._origin == QPoint(1920, 32)

        # Without the work-area workaround the surface covers the screen.
        overlay._work_area_mode = False
        overlay._update_origin()
        assert overlay._origin == QPoint(1920, 0)
    finally:
        overlay.dismiss()
        overlay.deleteLater()


def test_escape_cancels_add_mode_before_closing_overlay() -> None:
    overlay = _make_overlay()
    overlay._ensure_panel()
    assert overlay.panel is not None
    try:
        overlay.selection_manager.set_adding_content(True)
        assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor
        # The panel follows the shared selection state.
        assert overlay.panel.add_content_btn.isChecked()

        escape = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.keyPressEvent(escape)

        assert not overlay._is_closing
        assert not overlay.selection_manager.is_adding_content
        assert not overlay.panel.add_content_btn.isChecked()
    finally:
        overlay.deleteLater()


def test_dismiss_during_activation_reveal_is_safe() -> None:
    overlay = _make_overlay()
    overlay._start_reveal()
    # Close before the fade/guard timer fires; pending steps must be cancelled
    # rather than calling into a deleted widget.
    overlay.dismiss()
    QTest.qWait(250)


def _install_frame(overlay: MysticPointerOverlay, image: Image.Image) -> None:
    overlay.capture_result = ScreenCaptureResult(
        image=image,
        screen_geometry=overlay.screen_geometry,
    )
    overlay._build_frame_pixmap()


def _render(overlay: MysticPointerOverlay) -> QImage:
    target = QImage(overlay.size(), QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    overlay.render(target)
    return target


def test_frame_pixmap_crops_the_work_area() -> None:
    overlay = _make_overlay()
    overlay._work_area_mode = False
    overlay.screen_geometry = QRect(0, 0, 300, 240)
    try:
        overlay.resize(300, 200)
        # The overlay starts below the top bar, so its frame starts 40 px down.
        overlay._origin = QPoint(0, 40)
        image = Image.new("RGB", (300, 240), (255, 0, 0))
        image.paste((0, 0, 255), (0, 120, 300, 240))
        _install_frame(overlay, image)

        assert overlay._frame_pixmap is not None
        assert overlay._frame_pixmap.size() == QSize(300, 200)
        assert overlay._frame_pixmap.devicePixelRatio() == 1.0
        # The overlay's top 80 px are still the red upper half, but at y=100
        # it reaches the blue lower half: the frame really starts 40 px down.
        rendered = overlay._frame_pixmap.toImage()
        assert rendered.pixelColor(10, 10).red() > 200
        assert rendered.pixelColor(10, 100).blue() > 200
        assert rendered.pixelColor(10, 100).red() < 50
    finally:
        overlay.deleteLater()


def test_frozen_frame_is_dimmed_and_holes_show_it_bright() -> None:
    overlay = _make_overlay()
    overlay._work_area_mode = False
    overlay.screen_geometry = QRect(0, 0, 300, 200)
    try:
        overlay.resize(300, 200)
        overlay._origin = QPoint(0, 0)
        _install_frame(overlay, Image.new("RGB", (300, 200), (255, 255, 255)))
        overlay._active = True
        overlay._reveal = 1.0

        # With no hover, the whole frozen frame sits under the dim layer.
        dimmed = _render(overlay).pixelColor(250, 100)
        assert 100 < dimmed.red() < 180

        # Hovering redraws the frozen frame inside the hole at full brightness;
        # the surrounding area stays dimmed.
        overlay.hovered_rect = QRect(30, 70, 80, 50)
        hovered = _render(overlay)
        assert hovered.pixelColor(70, 95).red() > 240
        assert hovered.pixelColor(250, 100).red() < 180
    finally:
        overlay.deleteLater()


def test_activation_reveal_fades_the_frozen_frame_in() -> None:
    overlay = _make_overlay()
    overlay._work_area_mode = False
    overlay.screen_geometry = QRect(0, 0, 300, 200)
    try:
        overlay.resize(300, 200)
        overlay._origin = QPoint(0, 0)
        _install_frame(overlay, Image.new("RGB", (300, 200), (255, 255, 255)))
        overlay._active = True

        overlay._reveal = 0.0
        assert _render(overlay).pixelColor(250, 100).alpha() == 0

        # Early in the fade the frozen frame is translucent: it cross-fades
        # over the live desktop instead of popping in.
        overlay._reveal = 0.25
        halfway = _render(overlay).pixelColor(250, 100)
        assert halfway.alpha() < 255
        assert halfway.red() > 0

        # It is fully opaque halfway through the dim fade, so the video stops
        # before the desktop has finished darkening.
        overlay._reveal = 0.5
        assert _render(overlay).pixelColor(250, 100).alpha() == 255

        overlay._reveal = 1.0
        assert _render(overlay).pixelColor(250, 100).alpha() == 255
    finally:
        overlay.deleteLater()


def test_dismiss_fades_the_dim_layer_before_closing() -> None:
    overlay = _make_overlay()
    closed: list[bool] = []
    overlay.overlay_closed.connect(lambda: closed.append(True))
    overlay._active = True
    overlay._reveal = 1.0

    overlay.dismiss()

    # The window stays alive while the live desktop is revealed again.
    assert overlay._dismissing
    assert not closed
    assert overlay._reveal == 1.0

    QTest.qWait(260)

    assert closed == [True]
    assert overlay._reveal < 0.1


def _prepare_action_overlay(overlay: MysticPointerOverlay) -> None:
    overlay._work_area_mode = False
    overlay.screen_geometry = QRect(0, 0, 400, 300)
    overlay._origin = QPoint(0, 0)
    overlay.resize(400, 300)
    overlay._active = True
    overlay._reveal = 1.0


def _add_action_area(overlay: MysticPointerOverlay, rect: QRect) -> None:
    image = Image.new("RGB", (400, 300), (120, 140, 160))
    overlay.capture_result = ScreenCaptureResult(
        image=image,
        screen_geometry=overlay.screen_geometry,
    )
    overlay._build_frame_pixmap()
    overlay.selection_manager.add_selection(rect, image, overlay.screen_geometry)


def test_action_bar_stays_hidden_until_something_is_selected() -> None:
    overlay = _make_overlay()
    overlay._ensure_action_bar()

    assert overlay.action_bar is not None
    assert overlay.action_bar.isHidden()
    overlay.deleteLater()


def test_multiple_selections_share_one_action_bar() -> None:
    overlay = _make_overlay()
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(40, 40, 80, 60))
        _add_action_area(overlay, QRect(200, 120, 70, 50))

        assert overlay.action_bar is not None
        assert not overlay.action_bar.isHidden()
        assert len(overlay.findChildren(SelectionActionBar)) == 1
        assert overlay._selection_union_local() == QRect(40, 40, 230, 130)
    finally:
        overlay.deleteLater()


def test_action_bar_hides_while_adding_another_area() -> None:
    overlay = _make_overlay()
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(40, 40, 80, 60))
        assert overlay.action_bar is not None
        assert not overlay.action_bar.isHidden()

        overlay.selection_manager.set_adding_content(True)
        assert overlay.action_bar.isHidden()

        overlay.selection_manager.set_adding_content(False)
        assert not overlay.action_bar.isHidden()
    finally:
        overlay.deleteLater()


def test_action_bar_sits_next_to_the_selection_union() -> None:
    overlay = _make_overlay()
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(150, 100, 100, 80))

        assert overlay.action_bar is not None
        bar_rect = overlay.action_bar.geometry()
        selection_rect = QRect(150, 100, 100, 80)
        assert not bar_rect.intersects(selection_rect)
        assert bar_rect.bottom() < selection_rect.top()
    finally:
        overlay.deleteLater()


def test_screenshot_action_saves_every_selected_area(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(selection_actions, "default_screenshot_directory", lambda: tmp_path)
    overlay = _make_overlay()
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(40, 40, 80, 60))
        _add_action_area(overlay, QRect(200, 120, 70, 50))

        overlay._take_selection_screenshots()

        assert len(list(tmp_path.glob("*.png"))) == 2
        assert overlay.action_bar is not None
        assert overlay.action_bar.status_label.text() == "Saved 2 screenshots"
    finally:
        overlay.deleteLater()


def test_copy_action_places_each_area_on_the_clipboard_separately(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(selection_actions, "clipboard_image_directory", lambda: tmp_path)
    overlay = _make_overlay()
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(40, 40, 80, 60))
        _add_action_area(overlay, QRect(200, 120, 70, 50))

        overlay._copy_selections()

        clipboard = QGuiApplication.clipboard()
        assert clipboard is not None
        mime = clipboard.mimeData()
        assert mime is not None
        paths = [Path(url.toLocalFile()) for url in mime.urls()]
        assert len(paths) == 2
        assert all(path.exists() for path in paths)
        assert Image.open(paths[0]).size == (80, 60)
        assert Image.open(paths[1]).size == (70, 50)
        assert overlay.action_bar is not None
        assert overlay.action_bar.status_label.text() == "Copied 2 images separately"
    finally:
        overlay.deleteLater()


def test_copy_action_can_merge_areas_into_one_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(selection_actions, "clipboard_image_directory", lambda: tmp_path)
    overlay = _make_overlay(config=AppConfig(copy_merge_images=True))
    _prepare_action_overlay(overlay)
    try:
        _add_action_area(overlay, QRect(40, 40, 80, 60))
        _add_action_area(overlay, QRect(200, 120, 70, 50))

        overlay._copy_selections()

        clipboard = QGuiApplication.clipboard()
        assert clipboard is not None
        image = clipboard.image()
        assert not image.isNull()
        assert image.width() == 80
        assert image.height() == 60 + 8 + 50
        assert overlay.action_bar is not None
        assert overlay.action_bar.status_label.text() == "Copied 2 areas as one image"
    finally:
        overlay.deleteLater()
