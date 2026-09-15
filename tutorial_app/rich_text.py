from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import RichText, TextMark, normalize_link_url


def _qt_position(text: str, python_index: int) -> int:
    """Convierte una posición Unicode de Python a posición UTF-16 de QTextCursor."""

    return len(text[:python_index].encode("utf-16-le")) // 2


class SafeRichTextEdit(QTextEdit):
    """QTextEdit limitado a negrita y enlaces; el pegado siempre entra como texto plano."""

    def insertFromMimeData(self, source) -> None:  # noqa: N802
        self.textCursor().insertText(source.text())

    def set_structured_text(self, value: RichText) -> None:
        value.normalize()
        previous = self.blockSignals(True)
        try:
            self.document().setPlainText(value.text)
            self.setCurrentCharFormat(QTextCharFormat())
            for mark in value.marks:
                cursor = QTextCursor(self.document())
                cursor.setPosition(_qt_position(value.text, mark.start))
                cursor.setPosition(
                    _qt_position(value.text, mark.end), QTextCursor.MoveMode.KeepAnchor
                )
                fmt = QTextCharFormat()
                if mark.type == "bold":
                    fmt.setFontWeight(QFont.Weight.Bold)
                elif mark.type == "link" and mark.url:
                    fmt.setAnchor(True)
                    fmt.setAnchorHref(mark.url)
                    fmt.setFontUnderline(True)
                    fmt.setForeground(QColor("#1769aa"))
                cursor.mergeCharFormat(fmt)
            self.document().clearUndoRedoStacks()
        finally:
            self.blockSignals(previous)

    def structured_text(self) -> RichText:
        text_parts: list[str] = []
        marks: list[TextMark] = []
        offset = 0
        block = self.document().begin()
        first_block = True
        while block.isValid():
            if not first_block:
                text_parts.append("\n")
                offset += 1
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    segment = fragment.text()
                    start, end = offset, offset + len(segment)
                    fmt = fragment.charFormat()
                    if fmt.fontWeight() >= QFont.Weight.Bold.value:
                        marks.append(TextMark("bold", start, end))
                    if fmt.isAnchor() and fmt.anchorHref():
                        marks.append(TextMark("link", start, end, fmt.anchorHref()))
                    text_parts.append(segment)
                    offset = end
                iterator += 1
            first_block = False
            block = block.next()
        result = RichText("".join(text_parts), marks)
        result.normalize()
        return result


class LinkDialog(QDialog):
    def __init__(self, text: str = "", url: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insertar o editar enlace")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.text_input = QLineEdit(text)
        self.text_input.setPlaceholderText("Texto visible")
        self.url_input = QLineEdit(url)
        self.url_input.setPlaceholderText("https://sitio.example o correo@example.com")
        form.addRow("Texto:", self.text_input)
        form.addRow("Dirección:", self.url_input)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.normalized_url = ""

    def _validate(self) -> None:
        if not self.text_input.text():
            QMessageBox.warning(self, "Falta texto", "Escribe el texto visible del enlace.")
            return
        try:
            self.normalized_url = normalize_link_url(self.url_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Enlace no válido", str(exc))
            return
        self.accept()


class RichTextEditor(QWidget):
    contentChanged = Signal()

    def __init__(self, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        self.bold_button = QPushButton("Negrita")
        self.bold_button.setToolTip("Aplicar o quitar negrita (Ctrl+B)")
        self.link_button = QPushButton("Enlace…")
        self.link_button.setToolTip("Insertar o editar un enlace")
        self.unlink_button = QPushButton("Quitar enlace")
        tools.addWidget(self.bold_button)
        tools.addWidget(self.link_button)
        tools.addWidget(self.unlink_button)
        tools.addStretch(1)
        layout.addLayout(tools)
        self.editor = SafeRichTextEdit()
        self.editor.setPlaceholderText(placeholder)
        layout.addWidget(self.editor)
        self.bold_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.bold_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.bold_shortcut.activated.connect(self.toggle_bold)
        self.bold_button.clicked.connect(self.toggle_bold)
        self.link_button.clicked.connect(self.edit_link)
        self.unlink_button.clicked.connect(self.remove_link)
        self.editor.textChanged.connect(self.contentChanged)

    def set_structured_text(self, value: RichText) -> None:
        self.editor.set_structured_text(value)

    def structured_text(self) -> RichText:
        return self.editor.structured_text()

    def clear(self) -> None:
        self.set_structured_text(RichText())

    def _selection_or_word(self) -> QTextCursor:
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor

    def toggle_bold(self) -> None:
        cursor = self._selection_or_word()
        if not cursor.hasSelection():
            return
        current = cursor.charFormat().fontWeight() >= QFont.Weight.Bold.value
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if current else QFont.Weight.Bold)
        cursor.mergeCharFormat(fmt)
        self.editor.setTextCursor(cursor)

    def edit_link(self) -> None:
        cursor = self._selection_or_word()
        selected = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() else ""
        current_url = cursor.charFormat().anchorHref() if cursor.hasSelection() else ""
        dialog = LinkDialog(selected, current_url, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(dialog.normalized_url)
        fmt.setFontUnderline(True)
        fmt.setForeground(QColor("#1769aa"))
        cursor.insertText(dialog.text_input.text(), fmt)
        self.editor.setTextCursor(cursor)

    def remove_link(self) -> None:
        cursor = self._selection_or_word()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(False)
        fmt.setAnchorHref("")
        fmt.setFontUnderline(False)
        fmt.clearProperty(QTextFormat.Property.ForegroundBrush)
        cursor.mergeCharFormat(fmt)
        self.editor.setTextCursor(cursor)
