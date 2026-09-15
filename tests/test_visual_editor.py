import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tutorial_app.image_tools import normalize_to_png
from tutorial_app.main_window import VisualStateCommand
from tutorial_app.models import TutorialStep
from tutorial_app.widgets import VisualEditorCanvas


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_step() -> TutorialStep:
    return TutorialStep(
        title="Paso",
        image_png=normalize_to_png(Image.new("RGB", (800, 500), "white")),
    )


def test_canvas_creates_moves_and_deletes_marker() -> None:
    application = app()
    canvas = VisualEditorCanvas()
    canvas.resize(900, 650)
    canvas.show()
    step = make_step()
    canvas.set_step(step)
    application.processEvents()
    commits: list[str] = []
    canvas.visualEditCommitted.connect(lambda before, after, text: commits.append(text))

    canvas.set_mode("marker")
    initial = canvas._norm_to_widget(0.3, 0.4).toPoint()
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=initial)

    assert len(step.annotations) == 1
    assert step.annotations[0].type == "marker"
    assert commits[-1] == "Agregar marcador"

    canvas.set_mode("select")
    destination = canvas._norm_to_widget(0.6, 0.7).toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=initial)
    QTest.mouseMove(canvas, destination, delay=10)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=destination)

    assert step.annotations[0].x1 > 0.5
    assert step.annotations[0].y1 > 0.6
    canvas.delete_selected()
    assert step.annotations == []
    assert commits[-1] == "Eliminar anotación"
    canvas.close()


def test_canvas_creates_crop_and_secure_redaction() -> None:
    application = app()
    canvas = VisualEditorCanvas()
    canvas.resize(900, 650)
    canvas.show()
    step = make_step()
    canvas.set_step(step)
    application.processEvents()

    start = canvas._norm_to_widget(0.2, 0.2).toPoint()
    end = canvas._norm_to_widget(0.8, 0.8).toPoint()
    canvas.set_mode("crop")
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end, delay=10)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

    assert step.crop is not None
    assert step.crop.width > 0.5
    assert step.crop.height > 0.5

    canvas.set_mode("redaction_solid")
    redact_start = canvas._norm_to_widget(0.35, 0.35).toPoint()
    redact_end = canvas._norm_to_widget(0.55, 0.48).toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=redact_start)
    QTest.mouseMove(canvas, redact_end, delay=10)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=redact_end)

    assert len(step.annotations) == 1
    assert step.annotations[0].type == "redaction_solid"
    assert step.visual_reviewed is True
    canvas.close()


class DummyWindow:
    def __init__(self) -> None:
        self.state = None

    def _apply_visual_state(self, step_id, state) -> None:
        self.state = state


def test_visual_commands_undo_redo_and_merge_zoom() -> None:
    app()
    stack = QUndoStack()
    window = DummyWindow()
    before = {"zoom": 1.0}
    middle = {"zoom": 1.5}
    after = {"zoom": 2.0}

    stack.push(VisualStateCommand(window, "step", before, middle, "Zoom", merge_key="zoom"))
    stack.push(VisualStateCommand(window, "step", middle, after, "Zoom", merge_key="zoom"))

    assert stack.count() == 1
    assert window.state == after
    stack.undo()
    assert window.state == before
    stack.redo()
    assert window.state == after
