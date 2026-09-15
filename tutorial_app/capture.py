from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from io import BytesIO

from PIL import ImageGrab

from .image_tools import normalize_to_png


class CaptureError(RuntimeError):
    pass


@dataclass(slots=True)
class CapturedWindow:
    title: str
    image_png: bytes
    hwnd: int


def configure_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def foreground_window_handle() -> int:
    if sys.platform != "win32":
        raise CaptureError("La captura de ventanas solo está disponible en Windows.")
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    if not hwnd:
        raise CaptureError("No se encontró una ventana activa para capturar.")
    return hwnd


def _window_title(hwnd: int) -> str:
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _window_bounds(hwnd: int) -> tuple[int, int, int, int]:
    from ctypes import wintypes

    rect = wintypes.RECT()
    try:
        dwmapi = ctypes.windll.dwmapi
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            9,  # DWMWA_EXTENDED_FRAME_BOUNDS
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if result != 0:
            raise OSError(result)
    except (AttributeError, OSError):
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise CaptureError("No fue posible obtener el tamaño de la ventana activa.")

    bounds = (rect.left, rect.top, rect.right, rect.bottom)
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise CaptureError("La ventana activa no tiene un área visible válida.")
    return bounds


def capture_foreground_window(*, excluded_hwnd: int | None = None) -> CapturedWindow:
    hwnd = foreground_window_handle()
    if excluded_hwnd and hwnd == int(excluded_hwnd):
        raise CaptureError("Cambia a la ventana que deseas capturar y usa Ctrl+Shift+F9.")
    bounds = _window_bounds(hwnd)
    try:
        image = ImageGrab.grab(bbox=bounds, all_screens=True)
    except OSError as exc:
        raise CaptureError("Windows no permitió capturar la ventana activa.") from exc
    output = BytesIO()
    image.save(output, format="PNG")
    return CapturedWindow(
        title=_window_title(hwnd) or "Ventana capturada",
        image_png=normalize_to_png(output.getvalue()),
        hwnd=hwnd,
    )
