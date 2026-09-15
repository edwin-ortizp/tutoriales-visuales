import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from tutorial_app.image_tools import normalize_to_png
from tutorial_app.models import RichText, TutorialProject, TutorialStep
from tutorial_app.recovery import (
    InvalidRecoveryError,
    RecoveryManager,
    RecoveryMetadata,
    read_recovery,
    write_recovery_candidate,
)


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def sample_project() -> TutorialProject:
    return TutorialProject(
        title="Trabajo recuperable",
        description=RichText("Descripción"),
        steps=[
            TutorialStep(
                instruction=RichText("Paso pendiente"),
                image_png=normalize_to_png(Image.new("RGB", (160, 90), "white")),
            )
        ],
    )


def wait_for(predicate, timeout: float = 5.0) -> bool:
    application = app()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_recovery_round_trip_and_source_change_detection(tmp_path: Path) -> None:
    source = tmp_path / "original.tutorial"
    source.write_bytes(b"original")
    metadata = RecoveryMetadata.capture(source)
    target = tmp_path / "active.tutorial"

    write_recovery_candidate(target, sample_project(), metadata)
    recovered = read_recovery(target)

    assert recovered.project.title == "Trabajo recuperable"
    assert recovered.source_is_unchanged() is True
    source.write_bytes("cambió".encode("utf-8"))
    assert recovered.source_is_unchanged() is False


def test_invalid_recovery_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "active.tutorial"
    target.write_bytes(b"no es zip")
    with pytest.raises(InvalidRecoveryError):
        read_recovery(target)


def test_manager_writes_atomically_and_clear_invalidates_pending_result(tmp_path: Path) -> None:
    application = app()
    project = sample_project()
    manager = RecoveryManager(lambda: (project, None), directory=tmp_path, interval_ms=20)
    try:
        manager.mark_dirty()
        assert wait_for(manager.has_recovery)
        assert manager.inspect().project.title == project.title

        project.title = "No debe reaparecer"
        manager.mark_dirty()
        manager._write_if_needed()
        manager.clear()
        manager.pool.waitForDone(5000)
        application.processEvents()
        assert manager.has_recovery() is False
    finally:
        manager.shutdown()


def test_manager_reports_unwritable_recovery_location(tmp_path: Path) -> None:
    app()
    blocked = tmp_path / "blocked"
    blocked.write_text("archivo, no directorio", encoding="utf-8")
    errors: list[str] = []
    manager = RecoveryManager(
        lambda: (sample_project(), None), directory=blocked, interval_ms=60_000
    )
    manager.writeFailed.connect(errors.append)
    try:
        manager.mark_dirty()
        manager._write_if_needed()
        assert errors
        assert manager.has_recovery() is False
    finally:
        manager.shutdown()
