"""Mystic Pointer dimmed overlay and selection canvas.

Activation freezes the screen: the frame captured through the still-transparent
window is painted as an opaque base under the dim layer, so a playing video
cannot move on while the user is choosing an area.  The frame and the dim fade
in together over the live desktop, which keeps activation seamless.  Hovered and
selected regions redraw that frozen frame at full brightness inside a rounded
clip, so an image brightens through the dim instead of being outlined.  The same
capture supplies the crops sent to the model.

On GNOME Wayland the compositor composites *every* fullscreen surface against
black, which would turn a translucent fullscreen overlay into a black screen.
A regular window is composited correctly, so the overlay covers the work area
there (below the top bar) instead of the full screen.
"""

from __future__ import annotations

import time

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QScreen,
)
from PySide6.QtWidgets import QWidget

from mystic_pointer.ai.base import AIProvider
from mystic_pointer.config import AppConfig
from mystic_pointer.core.capture_service import CaptureBundle, CaptureService
from mystic_pointer.core.screen_capture import (
    ScreenCapture,
    ScreenCaptureResult,
    is_gnome_session,
    is_wayland_session,
    pil_to_pixmap,
)
from mystic_pointer.ui.floating_panel import FloatingPanel
from mystic_pointer.ui.selection import SelectionManager
from mystic_pointer.ui.style import ACCENT

# GNOME Shell scales every newly mapped toplevel up from a sliver at the bottom
# of the screen (150 ms, see gnome-shell's windowManager.js).  The overlay is
# fully transparent while that animation plays, so it has no visible pixels to
# scale; the dim layer only starts afterwards.
_MAP_ANIMATION_GUARD_MS = 180

# Dim fade duration.  InOutCubic keeps the first frame from jumping.
_DIM_FADE_MS = 300

# The frozen frame finishes fading in over the first half of the dim fade, so a
# playing video stops as soon as possible while the desktop still darkens
# smoothly around it.
_FRAME_FADE_SHARE = 0.5

# Dismiss fade.  The dim layer lifts off the live desktop just before the
# window is destroyed, so Mystic Pointer never disappears with a hard cut.
_DISMISS_FADE_MS = 160


