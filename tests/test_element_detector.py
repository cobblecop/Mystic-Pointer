"""Tests for image-only smart hover detection."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, QRect

from mystic_pointer.core.element_detector import ElementDetector


def _photo(width: int = 180, height: int = 120) -> Image.Image:
    """Create a colourful, photo-like patch without external assets."""
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            red = int(128 + 120 * math.sin(x / 11.0))
            green = int(128 + 120 * math.sin(y / 8.0 + 1.4))
            blue = int(128 + 120 * math.sin((x + y) / 15.0 + 2.1))
            pixels[x, y] = (
                max(0, min(255, red)),
                max(0, min(255, green)),
                max(0, min(255, blue)),
            )
    return image


def _desktop(width: int = 900, height: int = 600) -> Image.Image:
    """A neutral desktop with UI chrome and text-like rows."""
    image = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(image)

    # A saturated top bar: it touches the screen edge and must be rejected.
    draw.rectangle((0, 0, width, 34), fill=(53, 132, 228))

    # Flat saturated UI buttons and neutral text-like lines.  The text stops
    # well short of the photo pasted by the tests so the two never touch.
    draw.rounded_rectangle((70, 90, 250, 136), radius=8, fill=(53, 132, 228))
    for row in range(12):
        y = 180 + row * 18
        draw.rectangle((70, y, 250 + (row % 3) * 10, y + 6), fill=(185, 183, 180))

    return image


def test_neutral_ui_produces_no_image_boxes():
    image = _desktop()
    detector = ElementDetector(image, QRect(0, 0, 900, 600))
    assert detector.detected_boxes == []


def test_colourful_image_is_detected():
    image = _desktop()
    image.paste(_photo(), (300, 220))
    detector = ElementDetector(image, QRect(0, 0, 900, 600))

    assert len(detector.detected_boxes) == 1
    box = detector.detected_boxes[0]
    expected = QRect(300, 220, 180, 120)
    overlap = box.intersected(expected)
    assert overlap.width() * overlap.height() >= expected.width() * expected.height() * 0.85


def test_image_box_uses_screen_offset():
    image = _desktop()
    image.paste(_photo(), (300, 220))
    screen = QRect(120, 80, 900, 600)
    detector = ElementDetector(image, screen)

    assert len(detector.detected_boxes) == 1
    box = detector.detected_boxes[0]
    assert 120 + 280 <= box.x() <= 120 + 320
    assert 80 + 200 <= box.y() <= 80 + 240


def test_image_touching_screen_edge_is_ignored():
    image = _desktop()
    image.paste(_photo(), (0, 120))
    detector = ElementDetector(image, QRect(0, 0, 900, 600))
    assert detector.detected_boxes == []


def test_find_element_at_returns_containing_image():
    image = _desktop()
    image.paste(_photo(), (300, 220))
    detector = ElementDetector(image, QRect(0, 0, 900, 600))

    assert detector.find_element_at(QPoint(390, 280)) is not None
    assert detector.find_element_at(QPoint(80, 400)) is None


def test_side_by_side_images_are_split_into_separate_boxes():
    """Two cards in one row must not become one wide highlight."""
    image = Image.new("RGB", (900, 600), (246, 245, 244))
    draw = ImageDraw.Draw(image)
    photo = _photo(280, 180)
    for left in (80, 400):
        draw.rounded_rectangle(
            (left, 180, left + 330, 470),
            radius=12,
            fill=(255, 255, 255),
            outline=(222, 221, 218),
        )
        image.paste(photo, (left + 10, 190))
        draw.text((left + 10, 400), "A photo caption", fill=(60, 60, 60))

    detector = ElementDetector(image, QRect(0, 0, 900, 600))

    assert len(detector.detected_boxes) == 2
    boxes = sorted(detector.detected_boxes, key=lambda box: box.x())
    for box, left in zip(boxes, (90, 410), strict=True):
        expected = QRect(left, 190, 280, 180)
        overlap = box.intersected(expected)
        assert overlap.width() * overlap.height() >= expected.width() * expected.height() * 0.8


def test_text_above_an_image_is_not_merged_into_its_box():
    image = Image.new("RGB", (900, 600), (246, 245, 244))
    draw = ImageDraw.Draw(image)
    draw.text((90, 100), "Heading text right above the picture", fill=(30, 30, 30))
    draw.text((90, 130), "A subtitle line that must stay outside", fill=(80, 80, 80))
    image.paste(_photo(360, 220), (90, 160))

    detector = ElementDetector(image, QRect(0, 0, 900, 600))

    assert len(detector.detected_boxes) == 1
    box = detector.detected_boxes[0]
    expected = QRect(90, 160, 360, 220)
    overlap = box.intersected(expected)
    assert overlap.width() * overlap.height() >= expected.width() * expected.height() * 0.85
    assert box.y() >= 150


def test_text_panel_is_recognised_as_text():
    """A dense block of text must not be treated as a screenshot."""
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        return

    image = Image.new("RGB", (900, 600), (246, 245, 244))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((150, 120, 760, 500), radius=14, fill=(255, 255, 255))
    draw.rounded_rectangle((180, 150, 730, 470), radius=12, fill=(242, 241, 240))
    lines = [
        "The trail climbs steeply through the forest before opening",
        "onto a wide alpine meadow. Mornings are cold and clear and",
        "the light changes every few minutes as clouds drift across",
        "the ridge. We stopped for lunch beside a small lake, then",
        "continued along the ridge until the path turned back toward",
        "the valley. The descent took longer than expected because",
        "of the loose scree. Back at the hut we sorted the photos",
        "and wrote a few notes about the day.",
    ]
    for index, line in enumerate(lines):
        draw.text((200, 165 + index * 36), line, fill=(61, 56, 70), font=font)

    detector = ElementDetector(image, QRect(0, 0, 900, 600))

    assert detector._looks_like_text(image.crop((180, 150, 730, 470)), (242, 241, 240))
    assert detector.detected_boxes == []
