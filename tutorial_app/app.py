from __future__ import annotations

import argparse
import ctypes
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .capture import configure_dpi_awareness
from .exporter import build_html
from .image_tools import normalize_to_png, render_step_image
from .main_window import MainWindow
from .models import RichText, TextMark, TutorialProject, TutorialStep
from .resources import resource_path
from .single_instance import SingleInstanceController, SingleInstanceError


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="TutorialesVisuales", add_help=True)
    parser.add_argument("project", nargs="?", help="Proyecto .tutorial que se desea abrir")
    parser.add_argument("--version", action="store_true", help="Muestra la versión instalada")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Valida dependencias y render sin abrir la interfaz",
    )
    return parser.parse_args(argv)


def _print_or_show_version() -> None:
    message = f"Tutoriales Visuales {__version__}"
    if sys.stdout is not None:
        print(message)
    elif sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "Tutoriales Visuales", 0x40)


def run_smoke_test() -> int:
    try:
        source = normalize_to_png(Image.new("RGB", (320, 180), "white"))
        rendered = render_step_image(source, 0.5, 0.5, 1.0, annotations=[])
        with Image.open(BytesIO(rendered)) as image:
            if image.format != "WEBP" or image.size != (320, 180):
                return 2
        sample = TutorialProject(
            description=RichText("Ayuda", [TextMark("bold", 0, 5)]),
            steps=[
                TutorialStep(
                    instruction=RichText(
                        "Abrir ayuda", [TextMark("link", 0, 11, "https://example.com")]
                    ),
                    image_png=source,
                    visual_reviewed=True,
                )
            ],
        )
        exported = build_html(sample)
        if (
            "<strong>Ayuda</strong>" not in exported
            or 'href="https://example.com"' not in exported
            or "Paso 1 de 1" not in exported
            or "Comenzar tutorial" not in exported
            or "Tiempo estimado" not in exported
            or 'class="reading-rail"' not in exported
            or "Tutorial completado" not in exported
            or "IntersectionObserver" not in exported
        ):
            return 3
        if sys.stdout is not None:
            print(f"Tutoriales Visuales {__version__}: smoke test OK")
        return 0
    except Exception as exc:  # el smoke test debe traducir cualquier fallo a exit code
        if sys.stderr is not None:
            print(f"Smoke test falló: {exc}", file=sys.stderr)
        return 1


def _command_for_project(project: str | None) -> dict[str, object]:
    if project:
        return {"action": "open", "path": str(Path(project).resolve())}
    return {"action": "activate"}


def _set_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "TutorialesVisuales.App"
            )
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(list(sys.argv[1:] if argv is None else argv))
    if arguments.version:
        _print_or_show_version()
        return 0
    if arguments.smoke_test:
        return run_smoke_test()

    configure_dpi_awareness()
    _set_windows_app_id()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Tutoriales Visuales")
    app.setApplicationDisplayName("Tutoriales Visuales")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Tutoriales Visuales")
    icon_path = resource_path("assets/tutoriales-visuales.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    command = _command_for_project(arguments.project)
    controller = SingleInstanceController()
    try:
        if not controller.initialize(command):
            return 0
    except SingleInstanceError as exc:
        QMessageBox.critical(None, "No se pudo iniciar", str(exc))
        return 3

    window = MainWindow()
    from .update_ui import UpdateController
    window.update_controller = UpdateController(window)
    controller.commandReceived.connect(window.handle_external_command)
    window.show()
    project_path = str(Path(arguments.project).resolve()) if arguments.project else None
    QTimer.singleShot(0, lambda: window.initialize_startup(project_path))

    result = app.exec()
    controller.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
