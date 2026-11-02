"""Tests for screen capture helpers that do not need a real display."""

from PIL import Image
from PySide6.QtCore import QRect

from mystic_pointer.core.screen_capture import (
    ScreenCapture,
    ScreenCaptureResult,
    has_visible_content,
)


def test_blank_black_frame_is_rejected():
    black = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
    assert not has_visible_content(black)


def test_dark_but_structured_frame_is_accepted():
    # A dark desktop (wallpaper, panels) must not be mistaken for a failed grab.
    image = Image.new("RGBA", (200, 120), (0, 0, 0, 255))
    for x in range(200):
        for y in range(0, 20):
            image.putpixel((x, y), (60, 60, 70, 255))
    assert has_visible_content(image)


def test_white_frame_is_not_treated_as_blank():
    white = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    assert has_visible_content(white)


def test_crop_selection_accounts_for_device_pixel_ratio():
    image = Image.new("RGBA", (3840, 2160), (10, 20, 30, 255))
    screen = QRect(0, 0, 1920, 1080)
    crop = ScreenCapture.crop_selection(image, QRect(100, 50, 200, 100), screen, 2.0)
    assert crop.size == (400, 200)


def test_crop_selection_accounts_for_screen_offset():
    image = Image.new("RGBA", (1920, 1080), (10, 20, 30, 255))
    screen = QRect(1920, 0, 1920, 1080)
    crop = ScreenCapture.crop_selection(image, QRect(1920 + 30, 40, 100, 60), screen, 1.0)
    assert crop.size == (100, 60)


def test_crop_to_screen_slices_multi_monitor_image():
    desktop = Image.new("RGBA", (3840, 1080), (0, 0, 0, 255))
    # Right half is red so we can verify which screen was cropped.
    right = Image.new("RGBA", (1920, 1080), (255, 0, 0, 255))
    desktop.paste(right, (1920, 0))

    virtual = QRect(0, 0, 3840, 1080)
    cropped, ratio = ScreenCapture._crop_to_screen(desktop, virtual, QRect(1920, 0, 1920, 1080))
    assert cropped.size == (1920, 1080)
    assert ratio == 1.0
    pixel = cropped.convert("RGB").getpixel((10, 10))
    assert isinstance(pixel, tuple)
    assert pixel[0] == 255


def test_capture_result_ratio_math():
    image = Image.new("RGBA", (3840, 2160), (1, 2, 3, 255))
    result = ScreenCaptureResult(image=image, screen_geometry=QRect(0, 0, 1920, 1080))
    assert result.is_valid
    assert result.logical_size.width() == 1920
    assert result.device_pixel_ratio == 1.0


def test_load_captured_image_returns_detached_rgba(tmp_path):
    from mystic_pointer.core.screen_capture import _load_captured_image

    path = tmp_path / "capture.png"
    Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(path)
    loaded = _load_captured_image(str(path))
    assert loaded.mode == "RGBA"
    assert loaded.size == (16, 16)
    assert loaded.getpixel((0, 0)) == (10, 20, 30, 255)
