from __future__ import annotations

import re
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QKeySequence,
    QPixmap,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QApplication,
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .capture import CaptureError, capture_foreground_window
from .exporter import collect_export_warnings, export_html
from .hotkey import GlobalCaptureHotkey
from .image_tools import InvalidImageError, normalize_to_png, render_step_image
from .models import RichText, TutorialProject, TutorialStep, normalize_color
from .project_io import InvalidProjectError, load_project, save_project
from .recovery import InvalidRecoveryError, RecoveryManager
from .rich_text import RichTextEditor, SafeRichTextEdit
from .widgets import PreviewCanvas, VisualEditorCanvas
from . import __version__


class VisualStateCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        step_id: str,
        before: dict[str, object],
        after: dict[str, object],
        description: str,
        *,
        merge_key: str | None = None,
    ) -> None:
        super().__init__(description)
        self.window = window
        self.step_id = step_id
        self.before = before
        self.after = after
        self.merge_key = merge_key

    def undo(self) -> None:
        self.window._apply_visual_state(self.step_id, self.before)

    def redo(self) -> None:
        self.window._apply_visual_state(self.step_id, self.after)

    def id(self) -> int:
        return 2048 if self.merge_key == "zoom" else -1

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802
        if not isinstance(other, VisualStateCommand):
            return False
        if not self.merge_key or self.merge_key != other.merge_key or self.step_id != other.step_id:
            return False
        self.after = other.after
        return True


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = TutorialProject()
        self.project_path: Path | None = None
        self.preview_path: Path | None = None
        self.dirty = False
        self._loading = False
        self._recovered_force_save_as = False
        self._recovery_warning_shown = False
        self.undo_stack = QUndoStack(self)
        self.setMinimumSize(1220, 760)
        self.resize(1500, 900)

        self._build_actions()
        self._build_ui()
        self._connect_signals()

        self.hotkey = GlobalCaptureHotkey(self)
        self.hotkey.activated.connect(self._capture_from_hotkey)
        registered = self.hotkey.register(int(self.winId()))
        if registered:
            self.statusBar().showMessage(
                "Listo. Usa Ctrl+Shift+F9 sobre cualquier ventana para capturarla."
            )
        else:
            self.statusBar().showMessage(
                "Ctrl+Shift+F9 no está disponible; importa imágenes o usa la captura con temporizador."
            )

        self._show_project()
        self._set_dirty(False)
        self.recovery = RecoveryManager(self._recovery_snapshot, self)
        self.recovery.writeFailed.connect(self._recovery_failed)
        self.recovery.recoveryWritten.connect(
            lambda _: self.statusBar().showMessage("Copia de recuperación actualizada.", 2500)
        )

    def _build_actions(self) -> None:
        self.action_new = QAction("Nuevo", self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_open = QAction("Abrir…", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_save = QAction("Guardar", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save_as = QAction("Guardar como…", self)
        self.action_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.action_import = QAction("Importar imágenes…", self)
        self.action_import.setShortcut("Ctrl+I")
        self.action_capture_delay = QAction("Capturar ventana en 3 segundos", self)
        self.action_preview = QAction("Vista previa completa", self)
        self.action_preview.setShortcut("F5")
        self.action_export = QAction("Exportar HTML…", self)
        self.action_export.setShortcut("Ctrl+E")
        self.action_export_open = QAction("Exportar y abrir…", self)
        self.action_export_open.setShortcut("Ctrl+Shift+E")
        self.action_exit = QAction("Salir", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_undo = QAction("Deshacer", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_redo = QAction("Rehacer", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)

        file_menu = self.menuBar().addMenu("&Archivo")
        for action in (self.action_new, self.action_open, self.action_save, self.action_save_as):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.action_import)
        file_menu.addAction(self.action_preview)
        file_menu.addAction(self.action_export)
        file_menu.addAction(self.action_export_open)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        edit_menu = self.menuBar().addMenu("&Editar")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)

        capture_menu = self.menuBar().addMenu("&Captura")
        capture_menu.addAction(self.action_capture_delay)

        toolbar = QToolBar("Acciones principales", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for action in (
            self.action_new,
            self.action_open,
            self.action_save,
            self.action_undo,
            self.action_redo,
            self.action_import,
            self.action_capture_delay,
            self.action_preview,
            self.action_export,
        ):
            toolbar.addAction(action)

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        guide_group = QGroupBox("Información e identidad del tutorial")
        guide_layout = QFormLayout(guide_group)
        self.guide_title = QLineEdit()
        self.guide_title.setPlaceholderText("Ej. Cómo registrar una tarea")
        self.guide_description = RichTextEditor("Una breve introducción opcional")
        self.guide_description.setMaximumHeight(126)
        guide_layout.addRow("Título:", self.guide_title)
        guide_layout.addRow("Descripción:", self.guide_description)

        identity_widget = QWidget()
        identity_layout = QHBoxLayout(identity_widget)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        self.brand_name = QLineEdit()
        self.brand_name.setPlaceholderText("Nombre de la plataforma")
        self.brand_name.setMaximumWidth(280)
        self.color_button = QPushButton("Color principal")
        self.logo_preview = QLabel("Sin logo")
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_preview.setFixedSize(130, 44)
        self.logo_preview.setStyleSheet("border:1px solid #d0d5dd;border-radius:6px;color:#667085")
        self.logo_button = QPushButton("Elegir logo…")
        self.remove_logo_button = QPushButton("Quitar")
        identity_layout.addWidget(self.brand_name, 1)
        identity_layout.addWidget(self.color_button)
        identity_layout.addWidget(self.logo_preview)
        identity_layout.addWidget(self.logo_button)
        identity_layout.addWidget(self.remove_logo_button)
        guide_layout.addRow("Identidad:", identity_widget)
        root_layout.addWidget(guide_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_step_panel())
        splitter.addWidget(self._build_image_panel())
        splitter.addWidget(self._build_edit_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 880, 330])
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def _build_step_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(QLabel("Pasos"))
        self.step_list = QListWidget()
        self.step_list.setMinimumWidth(220)
        layout.addWidget(self.step_list, 1)
        self.import_button = QPushButton("Importar captura(s)")
        self.capture_button = QPushButton("Capturar en 3 s")
        self.replace_button = QPushButton("Reemplazar imagen")
        layout.addWidget(self.import_button)
        layout.addWidget(self.capture_button)
        layout.addWidget(self.replace_button)
        row = QHBoxLayout()
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        self.delete_button = QPushButton("Eliminar")
        row.addWidget(self.up_button)
        row.addWidget(self.down_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        return panel

    def _build_image_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)

        tool_row = QHBoxLayout()
        self.visual_tool_group = QButtonGroup(self)
        self.visual_tool_group.setExclusive(True)
        self.visual_tool_buttons: dict[str, QToolButton] = {}
        tools = [
            ("select", "Seleccionar", "Seleccionar, mover o redimensionar una anotación"),
            ("crop", "Recortar", "Dibujar el área visible"),
            ("focus", "Centro zoom", "Elegir el centro independiente del zoom"),
            ("marker", "Marcador", "Agregar un punto de atención"),
            ("arrow", "Flecha", "Arrastrar para crear una flecha"),
            ("rectangle", "Rectángulo", "Arrastrar para destacar un área"),
            ("redaction_solid", "Ocultar", "Bloque sólido seguro"),
            ("redaction_blur", "Desenfocar", "Desenfoque visual"),
        ]
        for index, (mode, label, tooltip) in enumerate(tools):
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.setAutoRaise(False)
            button.clicked.connect(lambda checked=False, selected=mode: self._set_visual_mode(selected))
            self.visual_tool_group.addButton(button, index)
            self.visual_tool_buttons[mode] = button
            tool_row.addWidget(button)
        self.visual_tool_buttons["select"].setChecked(True)
        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        command_row = QHBoxLayout()
        self.delete_annotation_button = QPushButton("Eliminar anotación")
        self.reset_crop_button = QPushButton("Restablecer recorte")
        command_row.addWidget(self.delete_annotation_button)
        command_row.addWidget(self.reset_crop_button)
        command_row.addStretch(1)
        layout.addLayout(command_row)

        self.image_tabs = QTabWidget()
        self.edit_canvas = VisualEditorCanvas()
        self.preview_canvas = PreviewCanvas()
        self.image_tabs.addTab(self.edit_canvas, "Editar imagen")
        self.image_tabs.addTab(self.preview_canvas, "Vista final del paso")
        layout.addWidget(self.image_tabs, 1)
        help_label = QLabel(
            "El bloque “Ocultar” elimina visualmente los datos en la exportación. "
            "“Desenfocar” es una alternativa estética menos segura."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color:#667085")
        layout.addWidget(help_label)
        return panel

    def _build_edit_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        form = QFormLayout()
        self.step_title = QLineEdit()
        self.step_title.setPlaceholderText("Ej. Selecciona Nueva tarea")
        self.step_instruction = RichTextEditor("Escribe qué debe hacer el usuario")
        self.step_instruction.setMinimumHeight(210)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 30)
        self.zoom_slider.setSingleStep(1)
        self.zoom_slider.setValue(10)
        self.zoom_value = QLabel("1.0×")
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value)
        self.reviewed_check = QCheckBox("Revisión visual completada")
        self.visual_summary = QLabel("Sin anotaciones")
        self.visual_summary.setWordWrap(True)
        self.visual_summary.setStyleSheet("color:#667085")
        form.addRow("Título del paso:", self.step_title)
        form.addRow("Instrucción:", self.step_instruction)
        form.addRow("Zoom:", zoom_row)
        form.addRow("Estado:", self.reviewed_check)
        form.addRow("Elementos:", self.visual_summary)
        layout.addLayout(form)
        layout.addStretch(1)
        hotkey_help = QLabel(
            "Captura rápida\n\n1. Abre la ventana objetivo.\n"
            "2. Presiona Ctrl+Shift+F9.\n"
            "3. Revisa privacidad, recorte y anotaciones."
        )
        hotkey_help.setWordWrap(True)
        hotkey_help.setStyleSheet(
            "background:#eef4ff;border:1px solid #c9dcff;border-radius:8px;padding:12px;color:#344054"
        )
        layout.addWidget(hotkey_help)
        return panel

    def _connect_signals(self) -> None:
        self.action_new.triggered.connect(self._new_project)
        self.action_open.triggered.connect(self._open_project)
        self.action_save.triggered.connect(self._save_project)
        self.action_save_as.triggered.connect(lambda: self._save_project(save_as=True))
        self.action_import.triggered.connect(self._import_images)
        self.action_capture_delay.triggered.connect(self._capture_with_delay)
        self.action_preview.triggered.connect(self._preview_full_guide)
        self.action_export.triggered.connect(lambda: self._export_html(open_after=False))
        self.action_export_open.triggered.connect(lambda: self._export_html(open_after=True))
        self.action_exit.triggered.connect(self.close)
        self.action_undo.triggered.connect(self._undo_contextual)
        self.action_redo.triggered.connect(self._redo_contextual)

        self.import_button.clicked.connect(self._import_images)
        self.capture_button.clicked.connect(self._capture_with_delay)
        self.replace_button.clicked.connect(self._replace_image)
        self.delete_button.clicked.connect(self._delete_step)
        self.up_button.clicked.connect(lambda: self._move_step(-1))
        self.down_button.clicked.connect(lambda: self._move_step(1))
        self.delete_annotation_button.clicked.connect(self.edit_canvas.delete_selected)
        self.reset_crop_button.clicked.connect(self.edit_canvas.clear_crop)

        self.guide_title.textChanged.connect(self._guide_changed)
        self.guide_description.contentChanged.connect(self._guide_changed)
        self.brand_name.textChanged.connect(self._branding_changed)
        self.color_button.clicked.connect(self._choose_color)
        self.logo_button.clicked.connect(self._choose_logo)
        self.remove_logo_button.clicked.connect(self._remove_logo)
        self.step_list.currentRowChanged.connect(self._load_step)
        self.step_title.textChanged.connect(self._step_changed)
        self.step_instruction.contentChanged.connect(self._step_changed)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.reviewed_check.toggled.connect(self._reviewed_changed)
        self.edit_canvas.visualEditCommitted.connect(self._visual_edit_committed)
        self.edit_canvas.selectionChanged.connect(self.delete_annotation_button.setEnabled)
        self.undo_stack.indexChanged.connect(lambda _: self._set_dirty(True))
        self.undo_stack.canUndoChanged.connect(lambda _: self._update_undo_actions())
        self.undo_stack.canRedoChanged.connect(lambda _: self._update_undo_actions())
        for editor in (self.guide_description.editor, self.step_instruction.editor):
            editor.document().undoAvailable.connect(lambda _: self._update_undo_actions())
            editor.document().redoAvailable.connect(lambda _: self._update_undo_actions())
        app = QApplication.instance()
        if app:
            app.focusChanged.connect(lambda _old, _new: self._update_undo_actions())

    def _selected_step(self) -> TutorialStep | None:
        row = self.step_list.currentRow()
        return self.project.steps[row] if 0 <= row < len(self.project.steps) else None

    def _focused_rich_editor(self) -> SafeRichTextEdit | None:
        focus = QApplication.focusWidget()
        for editor in (self.guide_description.editor, self.step_instruction.editor):
            if focus is editor or (focus is not None and editor.isAncestorOf(focus)):
                return editor
        return None

    def _undo_contextual(self) -> None:
        editor = self._focused_rich_editor()
        if editor:
            editor.undo()
        else:
            self.undo_stack.undo()
        self._update_undo_actions()

    def _redo_contextual(self) -> None:
        editor = self._focused_rich_editor()
        if editor:
            editor.redo()
        else:
            self.undo_stack.redo()
        self._update_undo_actions()

    def _update_undo_actions(self) -> None:
        editor = self._focused_rich_editor()
        if editor:
            self.action_undo.setEnabled(editor.document().isUndoAvailable())
            self.action_redo.setEnabled(editor.document().isRedoAvailable())
        else:
            self.action_undo.setEnabled(self.undo_stack.canUndo())
            self.action_redo.setEnabled(self.undo_stack.canRedo())

    def _show_project(self, selected_row: int = 0) -> None:
        self._loading = True
        self.guide_title.setText(self.project.title)
        self.guide_description.set_structured_text(self.project.description)
        self.brand_name.setText(self.project.brand_name)
        self._update_brand_controls()
        self.step_list.clear()
        for index, step in enumerate(self.project.steps, start=1):
            self.step_list.addItem(f"{index}. {step.title.strip() or f'Paso {index}'}")
        if self.project.steps:
            selected_row = max(0, min(selected_row, len(self.project.steps) - 1))
            self.step_list.setCurrentRow(selected_row)
        self._loading = False
        self._load_step(self.step_list.currentRow())
        self._update_enabled_state()
        self._update_window_title()

    def _load_step(self, row: int) -> None:
        if self._loading:
            return
        self._loading = True
        if 0 <= row < len(self.project.steps):
            step = self.project.steps[row]
            self.step_title.setText(step.title)
            self.step_instruction.set_structured_text(step.instruction)
            self.zoom_slider.setValue(round(step.zoom * 10))
            self.zoom_value.setText(f"{step.zoom:.1f}×")
            self.reviewed_check.setChecked(step.visual_reviewed)
            self.edit_canvas.set_step(step)
            self.edit_canvas.set_accent_color(self.project.accent_color)
            self._update_preview(step)
            self._update_visual_summary(step)
        else:
            self.step_title.clear()
            self.step_instruction.clear()
            self.zoom_slider.setValue(10)
            self.zoom_value.setText("1.0×")
            self.reviewed_check.setChecked(False)
            self.edit_canvas.set_step(None)
            self.preview_canvas.clear_image()
            self.visual_summary.setText("Sin anotaciones")
        self._loading = False
        self._update_enabled_state()

    def _guide_changed(self) -> None:
        if self._loading:
            return
        self.project.title = self.guide_title.text()
        self.project.description = self.guide_description.structured_text()
        self._set_dirty(True)

    def _branding_changed(self) -> None:
        if self._loading:
            return
        self.project.brand_name = self.brand_name.text()
        self._set_dirty(True)

    def _step_changed(self) -> None:
        if self._loading:
            return
        step = self._selected_step()
        if not step:
            return
        step.title = self.step_title.text()
        step.instruction = self.step_instruction.structured_text()
        row = self.step_list.currentRow()
        item = self.step_list.item(row)
        if item:
            item.setText(f"{row + 1}. {step.title.strip() or f'Paso {row + 1}'}")
        self._set_dirty(True)

    def _zoom_changed(self, value: int) -> None:
        self.zoom_value.setText(f"{value / 10:.1f}×")
        if self._loading:
            return
        step = self._selected_step()
        if not step or step.zoom == value / 10:
            return
        before = step.visual_state()
        step.zoom = value / 10
        step.visual_reviewed = True
        after = step.visual_state()
        self.undo_stack.push(
            VisualStateCommand(self, step.id, before, after, "Cambiar zoom", merge_key="zoom")
        )

    def _reviewed_changed(self, checked: bool) -> None:
        if self._loading:
            return
        step = self._selected_step()
        if not step or step.visual_reviewed == checked:
            return
        before = step.visual_state()
        step.visual_reviewed = checked
        after = step.visual_state()
        self.undo_stack.push(
            VisualStateCommand(self, step.id, before, after, "Cambiar estado de revisión")
        )

    def _visual_edit_committed(
        self, before: dict[str, object], after: dict[str, object], description: str
    ) -> None:
        step = self._selected_step()
        if not step:
            return
        self.undo_stack.push(VisualStateCommand(self, step.id, before, after, description))

    def _apply_visual_state(self, step_id: str, state: dict[str, object]) -> None:
        step = next((item for item in self.project.steps if item.id == step_id), None)
        if not step:
            return
        step.apply_visual_state(state)
        if self._selected_step() is step:
            self._loading = True
            self.zoom_slider.setValue(round(step.zoom * 10))
            self.zoom_value.setText(f"{step.zoom:.1f}×")
            self.reviewed_check.setChecked(step.visual_reviewed)
            self.edit_canvas.set_step(step)
            self.edit_canvas.set_accent_color(self.project.accent_color)
            self._update_preview(step)
            self._update_visual_summary(step)
            self._loading = False
        self._set_dirty(True)

    def _update_preview(self, step: TutorialStep) -> None:
        try:
            preview = render_step_image(
                step.image_png,
                step.focus_x,
                step.focus_y,
                step.zoom,
                crop=step.crop,
                annotations=step.annotations,
                accent_color=self.project.accent_color,
                max_width=1200,
            )
            self.preview_canvas.set_image(preview)
        except InvalidImageError:
            self.preview_canvas.clear_image()

    def _update_visual_summary(self, step: TutorialStep) -> None:
        names = {
            "marker": "marcadores",
            "arrow": "flechas",
            "rectangle": "rectángulos",
            "redaction_solid": "bloques seguros",
            "redaction_blur": "desenfoques",
        }
        counts = {key: sum(a.type == key for a in step.annotations) for key in names}
        parts = [f"{value} {names[key]}" for key, value in counts.items() if value]
        if step.crop:
            parts.append("recorte activo")
        self.visual_summary.setText(", ".join(parts) if parts else "Sin anotaciones ni recorte")

    def _set_visual_mode(self, mode: str) -> None:
        self.edit_canvas.set_mode(mode)
        self.image_tabs.setCurrentWidget(self.edit_canvas)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.project.accent_color), self, "Color principal")
        if not color.isValid():
            return
        self.project.accent_color = normalize_color(color.name())
        self._update_brand_controls()
        self.edit_canvas.set_accent_color(self.project.accent_color)
        step = self._selected_step()
        if step:
            self._update_preview(step)
        self._set_dirty(True)

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir logo", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        try:
            self.project.logo_png = normalize_to_png(path)
        except InvalidImageError as exc:
            QMessageBox.warning(self, "Logo no válido", str(exc))
            return
        self._update_brand_controls()
        self._set_dirty(True)

    def _remove_logo(self) -> None:
        if not self.project.logo_png:
            return
        self.project.logo_png = None
        self._update_brand_controls()
        self._set_dirty(True)

    def _update_brand_controls(self) -> None:
        color = normalize_color(self.project.accent_color)
        self.color_button.setStyleSheet(
            f"background:{color};color:white;border:1px solid #344054;border-radius:5px;padding:6px 12px"
        )
        if self.project.logo_png:
            pixmap = QPixmap()
            pixmap.loadFromData(self.project.logo_png)
            self.logo_preview.setPixmap(
                pixmap.scaled(
                    self.logo_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.logo_preview.setText("")
        else:
            self.logo_preview.setPixmap(QPixmap())
            self.logo_preview.setText("Sin logo")
        self.remove_logo_button.setEnabled(bool(self.project.logo_png))

    def _add_image_step(self, image_png: bytes, title: str = "") -> None:
        number = len(self.project.steps) + 1
        step = TutorialStep(
            title=title.strip() or f"Paso {number}", instruction=RichText(), image_png=image_png
        )
        self.project.steps.append(step)
        self._show_project(len(self.project.steps) - 1)
        self._set_dirty(True)

    def _import_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importar capturas",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp);;Todos los archivos (*)",
        )
        if not paths:
            return
        failed: list[str] = []
        for path in paths:
            try:
                self._add_image_step(normalize_to_png(path), Path(path).stem)
            except InvalidImageError:
                failed.append(Path(path).name)
        if failed:
            QMessageBox.warning(self, "Imágenes no válidas", "No fue posible importar: " + ", ".join(failed))

    def _replace_image(self) -> None:
        step = self._selected_step()
        if not step:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Reemplazar captura",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp);;Todos los archivos (*)",
        )
        if not path:
            return
        try:
            step.image_png = normalize_to_png(path)
        except InvalidImageError as exc:
            QMessageBox.warning(self, "Imagen no válida", str(exc))
            return
        step.focus_x = step.focus_y = 0.5
        step.zoom = 1.0
        step.crop = None
        step.annotations.clear()
        step.visual_reviewed = False
        self.undo_stack.clear()
        self._load_step(self.step_list.currentRow())
        self._set_dirty(True)

    def _capture_with_delay(self) -> None:
        self.statusBar().showMessage("Cambia a la ventana objetivo: captura en 3 segundos…")
        self.showMinimized()
        QTimer.singleShot(3000, self._capture_from_hotkey)

    def _capture_from_hotkey(self) -> None:
        try:
            captured = capture_foreground_window(excluded_hwnd=int(self.winId()))
        except CaptureError as exc:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.warning(self, "No se pudo capturar", str(exc))
            return
        self._add_image_step(captured.image_png, captured.title)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.statusBar().showMessage("Captura añadida. Revisa privacidad y anotaciones.", 5000)

    def _delete_step(self) -> None:
        row = self.step_list.currentRow()
        if not (0 <= row < len(self.project.steps)):
            return
        del self.project.steps[row]
        self.undo_stack.clear()
        self._show_project(min(row, len(self.project.steps) - 1))
        self._set_dirty(True)

    def _move_step(self, offset: int) -> None:
        row = self.step_list.currentRow()
        target = row + offset
        if not (0 <= row < len(self.project.steps) and 0 <= target < len(self.project.steps)):
            return
        self.project.steps[row], self.project.steps[target] = self.project.steps[target], self.project.steps[row]
        self._show_project(target)
        self._set_dirty(True)

    def _update_enabled_state(self) -> None:
        has_step = self._selected_step() is not None
        row = self.step_list.currentRow()
        for widget in (
            self.step_title,
            self.step_instruction,
            self.zoom_slider,
            self.reviewed_check,
            self.replace_button,
            self.delete_button,
            self.reset_crop_button,
        ):
            widget.setEnabled(has_step)
        for button in self.visual_tool_buttons.values():
            button.setEnabled(has_step)
        self.delete_annotation_button.setEnabled(False)
        self.up_button.setEnabled(has_step and row > 0)
        self.down_button.setEnabled(has_step and row < len(self.project.steps) - 1)
        for action in (self.action_preview, self.action_export, self.action_export_open):
            action.setEnabled(bool(self.project.steps))

    def initialize_startup(self, requested_project: str | Path | None = None) -> None:
        """Resuelve primero una recuperación pendiente y después la apertura solicitada."""

        if self.recovery.has_recovery():
            try:
                info = self.recovery.inspect()
            except InvalidRecoveryError as exc:
                QMessageBox.warning(
                    self,
                    "Recuperación no válida",
                    f"No fue posible usar la copia de recuperación y se descartará.\n\n{exc}",
                )
                self.recovery.clear()
            else:
                try:
                    captured = datetime.fromisoformat(info.metadata.captured_at_utc).astimezone()
                    captured_text = captured.strftime("%d/%m/%Y %I:%M:%S %p")
                except ValueError:
                    captured_text = info.metadata.captured_at_utc
                source = info.metadata.source_path or "Proyecto todavía no guardado"
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Trabajo sin guardar encontrado")
                box.setText("La aplicación no se cerró correctamente y encontró trabajo recuperable.")
                box.setInformativeText(
                    f"Proyecto: {info.project.title or 'Sin título'}\n"
                    f"Fecha: {captured_text}\nOrigen: {source}"
                )
                recover_button = box.addButton("Recuperar", QMessageBox.ButtonRole.AcceptRole)
                discard_button = box.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
                box.setDefaultButton(recover_button)
                box.exec()
                if box.clickedButton() is not discard_button:
                    unchanged = info.source_is_unchanged()
                    self.project = info.project
                    self.project_path = (
                        Path(info.metadata.source_path)
                        if unchanged and info.metadata.source_path
                        else None
                    )
                    self._recovered_force_save_as = not unchanged
                    self.undo_stack.clear()
                    self._show_project()
                    self.recovery.adopt_existing()
                    self._set_dirty(True, manage_recovery=False)
                    message = "Trabajo recuperado. Guarda el proyecto para confirmar los cambios."
                    if self._recovered_force_save_as:
                        message = "Trabajo recuperado. Debes usar Guardar como para proteger el original."
                    self.statusBar().showMessage(message, 9000)
                    return
                self.recovery.clear()
        if requested_project:
            self.open_project_path(requested_project)

    def _new_project(self) -> None:
        if not self._maybe_save_changes():
            return
        self.project = TutorialProject()
        self.project_path = None
        self._recovered_force_save_as = False
        self.undo_stack.clear()
        self._show_project()
        self._set_dirty(False)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir tutorial", "", "Proyectos de tutorial (*.tutorial)"
        )
        if not path:
            return
        self.open_project_path(path)

    def open_project_path(self, path: str | Path) -> bool:
        """Abre un proyecto desde diálogo, CLI o asociación de archivos."""

        if not self._maybe_save_changes():
            return False
        try:
            project = load_project(path)
        except InvalidProjectError as exc:
            QMessageBox.critical(self, "Proyecto no válido", str(exc))
            return False
        self.project = project
        self.project_path = Path(path)
        self._recovered_force_save_as = False
        self.undo_stack.clear()
        self._show_project()
        self._set_dirty(False)
        return True

    def handle_external_command(self, command: dict[str, object]) -> None:
        """Recibe activación o apertura desde una segunda invocación."""

        self.showNormal()
        self.raise_()
        self.activateWindow()
        if command.get("action") == "open" and command.get("path"):
            self.open_project_path(str(command["path"]))

    def _save_project(self, *, save_as: bool = False) -> bool:
        target = None if self._recovered_force_save_as else self.project_path
        if target is None or save_as:
            suggested = self._safe_name(self.project.title or "tutorial") + ".tutorial"
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar proyecto", suggested, "Proyectos de tutorial (*.tutorial)"
            )
            if not path:
                return False
            target = Path(path)
        try:
            self.project_path = save_project(target, self.project)
        except (OSError, InvalidImageError) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self._recovered_force_save_as = False
        self._set_dirty(False)
        self.statusBar().showMessage(f"Proyecto guardado: {self.project_path}", 5000)
        return True

    def _confirm_export_warnings(self) -> bool:
        warnings = collect_export_warnings(self.project)
        if not warnings:
            return True
        visible = warnings[:10]
        extra = len(warnings) - len(visible)
        text = "Se encontraron estas observaciones:\n\n• " + "\n• ".join(visible)
        if extra:
            text += f"\n• …y {extra} observación(es) más."
        text += "\n\n¿Deseas exportar de todas formas?"
        result = QMessageBox.warning(
            self,
            "Revisión antes de exportar",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Yes

    def _export_html(self, *, open_after: bool) -> None:
        if not self.project.steps or not self._confirm_export_warnings():
            return
        suggested = self._safe_name(self.project.title or "tutorial") + ".html"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar HTML", suggested, "Documento HTML (*.html)"
        )
        if not path:
            return
        try:
            exported = export_html(path, self.project)
        except (OSError, InvalidImageError) as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
            return
        if open_after:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(exported.resolve()))):
                QMessageBox.warning(self, "No se pudo abrir", f"El archivo se exportó en:\n{exported}")
        else:
            QMessageBox.information(
                self, "Tutorial exportado", f"El HTML autosuficiente quedó guardado en:\n{exported}"
            )

    def _preview_full_guide(self) -> None:
        if not self.project.steps:
            return
        self._clear_preview_file()
        handle = tempfile.NamedTemporaryFile(prefix="tutorial-preview-", suffix=".html", delete=False)
        self.preview_path = Path(handle.name)
        handle.close()
        try:
            export_html(self.preview_path, self.project)
        except (OSError, InvalidImageError) as exc:
            QMessageBox.critical(self, "No se pudo generar la vista previa", str(exc))
            self._clear_preview_file()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.preview_path.resolve()))):
            QMessageBox.warning(
                self, "No se pudo abrir", f"La vista previa quedó en:\n{self.preview_path}"
            )

    def _clear_preview_file(self) -> None:
        if self.preview_path:
            self.preview_path.unlink(missing_ok=True)
            self.preview_path = None

    @staticmethod
    def _safe_name(value: str) -> str:
        value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
        return re.sub(r"\s+", "-", value).lower() or "tutorial"

    def _maybe_save_changes(self) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "¿Deseas guardar los cambios antes de continuar?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if result == QMessageBox.StandardButton.Save:
            return self._save_project()
        if result == QMessageBox.StandardButton.Discard:
            if hasattr(self, "recovery"):
                self.recovery.clear()
            self._recovered_force_save_as = False
            return True
        return False

    def _set_dirty(self, dirty: bool, *, manage_recovery: bool = True) -> None:
        self.dirty = dirty
        if manage_recovery and hasattr(self, "recovery"):
            if dirty:
                self.recovery.mark_dirty()
            else:
                self.recovery.clear()
        self._update_window_title()

    def _recovery_snapshot(self) -> tuple[TutorialProject, Path | None]:
        return self.project, self.project_path

    def _recovery_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"No se pudo actualizar la recuperación: {message}", 10000)
        if not self._recovery_warning_shown:
            self._recovery_warning_shown = True
            QMessageBox.warning(
                self,
                "Recuperación no disponible",
                "No fue posible actualizar la copia de recuperación. "
                "El proyecto sigue abierto; guárdalo manualmente.\n\n"
                f"Detalle: {message}",
            )

    def _update_window_title(self) -> None:
        name = self.project_path.name if self.project_path else (self.project.title or "Sin título")
        marker = " *" if self.dirty else ""
        self.setWindowTitle(f"Tutoriales visuales v.{__version__} — {name}{marker}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._maybe_save_changes():
            self._pending_update = None
            event.ignore()
            return
        pending = getattr(self, "_pending_update", None)
        if pending:
            try:
                from .updater import launch_update
                launch_update(pending[0], pending[1], self.project_path)
            except Exception as exc:
                self._pending_update = None
                QMessageBox.warning(self, "No se pudo actualizar", str(exc))
                event.ignore()
                return
            self._pending_update = None
        self._clear_preview_file()
        self.hotkey.close()
        self.recovery.shutdown()
        event.accept()
