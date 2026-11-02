"""Tests for cursor wiggle gesture detection."""

from mystic_pointer.core.wiggle_detector import WiggleDetector


def test_wiggle_detection_triggers_on_rapid_reversals():
    detector = WiggleDetector(sensitivity=8, enabled=True)
    triggered = []
    detector.wiggle_detected.connect(lambda: triggered.append(True))

    now = 1000.0
    x, y = 500, 500

    # Simulate rapid left-and-right shakes
    for step in range(8):
        # Alternate moving +50 px right, then -50 px left
        direction = 1 if step % 2 == 0 else -1
        x += direction * 50
        now += 0.05
        detector.update_sample(x, y, now)

    assert len(triggered) >= 1, "Expected wiggle gesture to trigger"


def test_wiggle_detection_ignores_monotonic_drift():
    detector = WiggleDetector(sensitivity=5, enabled=True)
    triggered = []
    detector.wiggle_detected.connect(lambda: triggered.append(True))

    now = 1000.0
    x, y = 100, 100
    # Move in a straight line to the right (no reversals)
    for _ in range(20):
        x += 30
        now += 0.03
        detector.update_sample(x, y, now)

    assert len(triggered) == 0, "Monotonic cursor movement should not trigger wiggle"


def test_wiggle_detection_ignores_vertical_movement():
    detector = WiggleDetector(sensitivity=5, enabled=True)
    triggered = []
    detector.wiggle_detected.connect(lambda: triggered.append(True))

    now = 1000.0
    x, y = 500, 500
    # Move up and down rapidly
    for step in range(10):
        y += 50 if step % 2 == 0 else -50
        now += 0.04
        detector.update_sample(x, y, now)

    assert len(triggered) == 0, "Vertical movement should not trigger horizontal wiggle"


def test_wiggle_disabled():
    detector = WiggleDetector(sensitivity=10, enabled=False)
    triggered = []
    detector.wiggle_detected.connect(lambda: triggered.append(True))

    now = 1000.0
    x, y = 500, 500
    for step in range(10):
        x += 80 if step % 2 == 0 else -80
        now += 0.04
        detector.update_sample(x, y, now)

    assert len(triggered) == 0, "Disabled detector must not trigger"
