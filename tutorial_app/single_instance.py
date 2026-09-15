from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "TutorialesVisuales-7f0d71c7-99bb-4b22-98a2-53b3e591b925"
APP_MUTEX_NAME = "TutorialesVisuales.App.7f0d71c7-99bb-4b22-98a2-53b3e591b925"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceError(RuntimeError):
    pass


class WindowsAppMutex:
    def __init__(self, name: str = APP_MUTEX_NAME) -> None:
        self.name = name
        self.handle: int | None = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise SingleInstanceError("Windows no permitió crear el identificador de la aplicación.")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self.handle = int(handle)
        return True

    def close(self) -> None:
        if sys.platform == "win32" and self.handle:
            ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = None


class SingleInstanceController(QObject):
    commandReceived = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        server_name: str = SERVER_NAME,
        mutex_name: str = APP_MUTEX_NAME,
    ) -> None:
        super().__init__(parent)
        self.server_name = server_name
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._receive_connections)
        self.mutex = WindowsAppMutex(mutex_name)
        self.is_primary = False

    @staticmethod
    def _encoded(command: dict[str, object]) -> bytes:
        return json.dumps(command, ensure_ascii=False).encode("utf-8")

    def _forward(self, command: dict[str, object], timeout_ms: int = 500) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(timeout_ms):
            return False
        payload = self._encoded(command)
        if socket.write(payload) != len(payload):
            socket.abort()
            return False
        socket.flush()
        if socket.bytesToWrite() > 0:
            socket.waitForBytesWritten(timeout_ms)
        # La instancia receptora cierra el canal después de leer. Esperar ese cierre
        # evita que el proceso secundario termine antes de que el comando sea consumido.
        if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            if not socket.waitForDisconnected(timeout_ms):
                socket.abort()
                return False
        return True

    def initialize(self, command: dict[str, object]) -> bool:
        """Devuelve True para la instancia primaria y reenvía si ya existe otra."""

        if self._forward(command):
            return False
        if not self.mutex.acquire():
            # La instancia primaria puede estar entre la creación del mutex y el servidor.
            for _ in range(8):
                if self._forward(command, 250):
                    return False
            raise SingleInstanceError(
                "Ya existe una instancia, pero no fue posible comunicarse con ella."
            )

        QLocalServer.removeServer(self.server_name)
        if not self.server.listen(self.server_name):
            self.mutex.close()
            if self._forward(command):
                return False
            raise SingleInstanceError("No fue posible iniciar el canal de instancia única.")
        self.is_primary = True
        return True

    def _receive_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            if not socket.bytesAvailable():
                socket.waitForReadyRead(300)
            raw = bytes(socket.readAll())
            socket.disconnectFromServer()
            try:
                command = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(command, dict):
                self.commandReceived.emit(command)

    def close(self) -> None:
        if self.is_primary:
            self.server.close()
            QLocalServer.removeServer(self.server_name)
            self.is_primary = False
        self.mutex.close()
