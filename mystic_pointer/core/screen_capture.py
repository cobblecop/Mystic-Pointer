"""Cross-platform screen capture manager supporting Linux Wayland, Linux X11, and Windows.

On Wayland, clients are not allowed to read the framebuffer directly.  Qt's
``QScreen.grabWindow`` returns a null pixmap and tools that go through XWayland
(``mss``, ImageMagick's ``import``) return an all-black image.  The supported way
to take a screenshot is the ``org.freedesktop.portal.Screenshot`` D-Bus API,
which is implemented by xdg-desktop-portal on GNOME, KDE and wlroots desktops.

On GNOME, the Shell's private screenshot service is both faster and silent when
called with ``flash=false``.  The Shell only accepts that call from a small
allow-list of well-known bus names, so the capture helper briefly acquires the
``org.gnome.Screenshot`` name while it takes the frame.  The portal remains the
portable fallback; event sounds are muted for the short portal round-trip so a
fallback never plays the camera-shutter sound.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import unquote, urlparse

from PIL import Image, ImageStat
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QScreen

# A frame is considered blank when it is both almost perfectly uniform and
# almost black.  This catches the classic XWayland / compositor failure mode
# (a valid image full of zeroes) while still accepting genuinely dark desktops.
_BLANK_STD_THRESHOLD = 1.0
_BLANK_MEAN_THRESHOLD = 8.0

_PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
_PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_SCREENSHOT_INTERFACE = "org.freedesktop.portal.Screenshot"
_PORTAL_REQUEST_INTERFACE = "org.freedesktop.portal.Request"


@dataclass
class ScreenCaptureResult:
    """A frozen frame of one screen.

    ``image`` is in *device* pixels while ``screen_geometry`` is in Qt's
    logical coordinate space.  Use :attr:`device_pixel_ratio` when translating
    between the two (see :meth:`ScreenCapture.crop_selection`).
    """

    image: Image.Image
    screen_geometry: QRect
    device_pixel_ratio: float = 1.0
    source: str = ""

    @property
    def is_valid(self) -> bool:
        return self.image is not None and self.image.width > 0 and self.image.height > 0

    @property
    def logical_size(self) -> QSize:
        return self.screen_geometry.size()


def is_wayland_session() -> bool:
    """Return True when the desktop session is Wayland (even if Qt runs via XWayland)."""
    if os.name == "nt":
        return False
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def is_gnome_session() -> bool:
    """Return True when the current desktop is GNOME-based."""
    if os.name == "nt":
        return False
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "gnome" in desktop or "unity" in desktop


@contextmanager
def _silenced_event_sounds() -> Iterator[None]:
    """Temporarily mute GNOME event sounds while the portal takes a screenshot.

    GNOME's portal implementation always passes ``flash=true`` to the Shell,
    which also plays the camera-shutter sound.  There is no portal option to
    disable it, so we suspend the event-sound setting for the lifetime of the
    request and restore it immediately afterwards.
    """
    restore: str | None = None
    if is_gnome_session() and shutil.which("gsettings") is not None:
        try:
            current = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.sound", "event-sounds"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if current.returncode == 0:
                value = current.stdout.strip()
                if value in {"true", "false"}:
                    restore = value
                    if value == "true":
                        subprocess.run(
                            [
                                "gsettings",
                                "set",
                                "org.gnome.desktop.sound",
                                "event-sounds",
                                "false",
                            ],
                            capture_output=True,
                            timeout=1.0,
                        )
                        # Let the Shell's GSettings client observe the change
                        # before the portal asks it for a screenshot.
                        time.sleep(0.03)
        except (OSError, subprocess.SubprocessError):
            restore = None

    try:
        yield
    finally:
        if restore is not None:
            try:
                subprocess.run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.sound",
                        "event-sounds",
                        restore,
                    ],
                    capture_output=True,
                    timeout=1.0,
                )
            except (OSError, subprocess.SubprocessError):
                pass


def has_visible_content(image: Image.Image | None) -> bool:
    """Reject uniform black frames produced by unsupported capture paths."""
    if image is None or image.width <= 0 or image.height <= 0:
        return False
    try:
        sample = image.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
        stats = ImageStat.Stat(sample)
        std_dev = float(stats.stddev[0])
        mean = float(stats.mean[0])
        return not (std_dev < _BLANK_STD_THRESHOLD and mean < _BLANK_MEAN_THRESHOLD)
    except Exception:
        # If validation itself fails, do not throw the frame away.
        return True


def _load_captured_image(path: str) -> Image.Image:
    """Load a capture file, detaching it from the open file handle.

    Avoiding a needless RGBA conversion matters here: decoding a 1080p PNG
    already costs ~100 ms, and converting an already-RGBA image doubles that.
    """
    with Image.open(path) as source:
        source.load()
        if source.mode == "RGBA":
            return source.copy()
        return source.convert("RGBA")


def qimage_to_pil(image: QImage) -> Image.Image:
    """Convert a QImage to a PIL image without relying on the source buffer lifetime."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    raw = bytes(image.constBits())
    pil = Image.frombuffer(
        "RGBA",
        (width, height),
        raw,
        "raw",
        "RGBA",
        stride,
        1,
    )
    return pil.copy()


