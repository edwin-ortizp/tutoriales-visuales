from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication


WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_F9 = 0x78


class _WindowsMessageFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - API de Qt
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and int(msg.wParam) == self.hotkey_id:
                self.callback()
                return True, 0
        except (TypeError, ValueError):
            pass
        return False, 0


class GlobalCaptureHotkey(QObject):
    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.hotkey_id = 0x5C81
        self.window_handle: int | None = None
        self._filter = _WindowsMessageFilter(self.hotkey_id, self._queue_activation)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    def register(self, window_handle: int) -> bool:
        if sys.platform != "win32":
            return False
        self.unregister()
        result = ctypes.windll.user32.RegisterHotKey(
            wintypes.HWND(window_handle),
            self.hotkey_id,
            MOD_CONTROL | MOD_SHIFT,
            VK_F9,
        )
        if result:
            self.window_handle = window_handle
            return True
        return False

    def _queue_activation(self) -> None:
        # La captura puede ser costosa; se ejecuta después de devolver el mensaje
        # nativo a Windows para no bloquear el procesamiento de WM_HOTKEY.
        QTimer.singleShot(0, self.activated.emit)

    def unregister(self) -> None:
        if sys.platform == "win32" and self.window_handle is not None:
            ctypes.windll.user32.UnregisterHotKey(
                wintypes.HWND(self.window_handle), self.hotkey_id
            )
            self.window_handle = None

    def close(self) -> None:
        self.unregister()
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._filter)
