"""Single-instance activation IPC.

Wayland compositors do not let an application register global hotkeys or read
the global cursor position.  The portable workaround is a system-level shortcut
that runs ``mystic-pointer --activate``; this module forwards that invocation to
the already-running tray process over a per-user local socket.
"""

from __future__ import annotations

import getpass
import os
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SERVER_NAME = f"mystic-pointer-{getpass.getuser()}"
_MESSAGE = b"activate"


def notify_running_instance(timeout_ms: int = 1200) -> bool:
    """Ask an existing Mystic Pointer instance to activate.

    Returns True when a running instance accepted the request.  Retries briefly
    so a shortcut pressed during application startup does not spawn a second
    copy.  Intentionally avoids creating a QCoreApplication so the caller can
    fall through to a normal QApplication startup when no instance is running.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(250):
            socket.write(_MESSAGE)
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            socket.abort()
            return True
        socket.abort()
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


class ActivationServer(QObject):
    """Receives activation requests from the ``--activate`` command line."""

    activated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        # Remove a stale socket left behind by a crash.
        QLocalServer.removeServer(_SERVER_NAME)
        if not self._server.listen(_SERVER_NAME):
            print(
                f"[MysticPointer] Could not start activation socket: {self._server.errorString()}"
            )
        else:
            print(f"[MysticPointer] Activation socket ready ({_SERVER_NAME})")
        self._server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda s=socket: self._on_ready_read(s))
            socket.disconnected.connect(socket.deleteLater)
            # The whole message is tiny and normally already buffered.
            self._on_ready_read(socket)

    def _on_ready_read(self, socket: QLocalSocket) -> None:
        if socket.bytesAvailable() <= 0:
            return
        if _MESSAGE in socket.readAll().data():
            self.activated.emit()
        socket.disconnectFromServer()

    @property
    def is_listening(self) -> bool:
        return self._server.isListening()

    def close(self) -> None:
        self._server.close()
        if os.name != "nt":
            QLocalServer.removeServer(_SERVER_NAME)