def pil_to_pixmap(image: Image.Image, size: QSize | None = None) -> QPixmap:
    """Create a QPixmap on the GUI thread, optionally scaled to logical pixels."""
    if size is not None and size.width() > 0 and size.height() > 0:
        if image.width != size.width() or image.height != size.height():
            image = image.resize((size.width(), size.height()), Image.Resampling.LANCZOS)
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    # copy() detaches from the temporary Python bytes buffer.
    return QPixmap.fromImage(qimage.copy())


class ScreenCapture:
    """Takes a frozen frame of one screen across Windows, X11 and Wayland."""

    @staticmethod
    def get_virtual_geometry() -> QRect:
        """Combined geometry of all screens, in logical coordinates."""
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)

        left = min(s.geometry().left() for s in screens)
        top = min(s.geometry().top() for s in screens)
        right = max(s.geometry().right() for s in screens)
        bottom = max(s.geometry().bottom() for s in screens)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    @classmethod
    def capture_screen_fast(cls, screen: QScreen) -> ScreenCaptureResult | None:
        """Grab a single screen with Qt.  Must be called on the GUI thread.

        Returns ``None`` on Wayland (where this API is not supported) or when the
        result looks blank, so the caller can fall back to a portal capture.
        """
        if is_wayland_session():
            # Both native Wayland and XWayland grabs are unusable here.
            return None
        try:
            pixmap = screen.grabWindow(0)
            if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
                return None
            image = qimage_to_pil(pixmap.toImage())
        except Exception:
            return None

        if not has_visible_content(image):
            return None

        geometry = screen.geometry()
        ratio = image.width / geometry.width() if geometry.width() else 1.0
        return ScreenCaptureResult(
            image=image,
            screen_geometry=geometry,
            device_pixel_ratio=ratio,
            source="qt",
        )

    @classmethod
    def capture_for_screen(
        cls, screen_geometry: QRect, virtual_geometry: QRect
    ) -> ScreenCaptureResult | None:
        """Capture one screen using the best backend for the current session.

        This is blocking and safe to call off the GUI thread (it does not touch
        Qt widgets).  Returns ``None`` if every backend failed or produced a
        blank frame.
        """
        if is_wayland_session():
            if is_gnome_session():
                # GNOME's private service is ~3x faster than the portal and,
                # with flash disabled, is silent.
                backends = [
                    cls._capture_gnome_dbus,
                    cls._capture_portal,
                    cls._capture_cli_tools,
                ]
            else:
                backends = [cls._capture_portal, cls._capture_cli_tools]
        elif is_gnome_session():
            backends = [
                cls._capture_mss,
                cls._capture_gnome_dbus,
                cls._capture_portal,
                cls._capture_cli_tools,
            ]
        else:
            backends = [cls._capture_mss, cls._capture_portal, cls._capture_cli_tools]

        for backend in backends:
            try:
                image = backend(virtual_geometry)
            except Exception as exc:
                print(f"[ScreenCapture] {backend.__name__} failed: {exc}")
                continue
            if image is None:
                continue

            cropped, ratio = cls._crop_to_screen(image, virtual_geometry, screen_geometry)
            if not has_visible_content(cropped):
                print(
                    f"[ScreenCapture] {backend.__name__} returned a blank frame; trying next backend"
                )
                continue

            return ScreenCaptureResult(
                image=cropped,
                screen_geometry=screen_geometry,
                device_pixel_ratio=ratio,
                source=backend.__name__.removeprefix("_capture_"),
            )

        print("[ScreenCapture] All capture backends failed")
        return None

    @staticmethod
    def _crop_to_screen(
        image: Image.Image,
        virtual_geometry: QRect,
        screen_geometry: QRect,
    ) -> tuple[Image.Image, float]:
        """Crop a full-desktop image down to one screen and return its pixel ratio."""
        if virtual_geometry.width() <= 0 or virtual_geometry.height() <= 0:
            return image, 1.0

        scale_x = image.width / virtual_geometry.width()
        scale_y = image.height / virtual_geometry.height()

        left = int(round((screen_geometry.x() - virtual_geometry.x()) * scale_x))
        top = int(round((screen_geometry.y() - virtual_geometry.y()) * scale_y))
        right = int(round(left + screen_geometry.width() * scale_x))
        bottom = int(round(top + screen_geometry.height() * scale_y))

        left = max(0, min(left, image.width - 1))
        top = max(0, min(top, image.height - 1))
        right = max(left + 1, min(right, image.width))
        bottom = max(top + 1, min(bottom, image.height))

        # If the screen covers the whole desktop this is effectively a no-op.
        if (left, top, right, bottom) == (0, 0, image.width, image.height):
            return image, scale_x

        return image.crop((left, top, right, bottom)), scale_x

    @classmethod
    def _capture_portal(cls, virtual_geometry: QRect) -> Image.Image | None:
        """Capture through the portable portal, without the shutter sound."""
        with _silenced_event_sounds():
            return cls._capture_portal_silent(virtual_geometry)

    @classmethod
    def _capture_portal_silent(cls, virtual_geometry: QRect) -> Image.Image | None:
        """Capture via the xdg-desktop-portal Screenshot API (Wayland-safe)."""
        try:
            from jeepney import DBusAddress, MatchRule, new_method_call
            from jeepney.io.blocking import open_dbus_connection
        except ImportError:
            print("[ScreenCapture] jeepney is not installed; cannot use the desktop portal")
            return None

        started_at = time.time()
        connection = None
        try:
            connection = open_dbus_connection(bus="SESSION")
            portal = DBusAddress(
                _PORTAL_OBJECT_PATH,
                bus_name=_PORTAL_BUS_NAME,
                interface=_PORTAL_SCREENSHOT_INTERFACE,
            )

            token = f"mysticpointer_{os.getpid()}_{time.monotonic_ns()}"
            sender = connection.unique_name[1:].replace(".", "_")
            request_path = f"{_PORTAL_OBJECT_PATH}/request/{sender}/{token}"

            rule = MatchRule(
                type="signal",
                interface=_PORTAL_REQUEST_INTERFACE,
                member="Response",
                path=request_path,
            )

            with connection.filter(rule) as queue:
                message = new_method_call(
                    portal,
                    "Screenshot",
                    "sa{sv}",
                    (
                        "",
                        {
                            "interactive": ("b", False),
                            "modal": ("b", False),
                            "handle_token": ("s", token),
                        },
                    ),
                )
                connection.send_and_get_reply(message)
                response = connection.recv_until_filtered(queue, timeout=6.0)

            response_code, results = response.body
            if response_code != 0:
                # 1 = user cancelled, 2 = other error
                print(f"[ScreenCapture] Portal screenshot was not completed (code {response_code})")
                return None

            uri = results.get("uri")
            if isinstance(uri, tuple):  # jeepney wraps variant values
                uri = uri[1]
            if not isinstance(uri, str):
                return None

            path = unquote(urlparse(uri).path)
            if not os.path.isfile(path):
                return None

            image = _load_captured_image(path)

            # The portal writes its screenshot into the user's Pictures folder.
            # Remove the file we just caused, but only if it really is fresh, so
            # we never delete an unrelated user screenshot.
            try:
                if os.path.getmtime(path) >= started_at - 5:
                    os.remove(path)
            except OSError:
                pass

            return image
        except Exception as exc:
            print(f"[ScreenCapture] Portal capture failed: {exc}")
            return None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    @staticmethod
    def _capture_gnome_dbus(virtual_geometry: QRect) -> Image.Image | None:
        """Take a fast, silent frame through GNOME Shell's screenshot service.

        The Shell only lets allow-listed bus names use this API.  We briefly
        acquire the ``org.gnome.Screenshot`` name (released again in ``finally``)
        and call ``Screenshot`` with ``flash=false``, which skips both the screen
        flash and the camera-shutter sound.  If another screenshot tool owns the
        name, or the Shell rejects the call, the caller falls back to the portal.
        """
        if os.name == "nt" or not is_gnome_session():
            return None

        try:
            from jeepney import DBusAddress, new_method_call
            from jeepney.io.blocking import open_dbus_connection
        except ImportError:
            return None

        output_path = os.path.join(
            tempfile.gettempdir(),
            f"mystic_pointer_gnome_{os.getpid()}_{time.monotonic_ns()}.png",
        )
        connection = None
        name_acquired = False
        bus = DBusAddress(
            "/org/freedesktop/DBus",
            bus_name="org.freedesktop.DBus",
            interface="org.freedesktop.DBus",
        )
        try:
            connection = open_dbus_connection(bus="SESSION")

            # DBUS_NAME_FLAG_DO_NOT_QUEUE: never steal the name from a real
            # screenshot application that may be running.
            reply = connection.send_and_get_reply(
                new_method_call(
                    bus,
                    "RequestName",
                    "su",
                    ("org.gnome.Screenshot", 4),
                ),
                timeout=2.0,
            )
            if not reply.body or reply.body[0] not in (1, 4):
                return None
            name_acquired = True

            # Shell watches the allow-listed names asynchronously.  Give it a
            # moment to process NameOwnerChanged before invoking the service.
            time.sleep(0.02)

            screenshot = DBusAddress(
                "/org/gnome/Shell/Screenshot",
                bus_name="org.gnome.Shell.Screenshot",
                interface="org.gnome.Shell.Screenshot",
            )
            reply = connection.send_and_get_reply(
                new_method_call(
                    screenshot,
                    "Screenshot",
                    "bbs",
                    (False, False, output_path),
                ),
                timeout=4.0,
            )
            success = bool(reply.body[0]) if reply.body else False
            if not success or not os.path.isfile(output_path):
                return None

            return _load_captured_image(output_path)
        except Exception as exc:
            print(f"[ScreenCapture] GNOME Shell capture failed: {exc}")
            return None
        finally:
            if connection is not None and name_acquired:
                try:
                    connection.send_and_get_reply(
                        new_method_call(
                            bus,
                            "ReleaseName",
                            "s",
                            ("org.gnome.Screenshot",),
                        ),
                        timeout=1.0,
                    )
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass

    @staticmethod
    def _capture_cli_tools(virtual_geometry: QRect) -> Image.Image | None:
        """Capture with an installed desktop screenshot tool, if any."""
        if os.name == "nt":
            return None

        output_path = os.path.join(tempfile.gettempdir(), "mystic_pointer_cli.png")
        tools: list[list[str]] = []
        if is_wayland_session():
            tools = [
                ["grim", output_path],
                ["spectacle", "-b", "-n", "-o", output_path],
                ["gnome-screenshot", "-f", output_path],
            ]
        else:
            tools = [
                ["import", "-window", "root", output_path],
                ["gnome-screenshot", "-f", output_path],
                ["spectacle", "-b", "-n", "-o", output_path],
                ["grim", output_path],
            ]

        try:
            for command in tools:
                if shutil.which(command[0]) is None:
                    continue
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    result = subprocess.run(command, capture_output=True, timeout=5)
                    if result.returncode != 0 or not os.path.exists(output_path):
                        continue
                    if os.path.getsize(output_path) < 1000:
                        continue
                    return _load_captured_image(output_path)
                except Exception:
                    continue
        finally:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass
        return None

    @staticmethod
    def _capture_mss(virtual_geometry: QRect) -> Image.Image | None:
        """Multi-monitor capture via mss (Windows / X11 only)."""
        if os.name == "nt":
            pass
        elif is_wayland_session():
            # mss reads the XWayland root window, which is always black.
            return None

        try:
            import mss as mss_module

            factory = getattr(mss_module, "MSS", None) or mss_module.mss
            with factory() as capture:
                monitor = capture.monitors[0]  # all monitors combined
                shot = capture.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                return image.convert("RGBA")
        except Exception:
            return None

    @classmethod
    def capture_area(
        cls,
        rect: QRect,
        full_image: Image.Image | None,
        screen_geometry: QRect,
        device_pixel_ratio: float = 1.0,
    ) -> Image.Image | None:
        """Crop a selection from the frozen frame.

        The overlay always keeps the frozen frame for the lifetime of a session,
        so a second live capture is never needed (and would include the overlay
        itself on Wayland).
        """
        if full_image is None:
            return None
        return cls.crop_selection(full_image, rect, screen_geometry, device_pixel_ratio)

    @staticmethod
    def crop_selection(
        source_image: Image.Image,
        rect: QRect,
        screen_geometry: QRect,
        device_pixel_ratio: float = 1.0,
    ) -> Image.Image:
        """Crop a selection (logical coords) from a full-resolution screenshot."""
        ratio = device_pixel_ratio if device_pixel_ratio > 0 else 1.0
        left = int(round((rect.x() - screen_geometry.x()) * ratio))
        top = int(round((rect.y() - screen_geometry.y()) * ratio))
        right = int(round((rect.x() + rect.width() - screen_geometry.x()) * ratio))
        bottom = int(round((rect.y() + rect.height() - screen_geometry.y()) * ratio))

        left = max(0, min(left, source_image.width))
        top = max(0, min(top, source_image.height))
        right = max(left + 1, min(right, source_image.width))
        bottom = max(top + 1, min(bottom, source_image.height))

        return source_image.crop((left, top, right, bottom))