class MysticPointerOverlay(QWidget):
    """Dimmed screen overlay supporting hover, drag selection, and AI prompts."""

    overlay_closed = Signal()
    capture_failed = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        provider: AIProvider,
        screen: QScreen,
        capture_service: CaptureService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.provider = provider
        self.target_screen = screen
        self.screen_geometry = screen.geometry()
        self.capture_service = capture_service
        self.selection_manager = SelectionManager(self)

        # Window configuration
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)

        # Compositor workaround: a translucent fullscreen surface is drawn over
        # black on GNOME Wayland.  There the overlay is a maximized window over
        # the work area; Qt does not report its real position, but the surface
        # is placed directly below the top bar, so the missing height is the
        # offset.  Everywhere else the overlay covers the whole screen.
        self._work_area_mode = is_wayland_session() and is_gnome_session()
        self._origin = self.screen_geometry.topLeft()

        # Screen capture: hover detection, AI crops and the frozen frame.
        self.capture_result: ScreenCaptureResult | None = None
        self.detected_boxes: list[QRect] = []
        self._frame_pixmap: QPixmap | None = None

        # Selection state
        self.is_dragging = False
        self.drag_start = QPoint()
        self.drag_current = QPoint()
        self.hovered_rect: QRect | None = None

        # Floating panel
        self.panel: FloatingPanel | None = None
        self._panel_height_hint: int | None = None
        self._panel_anchor: QRect | None = None
        self._positioning_panel = False
        self._is_closing = False

        # Activation reveal.  The window is mapped at its final size while it
        # is still fully transparent, so the compositor's open animation is
        # invisible.  The dim layer fades in over the live desktop once the
        # screenshot is out of the way (see ``_maybe_start_reveal``).
        self._reveal = 0.0
        self._reveal_anim: QVariantAnimation | None = None
        self._dismiss_anim: QVariantAnimation | None = None
        self._dismissing = False
        self._active = False
        self._capture_ready = False
        self._shown_at = 0.0
        # Composable timers (instead of QTimer.singleShot) so pending steps are
        # cancelled automatically when the overlay is closed.
        self._guard_timer = QTimer(self)
        self._guard_timer.setSingleShot(True)
        self._guard_timer.timeout.connect(self._maybe_start_reveal)
        # Only GNOME Shell animates newly mapped windows.
        self._map_guard_ms = _MAP_ANIMATION_GUARD_MS if is_gnome_session() else 0

        self.selection_manager.adding_content_changed.connect(self._on_adding_content_changed)

    # --- Activation ---

    def begin(self) -> None:
        """Map the transparent overlay and capture the screen behind it.

        The window is mapped while nothing is painted, so the compositor's
        window-open animation has no visible pixels to scale.  The screenshot
        is taken through the fully transparent window, therefore it contains
        only the real desktop.  Once both the capture has finished and the map
        animation is over, the frozen frame and the dim layer cross-fade in
        together instead of a snapshot popping onto the screen.
        """
        self.setScreen(self.target_screen)
        self.setGeometry(self.screen_geometry)

        # Detection can finish after the overlay is already visible.
        self.capture_service.elements_detected.connect(self._on_elements_detected)

        # The first layout of the panel is surprisingly expensive (QSS + font
        # metrics).  Do it while the capture is in flight.
        self._ensure_panel()
        if self.panel is not None:
            self._panel_height_hint = self.panel.sizeHint().height()

        self._map_overlay()
        self._shown_at = time.monotonic()

        self.capture_service.completed.connect(self._on_capture_completed)
        self.capture_service.request(
            self.screen_geometry,
            ScreenCapture.get_virtual_geometry(),
            detect_elements=self.config.smart_detection,
        )

        delay = self._reveal_delay_ms()
        if delay <= 0:
            self._maybe_start_reveal()
        else:
            self._guard_timer.start(delay)

    def _map_overlay(self) -> None:
        """Map the overlay at its final geometry while fully transparent."""
        if self._work_area_mode:
            self.showMaximized()
        else:
            self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._update_origin()

    def _update_origin(self) -> None:
        """Translate between overlay-local and desktop-global coordinates."""
        if self._work_area_mode:
            top_offset = max(0, self.screen_geometry.height() - self.height())
            self._origin = QPoint(
                self.screen_geometry.x(),
                self.screen_geometry.y() + top_offset,
            )
        else:
            self._origin = self.screen_geometry.topLeft()

    def _reveal_delay_ms(self) -> int:
        """Milliseconds left before the compositor's open animation is done."""
        if self._map_guard_ms <= 0:
            return 0
        elapsed_ms = int((time.monotonic() - self._shown_at) * 1000)
        return max(0, self._map_guard_ms - elapsed_ms)

    def _maybe_start_reveal(self) -> None:
        """Start the reveal once the capture is done and the map has settled."""
        if self._is_closing or not self._capture_ready:
            return
        delay = self._reveal_delay_ms()
        if delay > 0:
            self._guard_timer.start(delay)
            return
        self._start_reveal()

    def _start_reveal(self) -> None:
        """Cross-fade the frozen frame and dim layer in over the live desktop."""
        if self._is_closing or self._reveal_anim is not None:
            return
        self._active = True
        self._reveal = 0.0
        if self.panel is not None:
            self._position_panel_initial()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(_DIM_FADE_MS)
        # Ease in *and* out: an ease-out dim changes fastest on its first
        # frame, which reads as a small step rather than a fade.
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.valueChanged.connect(self._on_reveal_value)
        anim.finished.connect(self._on_reveal_finished)
        self._reveal_anim = anim
        self.update()
        anim.start()

    def _on_reveal_value(self, value: object) -> None:
        self._reveal = float(value)  # type: ignore[arg-type]
        self.update()

    def _on_reveal_finished(self) -> None:
        self._reveal = 1.0
        if self._reveal_anim is not None:
            self._reveal_anim.deleteLater()
            self._reveal_anim = None
        self.update()

    # --- Capture results ---

    def _on_elements_detected(self, bundle: CaptureBundle) -> None:
        if self._is_closing or self.capture_result is not bundle.result:
            return
        self.detected_boxes = bundle.boxes
        self.update()

    def _on_capture_completed(self, bundle: CaptureBundle | None) -> None:
        if self._is_closing:
            return
        if bundle is None or not bundle.result.is_valid:
            # Never start a session that cannot describe the screen: fail
            # visibly instead.
            self.capture_failed.emit(
                "Could not capture the screen. On Wayland, make sure "
                "xdg-desktop-portal is installed and running."
            )
            self.close()
            return
        self._apply_capture(bundle.result, bundle.boxes)

    def _apply_capture(self, result: ScreenCaptureResult, boxes: list[QRect]) -> None:
        """Store the frame that pauses the screen and feeds detection/crops."""
        self.capture_result = result
        self.detected_boxes = boxes
        self._capture_ready = True
        self._build_frame_pixmap()
        self._ensure_panel()
        if self.panel is not None:
            self.panel.user_positioned = False
        self._maybe_start_reveal()

    def _build_frame_pixmap(self) -> None:
        """Prepare the frozen frame for the part of the screen the overlay covers.

        The capture holds the whole screen in device pixels; the overlay may be
        the work area only (GNOME Wayland), so crop the matching region and
        scale it with the device pixel ratio.  The pixmap is opaque: once the
        dim is revealed it is what the user sees, which is what pauses a video.
        """
        result = self.capture_result
        if result is None or not result.is_valid:
            self._frame_pixmap = None
            return

        ratio = result.device_pixel_ratio if result.device_pixel_ratio > 0 else 1.0
        screen = self.screen_geometry
        left = max(0, int(round((self._origin.x() - screen.x()) * ratio)))
        top = max(0, int(round((self._origin.y() - screen.y()) * ratio)))
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        right = min(left + width, result.image.width)
        bottom = min(top + height, result.image.height)
        if right <= left or bottom <= top:
            self._frame_pixmap = None
            return

        try:
            source = result.image.crop((left, top, right, bottom))
            pixmap = pil_to_pixmap(source, QSize(width, height))
        except Exception as exc:
            # Never break activation because the frame could not be converted;
            # the live desktop still works, just without the freeze.
            print(f"[MysticPointer] Could not prepare the frozen frame: {exc}")
            self._frame_pixmap = None
            return
        # Draw at the widget's logical size while keeping the frame sharp on
        # high-DPI screens.
        pixmap.setDevicePixelRatio(ratio)
        self._frame_pixmap = pixmap

    def _ensure_panel(self) -> None:
        if self.panel is not None:
            return
        self.panel = FloatingPanel(
            selection_manager=self.selection_manager,
            provider=self.provider,
            config=self.config,
            parent=self,
        )
        # The panel is a child of the overlay.  Keep it hidden until there is
        # something to ask about, so activation is just the dimmed desktop.
        self.panel.hide()
        self.panel.close_requested.connect(self.dismiss)
        self.panel.panel_resized.connect(self._on_panel_resized)

    def dismiss(self) -> None:
        """Exit Mystic Pointer completely, fading the dim layer out first."""
        if self._is_closing:
            return
        self._is_closing = True
        self._guard_timer.stop()
        if self._reveal_anim is not None:
            self._reveal_anim.stop()
            self._reveal_anim.deleteLater()
            self._reveal_anim = None
        self.selection_manager.clear()
        self.hovered_rect = None
        if self.panel is not None:
            self.panel.hide()
        # A visible dim layer fades away instead of vanishing in one frame;
        # an overlay that was still fully transparent closes immediately.
        if self._active and self._reveal > 0.01:
            self._dismissing = True
            self.setCursor(Qt.CursorShape.ArrowCursor)
            anim = QVariantAnimation(self)
            anim.setStartValue(self._reveal)
            anim.setEndValue(0.0)
            anim.setDuration(_DISMISS_FADE_MS)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.valueChanged.connect(self._on_dismiss_value)
            anim.finished.connect(self._finish_dismiss)
            self._dismiss_anim = anim
            anim.start()
            return
        self._finish_dismiss()

    def _on_dismiss_value(self, value: object) -> None:
        self._reveal = float(value)  # type: ignore[arg-type]
        self.update()

    def _finish_dismiss(self) -> None:
        if self._dismiss_anim is not None:
            self._dismiss_anim.deleteLater()
            self._dismiss_anim = None
        self.close()

    def closeEvent(self, event) -> None:
        self._is_closing = True
        self._guard_timer.stop()
        if self._dismiss_anim is not None:
            self._dismiss_anim.stop()
            self._dismiss_anim.deleteLater()
            self._dismiss_anim = None
        try:
            if self.panel is not None:
                # Stop a streaming AI worker before the panel is destroyed.
                self.panel.shutdown()
        finally:
            # Always notify the controller: it must never keep a reference to a
            # closed (and, with WA_DeleteOnClose, deleted) overlay.
            self.overlay_closed.emit()
            super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self._update_origin()
        # A resize after the capture (compositor settling, monitor change) must
        # not stretch or misalign the frozen frame.
        if self.capture_result is not None and self._frame_pixmap is not None:
            self._build_frame_pixmap()

    # --- Panel placement ---

    def _on_adding_content_changed(self, adding: bool) -> None:
        """Enter/leave the 'pick another area' mode.

        The panel shows the mode inline; the overlay reinforces it with a
        crosshair cursor and a dedicated hint pill above the desktop.
        """
        if adding:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if self.hovered_rect is not None
                else Qt.CursorShape.ArrowCursor
            )
        self.update()

    def _get_current_drag_rect(self) -> QRect:
        x = min(self.drag_start.x(), self.drag_current.x())
        y = min(self.drag_start.y(), self.drag_current.y())
        w = abs(self.drag_start.x() - self.drag_current.x())
        h = abs(self.drag_start.y() - self.drag_current.y())
        return QRect(x, y, w, h)

    def _panel_height(self) -> int:
        if self.panel is None:
            return 0
        # Once shown, the real height reflects the current layout (including a
        # visible response card); before that, use the pre-laid-out hint.
        if self.panel.isVisible() and self.panel.height() > 0:
            return self.panel.height()
        if self._panel_height_hint is not None:
            return self._panel_height_hint
        return max(self.panel.sizeHint().height(), self.panel.height())

    def _position_panel_initial(self) -> None:
        if self.panel is None:
            return
        panel_w = self.panel.width()
        panel_h = self._panel_height()
        target_x = (self.width() - panel_w) // 2
        target_y = int(self.height() * 0.78)
        target_y = min(target_y, self.height() - panel_h - 24)
        target_x = max(20, min(target_x, self.width() - panel_w - 20))
        target_y = max(20, target_y)
        self.panel.move(target_x, target_y)

    def _position_panel_near(self, local_rect: QRect) -> None:
        """Place the panel near a selection, using overlay-local coordinates."""
        if self.panel is None:
            return

        self._panel_anchor = QRect(local_rect)
        self._positioning_panel = True
        try:
            # Show (and settle) the panel before measuring it: its first
            # polished layout is taller than the hint cached while it was
            # hidden, and placing it with the stale height pushes it off-screen.
            self.panel.reveal()
            panel_w = self.panel.width()
            panel_h = self._panel_height()

            target_x = local_rect.center().x() - panel_w // 2
            target_y = local_rect.bottom() + 16

            if target_y + panel_h > self.height() - 20:
                target_y = local_rect.top() - panel_h - 16

            target_x = max(20, min(target_x, self.width() - panel_w - 20))
            target_y = max(20, min(target_y, self.height() - panel_h - 20))

            self.panel.move(target_x, target_y)
        finally:
            self._positioning_panel = False

    def _on_panel_resized(self) -> None:
        """Keep the popover on-screen as thumbnails or a response appear."""
        if self._positioning_panel or self.panel is None or not self.panel.isVisible():
            return
        if self.panel.user_positioned:
            # Once the user has moved the dialog, resizing it (streaming text,
            # thumbnails) must not snap it back to the selection.
            self._clamp_panel_position()
        elif self._panel_anchor is not None:
            self._position_panel_near(self._panel_anchor)
        else:
            self._position_panel_initial()

    def _clamp_panel_position(self) -> None:
        """Keep a user-positioned panel fully inside the overlay."""
        if self.panel is None:
            return
        max_x = max(20, self.width() - self.panel.width() - 20)
        max_y = max(20, self.height() - self.panel.height() - 20)
        target_x = max(20, min(self.panel.x(), max_x))
        target_y = max(20, min(self.panel.y(), max_y))
        if target_x != self.panel.x() or target_y != self.panel.y():
            self.panel.move(target_x, target_y)

    # --- Paint Events ---

    def paintEvent(self, event) -> None:
        if not self._active:
            self._clear_transparent()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Start from a transparent frame so the live desktop is visible until
        # the capture is ready.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        reveal = max(0.0, min(1.0, self._reveal))

        # 2. Fade in the frozen frame.  It is cross-faded with the live desktop
        # rather than switched on, so activation has no snapshot pop.  The
        # frame is fully opaque halfway through the dim fade, which stops a
        # playing video sooner.
        self._draw_frame(painter, self._frame_opacity(reveal))

        # 3. Draw the dim layer over the frozen frame.  Its alpha is animated
        # during activation, so the desktop darkens smoothly.
        if reveal > 0:
            dim_color = QColor(0, 0, 0, int(round(255 * self.config.dim_opacity * reveal)))
            painter.fillRect(self.rect(), dim_color)

        # While dismissing, only the frame and dim remain: selections, spotted
        # images and the hint should not linger through the fade-out.
        if self._dismissing:
            painter.end()
            return

        # 4. Reveal confirmed selections.  The frozen frame is redrawn inside a
        # rounded clip, brighter than the dimmed surroundings.
        for item in self.selection_manager.items:
            rel_rect = self._to_local(item.rect)
            self._punch_hole(painter, rel_rect, 6)

            # Accent outline and numbered badge.
            painter.setPen(QPen(QColor(ACCENT), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rel_rect, 6, 6)

            badge_rect = QRect(rel_rect.left() + 4, rel_rect.top() + 4, 22, 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ACCENT))
            painter.drawEllipse(badge_rect)

            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Cantarell", 10, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, str(item.id))

        # 5. Brighten the image under the cursor.  Redrawing the frozen frame
        # inside a rounded clip reads as a highlight without a box around it.
        if not self.is_dragging and self.hovered_rect is not None:
            self._punch_hole(painter, self._to_local(self.hovered_rect), 5)

        # 6. Draw active drag selection rectangle
        if self.is_dragging:
            drag_rect = self._get_current_drag_rect()
            self._punch_hole(painter, drag_rect, 6)
            painter.setPen(QPen(QColor(ACCENT), 2.0))
            painter.setBrush(QColor(53, 132, 228, 38))
            painter.drawRoundedRect(drag_rect, 6, 6)

        # 7. Soft accent glow around the screen edge: a quiet "Mystic Pointer is
        # active" cue that does not add another floating surface.  Draw it
        # before the hint so the pill stays crisp on top of the glow.
        self._draw_edge_glow(painter, reveal)

        # 8. First-run hint, drawn over the dimmed desktop.
        adding = self.selection_manager.is_adding_content
        if adding or (not self.selection_manager.items and not self.is_dragging):
            self._draw_selection_hint(painter, reveal)

        painter.end()

    def _clear_transparent(self) -> None:
        """Leave the surface fully transparent while the window is idle."""
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.end()

    @staticmethod
    def _frame_opacity(reveal: float) -> float:
        """Opacity of the frozen frame for the current reveal value."""
        if reveal <= 0.0:
            return 0.0
        return min(1.0, reveal / _FRAME_FADE_SHARE)

    def _draw_frame(
        self,
        painter: QPainter,
        opacity: float,
        rect: QRect | None = None,
        radius: float = 0.0,
    ) -> None:
        """Paint the frozen frame, optionally clipped to a rounded rectangle."""
        if self._frame_pixmap is None or opacity <= 0.0:
            return
        painter.save()
        painter.setOpacity(min(1.0, opacity))
        if rect is not None:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(rect), radius, radius)
            painter.setClipPath(clip)
        painter.drawPixmap(0, 0, self._frame_pixmap)
        painter.restore()

    def _punch_hole(self, painter: QPainter, rect: QRect, radius: int) -> None:
        """Show the frozen frame at full brightness inside ``rect``."""
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if self._frame_pixmap is None:
            # No frozen frame available: fall back to a transparent hole so
            # the live desktop shows through, as before.
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0))
            painter.drawRoundedRect(QRectF(rect), radius, radius)
            painter.restore()
            return
        self._draw_frame(painter, self._frame_opacity(self._reveal), rect, radius)

    def _draw_edge_glow(self, painter: QPainter, strength: float) -> None:
        """Draw a soft inner glow plus a crisp hairline around the screen."""
        if strength <= 0.0:
            return

        width = self.width()
        height = self.height()
        depth = 34

        edge = QColor(ACCENT)
        edge.setAlphaF(0.30 * strength)
        transparent = QColor(ACCENT)
        transparent.setAlpha(0)

        gradients = [
            (QRect(0, 0, width, depth), 0, 0, 0, depth),
            (QRect(0, height - depth, width, depth), 0, height, 0, height - depth),
            (QRect(0, 0, depth, height), 0, 0, depth, 0),
            (QRect(width - depth, 0, depth, height), width, 0, width - depth, 0),
        ]
        for rect, x1, y1, x2, y2 in gradients:
            gradient = QLinearGradient(x1, y1, x2, y2)
            gradient.setColorAt(0.0, edge)
            gradient.setColorAt(1.0, transparent)
            painter.fillRect(rect, gradient)

        hairline = QColor(ACCENT)
        hairline.setAlphaF(0.50 * strength)
        painter.setPen(QPen(hairline, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, width - 1.0, height - 1.0))

    def _draw_selection_hint(self, painter: QPainter, opacity: float = 1.0) -> None:
        adding = self.selection_manager.is_adding_content
        if adding:
            text = "Click or drag to add another area   ·   Esc to cancel"
        else:
            text = "Hover an image to highlight   ·   Click or drag to select   ·   Esc to cancel"
        font = QFont("Cantarell", 10)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(text) + 32
        height = 36
        hint_rect = QRect((self.width() - width) // 2, 24, width, height)

        painter.save()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        if adding:
            border = QColor(ACCENT)
            border.setAlphaF(0.75)
            painter.setPen(QPen(border, 1.0))
            painter.setBrush(QColor(28, 40, 58, 242))
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 28), 1.0))
            painter.setBrush(QColor(36, 36, 36, 238))
        painter.drawRoundedRect(hint_rect, 10, 10)

        painter.setPen(QColor("#f6f5f4"))
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    # --- Mouse & Keyboard Events ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._is_closing:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked inside floating panel
            if (
                self.panel
                and self.panel.isVisible()
                and self.panel.geometry().contains(event.pos())
            ):
                super().mousePressEvent(event)
                return

            self.is_dragging = True
            self.drag_start = event.pos()
            self.drag_current = event.pos()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_closing:
            return
        if self.panel and self.panel.isVisible() and self.panel.geometry().contains(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.is_dragging:
            self.drag_current = event.pos()
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()
        else:
            # Detect smart element hover
            if self.detected_boxes and self.capture_result is not None:
                global_pos = event.pos() + self._origin
                found = self._find_element_at(global_pos)
                if found != self.hovered_rect:
                    self.hovered_rect = found
                    self.update()
            if self.selection_manager.is_adding_content:
                # Picking another area keeps the crosshair even over images so
                # it is obvious that a click/drag starts a new selection.
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(
                    Qt.CursorShape.PointingHandCursor
                    if self.hovered_rect
                    else Qt.CursorShape.CrossCursor
                )

    def _find_element_at(self, global_pos: QPoint) -> QRect | None:
        candidates = [box for box in self.detected_boxes if box.contains(global_pos)]
        if not candidates:
            return None
        return min(candidates, key=lambda b: b.width() * b.height())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_closing:
            return
        if not self.capture_result:
            return

        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            drag_rect = self._get_current_drag_rect()
            is_ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            is_multi = is_ctrl_pressed or self.selection_manager.is_adding_content

            # Check if this was a click (distance < 8px) or drag selection
            if drag_rect.width() < 8 and drag_rect.height() < 8:
                if self.hovered_rect is not None:
                    # Clicked on a detected image; a new selection gets a fresh
                    # automatic placement even if the panel was moved before.
                    target_rect = self.hovered_rect
                    if self.panel is not None:
                        self.panel.user_positioned = False
                    if not is_multi:
                        self.selection_manager.clear()
                    self.selection_manager.add_selection(
                        target_rect,
                        self.capture_result.image,
                        self.screen_geometry,
                        self.capture_result.device_pixel_ratio,
                    )
                    self._position_panel_near(self._to_local(target_rect))
                else:
                    # Clicked anywhere in dimmed area -> exit Mystic Pointer
                    # completely, as described in script.txt.
                    if self.selection_manager.is_adding_content:
                        # A plain click means "never mind" rather than wiping
                        # the existing selections and closing the overlay.
                        self.selection_manager.set_adding_content(False)
                    elif not self.selection_manager.has_selection or not is_multi:
                        self.dismiss()
                        return
            else:
                # Dragged area selection
                if self.panel is not None:
                    self.panel.user_positioned = False
                if not is_multi:
                    self.selection_manager.clear()

                global_drag_rect = QRect(
                    drag_rect.x() + self._origin.x(),
                    drag_rect.y() + self._origin.y(),
                    drag_rect.width(),
                    drag_rect.height(),
                )
                self.selection_manager.add_selection(
                    global_drag_rect,
                    self.capture_result.image,
                    self.screen_geometry,
                    self.capture_result.device_pixel_ratio,
                )
                self._position_panel_near(drag_rect)

            self.update()

    def _to_local(self, rect: QRect) -> QRect:
        return QRect(
            rect.x() - self._origin.x(),
            rect.y() - self._origin.y(),
            rect.width(),
            rect.height(),
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # In add-area mode the first Escape only leaves that mode; the
            # existing selection and prompt stay untouched.
            if self.selection_manager.is_adding_content:
                self.selection_manager.set_adding_content(False)
                event.accept()
                return
            # As described in script.txt: "To exit Mystic Pointer completely, on
            # your keyboard, select Escape."
            self.dismiss()
        else:
            super().keyPressEvent(event)
