import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from tutorial_app.models import RichText, TextMark, normalize_link_url
from tutorial_app.rich_text import RichTextEditor, SafeRichTextEdit


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_structured_editor_round_trip_preserves_unicode_and_overlapping_marks() -> None:
    app()
    value = RichText(
        "Haz clic aquí 😊",
        [
            TextMark("bold", 0, 13),
            TextMark("link", 4, 13, "https://example.com/guía"),
        ],
    )
    editor = SafeRichTextEdit()

    editor.set_structured_text(value)
    restored = editor.structured_text()

    assert restored.text == value.text
    assert restored.marks == value.marks


def test_paste_discards_external_html_styles() -> None:
    app()
    editor = SafeRichTextEdit()
    mime = QMimeData()
    mime.setText("Texto pegado")
    mime.setHtml('<b>Texto</b><a href="javascript:alert(1)"> pegado</a>')

    editor.insertFromMimeData(mime)

    assert editor.structured_text() == RichText("Texto pegado")


@pytest.mark.parametrize("value", ["javascript:alert(1)", "file:///C:/secreto", "data:text/html,x"])
def test_link_validation_rejects_unsafe_protocols(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_link_url(value)


def test_link_validation_normalizes_web_and_email_addresses() -> None:
    assert normalize_link_url("example.com/ayuda") == "https://example.com/ayuda"
    assert normalize_link_url("soporte@example.com") == "mailto:soporte@example.com"


def test_visual_controls_toggle_bold_and_remove_links() -> None:
    app()
    field = RichTextEditor("Texto")
    field.set_structured_text(RichText("Texto de prueba"))
    cursor = field.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    field.editor.setTextCursor(cursor)

    field.toggle_bold()
    assert field.structured_text().marks == [TextMark("bold", 0, 5)]

    field.set_structured_text(
        RichText("Enlace seguro", [TextMark("link", 0, 6, "https://example.com")])
    )
    cursor = field.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
    field.editor.setTextCursor(cursor)
    field.remove_link()
    assert field.structured_text().marks == []


def test_overlapping_links_are_rejected() -> None:
    value = RichText(
        "texto largo",
        [
            TextMark("link", 0, 6, "https://one.example"),
            TextMark("link", 4, 10, "https://two.example"),
        ],
    )
    with pytest.raises(ValueError):
        value.normalize()
