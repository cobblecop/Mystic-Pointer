"""Background screen-capture service.

Wayland screenshots use a D-Bus round-trip (typically 300-600 ms). Running that
on the GUI thread would stall the tray, the wiggle detector and the overlay
itself, so captures happen on a worker thread and are delivered as a queued Qt
signal.  The frame is emitted before element detection so the overlay can appear
as soon as the pixels are ready.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QRect, QRunnable, QThreadPool, Signal

from mystic_pointer.core.element_detector import ElementDetector
from mystic_pointer.core.screen_capture import ScreenCapture, ScreenCaptureResult


@dataclass
class CaptureBundle:
    """A finished capture plus the candidate elements detected in it."""

    result: ScreenCaptureResult
    boxes: list[QRect] = field(default_factory=list)


class _CaptureTask(QRunnable):
    def __init__(
        self,
        completed: Callable[[object], None],
        elements_detected: Callable[[object], None],
        screen_geometry: QRect,
        virtual_geometry: QRect,
        detect_elements: bool,
    ):
        super().__init__()
        self._completed = completed
        self._elements_detected = elements_detected
        self._screen_geometry = screen_geometry
        self._virtual_geometry = virtual_geometry
        self._detect_elements = detect_elements
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = ScreenCapture.capture_for_screen(self._screen_geometry, self._virtual_geometry)
        except Exception as exc:
            print(f"[CaptureService] Capture failed: {exc}")
            result = None

        if result is None or not result.is_valid:
            self._completed(None)
            return

        # Deliver the frame first.  Element detection costs another ~60 ms at
        # 1080p and is not needed to show the overlay; it can arrive later and
        # only affects smart hover highlighting.
        self._completed(CaptureBundle(result=result))

        if not self._detect_elements:
            return

        try:
            detector = ElementDetector(result.image, result.screen_geometry)
            boxes = detector.detected_boxes
        except Exception as exc:
            print(f"[CaptureService] Element detection failed: {exc}")
            return

        self._elements_detected(CaptureBundle(result=result, boxes=boxes))


class _ElementDetectionTask(QRunnable):
    """Detect candidate elements for an already-captured frame off the GUI thread."""

    def __init__(
        self,
        completed: Callable[[ScreenCaptureResult, list[QRect]], None],
        result: ScreenCaptureResult,
    ):
        super().__init__()
        self._completed = completed
        self._result = result
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            detector = ElementDetector(self._result.image, self._result.screen_geometry)
            boxes = detector.detected_boxes
        except Exception as exc:
            print(f"[CaptureService] Element detection failed: {exc}")
            return
        self._completed(self._result, boxes)


class CaptureService(QObject):
    """Serialises background captures and emits the result on the GUI thread."""

    completed = Signal(object)  # CaptureBundle | None
    elements_detected = Signal(object)  # CaptureBundle

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        # A portal call must not race with a second portal call.
        self._pool.setMaxThreadCount(1)

    def request(
        self,
        screen_geometry: QRect,
        virtual_geometry: QRect,
        detect_elements: bool = True,
    ) -> None:
        task = _CaptureTask(
            self.completed.emit,
            self.elements_detected.emit,
            screen_geometry,
            virtual_geometry,
            detect_elements,
        )
        self._pool.start(task)

    def request_element_detection(self, result: ScreenCaptureResult) -> None:
        """Detect elements for a frame that was captured on the GUI thread."""
        task = _ElementDetectionTask(
            lambda captured, boxes: self.elements_detected.emit(
                CaptureBundle(result=captured, boxes=boxes)
            ),
            result,
        )
        self._pool.start(task)

    def shutdown(self, timeout_ms: int = 8000) -> None:
        """Wait for an in-flight capture so the app can exit cleanly."""
        self._pool.waitForDone(timeout_ms)
