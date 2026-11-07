"""Mouse wiggle gesture detector for Mystic Pointer.

Detects when the user quickly moves the cursor left and right for a few moments,
matching the Magic Pointer gesture on Googlebooks.
"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QCursor


class WiggleDetector(QObject):
    """Detects rapid back-and-forth horizontal cursor movement."""

    wiggle_detected = Signal()

    def __init__(
        self,
        sensitivity: int = 5,
        enabled: bool = True,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.sensitivity = max(1, min(10, sensitivity))
        self.enabled = enabled
        self._is_running = False
        self._last_trigger_time = 0.0
        self._cooldown_seconds = 2.0  # Prevent multiple rapid triggers

        # Rolling history of (timestamp, x, y)
        self._history: deque[tuple[float, int, int]] = deque(maxlen=40)
        self._last_direction = 0  # -1 for left, +1 for right, 0 for none
        self._reversals: deque[float] = deque(maxlen=20)

    def set_sensitivity(self, val: int) -> None:
        self.sensitivity = max(1, min(10, val))

    def set_enabled(self, val: bool) -> None:
        self.enabled = val
        if not val:
            self._history.clear()
            self._reversals.clear()

    def update_sample(self, x: int, y: int, now: float | None = None) -> bool:
        """Process a single cursor sample (x, y).

        Returns True if a wiggle was detected.
        """
        if not self.enabled:
            return False

        if now is None:
            now = time.monotonic()

        if now - self._last_trigger_time < self._cooldown_seconds:
            return False

        if not self._history:
            self._history.append((now, x, y))
            return False

        prev_t, prev_x, prev_y = self._history[-1]
        dt = now - prev_t
        if dt <= 0:
            return False

        dx = x - prev_x
        dy = y - prev_y
        self._history.append((now, x, y))

        # Sensitivity parameters
        # High sensitivity (10): min_dx = 12 px, reversals needed = 3, window = 0.9s
        # Low sensitivity (1): min_dx = 40 px, reversals needed = 6, window = 0.6s
        factor = (11 - self.sensitivity) / 10.0  # 1.0 (lowest) down to 0.1 (highest)
        min_dx = int(12 + factor * 28)
        reversals_needed = int(3 + factor * 3)
        time_window = 0.5 + (self.sensitivity / 10.0) * 0.4  # 0.54s - 0.9s

        # Dominant horizontal movement check: dx should exceed dy significantly
        if abs(dx) >= min_dx and abs(dx) > abs(dy) * 0.8:
            new_direction = 1 if dx > 0 else -1
            if self._last_direction != 0 and new_direction != self._last_direction:
                # Direction reversed!
                self._reversals.append(now)

            self._last_direction = new_direction

        # Prune reversals older than the sliding time window
        while self._reversals and (now - self._reversals[0]) > time_window:
            self._reversals.popleft()

        if len(self._reversals) >= reversals_needed:
            self._last_trigger_time = now
            self._reversals.clear()
            self._history.clear()
            self._last_direction = 0
            self.wiggle_detected.emit()
            return True

        return False


class WiggleThread(QThread):
    """Background polling thread that queries QCursor.pos() at ~60Hz."""

    wiggle_detected = Signal()

    def __init__(self, detector: WiggleDetector, parent: QObject | None = None):
        super().__init__(parent)
        self.detector = detector
        self._running = False
        # Forward detector's signal
        self.detector.wiggle_detected.connect(self.wiggle_detected.emit)

    def run(self) -> None:
        self._running = True
        while self._running:
            pos = QCursor.pos()
            self.detector.update_sample(pos.x(), pos.y())
            time.sleep(0.016)  # ~60 FPS polling

    def stop(self) -> None:
        self._running = False
        self.wait(1000)
