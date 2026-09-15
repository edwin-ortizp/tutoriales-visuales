import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from tutorial_app.image_tools import normalize_to_png
from tutorial_app.main_window import MainWindow
from tutorial_app.models import RichText, TutorialProject, TutorialStep
from tutorial_app.project_io import save_project
from tutorial_app.recovery import RecoveryMetadata, write_recovery_candidate


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def project(title: str) -> TutorialProject:
    return TutorialProject(
        title=title,
        steps=[
            TutorialStep(
                instruction=RichText("Instrucción"),
                image_png=normalize_to_png(Image.new("RGB", (160, 90), "white")),
            )
        ],
    )


def test_startup_recovery_takes_priority_over_requested_project(
    tmp_path: Path, monkeypatch
) -> None:
    application = app()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    source = save_project(tmp_path / "original.tutorial", project("Original"))
    requested = save_project(tmp_path / "solicitado.tutorial", project("Solicitado"))
    recovery_path = tmp_path / "appdata" / "Tutoriales Visuales" / "recovery" / "active.tutorial"
    recovery_path.parent.mkdir(parents=True)
    write_recovery_candidate(
        recovery_path, project("Recuperado"), RecoveryMetadata.capture(source)
    )

    def choose_recover(box: QMessageBox) -> int:
        button = next(item for item in box.buttons() if item.text() == "Recuperar")
        button.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", choose_recover)
    window = MainWindow()
    try:
        window.initialize_startup(requested)
        application.processEvents()
        assert window.project.title == "Recuperado"
        assert window.project_path == source
        assert window.dirty is True
        assert window.recovery.has_recovery() is True
    finally:
        window.dirty = False
        window.recovery.clear()
        window.close()
        application.processEvents()
