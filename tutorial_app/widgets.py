from __future__ import annotations

import copy
import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from .models import Annotation, NormalizedRect, RECTANGLE_TYPES, TutorialStep, normalize_color


DRAW_MODES = {
    "arrow": "arrow",
    "rectangle": "rectangle",
    "redaction_solid": "redaction_solid",
    "redaction_blur": "redaction_blur",
}


class PreviewCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setMinimumSize(420, 300)

    def set_image(self, image_bytes: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        self._pixmap = pixmap
        self.update()

    def clear_image(self) -> None:
        self._pixmap = QPixmap()
        self.update()

    def _image_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF()
        available = self.rect().adjusted(14, 14, -14, -14)
        scaled = self._pixmap.size().scaled(
            available.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = available.x() + (available.width() - scaled.width()) / 2
        y = available.y() + (available.height() - scaled.height()) / 2
        return QRectF(x, y, scaled.width(), scaled.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202633"))
        if self._pixmap.isNull():
            painter.setPen(QColor("#aeb7c5"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Selecciona o captura una imagen")
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(self._image_rect(), self._pixmap, QRectF(self._pixmap.rect()))


class VisualEditorCanvas(PreviewCanvas):
    visualEditCommitted = Signal(object, object, str)
    selectionChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.step: TutorialStep | None = None
        self.mode = "select"
        self.accent_color = "#ff7a00"
        self.selected_id: str | None = None
        self._dragging = False
        self._drag_start = QPointF()
        self._drag_before: dict[str, object] | None = None
        self._drag_original: Annotation | None = None
        self._drag_handle = "move"
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_step(self, step: TutorialStep | None) -> None:
        self.step = step
        self.selected_id = None
        self._dragging = False
        if step is None:
            self.clear_image()
        else:
            self.set_image(step.image_png)
        self.selectionChanged.emit(False)
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        cursors = {
            "select": Qt.CursorShape.ArrowCursor,
            "crop": Qt.CursorShape.CrossCursor,
            "focus": Qt.CursorShape.CrossCursor,
        }
        self.setCursor(cursors.get(mode, Qt.CursorShape.CrossCursor))
        self.update()

    def set_accent_color(self, color: str) -> None:
        self.accent_color = normalize_color(color)
        self.update()

    def _accent(self) -> QColor:
        return QColor(self.accent_color)

    def _norm_to_widget(self, x: float, y: float) -> QPointF:
        target = self._image_rect()
        return QPointF(target.left() + x * target.width(), target.top() + y * target.height())

    def _widget_to_norm(self, point: QPointF) -> QPointF | None:
        target = self._image_rect()
        if target.isEmpty() or not target.contains(point):
            return None
        return QPointF(
            max(0.0, min(1.0, (point.x() - target.left()) / target.width())),
            max(0.0, min(1.0, (point.y() - target.top()) / target.height())),
        )

    def _selected_annotation(self) -> Annotation | None:
        if not self.step or not self.selected_id:
            return None
        return next((a for a in self.step.annotations if a.id == self.selected_id), None)

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF, pen: QPen) -> None:
        painter.setPen(pen)
        painter.drawLine(start, end)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head = 16.0
        spread = math.pi / 6
        p1 = QPointF(end.x() - head * math.cos(angle - spread), end.y() - head * math.sin(angle - spread))
        p2 = QPointF(end.x() - head * math.cos(angle + spread), end.y() - head * math.sin(angle + spread))
        painter.setBrush(pen.color())
        painter.drawPolygon(QPolygonF([end, p1, p2]))

    def _paint_crop(self, painter: QPainter) -> None:
        if not self.step or self.step.crop is None:
            return
        target = self._image_rect()
        crop = self.step.crop
        crop_rect = QRectF(
            target.left() + crop.x * target.width(),
            target.top() + crop.y * target.height(),
            crop.width * target.width(),
            crop.height * target.height(),
        )
        painter.fillRect(QRectF(target.left(), target.top(), target.width(), crop_rect.top() - target.top()), QColor(0, 0, 0, 110))
        painter.fillRect(QRectF(target.left(), crop_rect.bottom(), target.width(), target.bottom() - crop_rect.bottom()), QColor(0, 0, 0, 110))
        painter.fillRect(QRectF(target.left(), crop_rect.top(), crop_rect.left() - target.left(), crop_rect.height()), QColor(0, 0, 0, 110))
        painter.fillRect(QRectF(crop_rect.right(), crop_rect.top(), target.right() - crop_rect.right(), crop_rect.height()), QColor(0, 0, 0, 110))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("white"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(crop_rect)

    def _paint_annotation(self, painter: QPainter, annotation: Annotation) -> None:
        start = self._norm_to_widget(annotation.x1, annotation.y1)
        end = self._norm_to_widget(annotation.x2, annotation.y2)
        accent = self._accent()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if annotation.type == "marker":
            painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 60))
            painter.setPen(QPen(accent, 4))
            painter.drawEllipse(start, 16, 16)
            painter.setBrush(QColor("white"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(start, 4, 4)
        elif annotation.type == "arrow":
            self._draw_arrow(painter, start, end, QPen(accent, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        else:
            rect = QRectF(start, end).normalized()
            if annotation.type == "rectangle":
                painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 38))
                painter.setPen(QPen(accent, 4))
            elif annotation.type == "redaction_solid":
                painter.setBrush(QColor("#1f2937"))
                painter.setPen(QPen(QColor("#111827"), 2))
            else:
                painter.setBrush(QColor(148, 163, 184, 185))
                painter.setPen(QPen(QColor("#475569"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
            if annotation.type == "redaction_blur" and rect.width() > 70 and rect.height() > 28:
                painter.setPen(QColor("white"))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DESENFOQUE")

    def _paint_selection(self, painter: QPainter) -> None:
        annotation = self._selected_annotation()
        if annotation is None:
            return
        start = self._norm_to_widget(annotation.x1, annotation.y1)
        end = self._norm_to_widget(annotation.x2, annotation.y2)
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#2563eb"), 2))
        handles = [start] if annotation.type == "marker" else [start, end]
        for point in handles:
            painter.drawRect(QRectF(point.x() - 5, point.y() - 5, 10, 10))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self.step or self._pixmap.isNull():
            return
        painter = QPainter(self)
        self._paint_crop(painter)
        for annotation in self.step.annotations:
            self._paint_annotation(painter, annotation)
        focus = self._norm_to_widget(self.step.focus_x, self.step.focus_y)
        painter.setPen(QPen(QColor("#22d3ee"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(focus.x() - 12, focus.y()), QPointF(focus.x() + 12, focus.y()))
        painter.drawLine(QPointF(focus.x(), focus.y() - 12), QPointF(focus.x(), focus.y() + 12))
        self._paint_selection(painter)

    def _distance_to_segment(self, point: QPointF, start: QPointF, end: QPointF) -> float:
        line = QLineF(start, end)
        if line.length() == 0:
            return QLineF(point, start).length()
        dx, dy = end.x() - start.x(), end.y() - start.y()
        t = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        projected = QPointF(start.x() + t * dx, start.y() + t * dy)
        return QLineF(point, projected).length()

    def _hit_annotation(self, point: QPointF) -> Annotation | None:
        if not self.step:
            return None
        widget_point = self._norm_to_widget(point.x(), point.y())
        for annotation in reversed(self.step.annotations):
            start = self._norm_to_widget(annotation.x1, annotation.y1)
            end = self._norm_to_widget(annotation.x2, annotation.y2)
            if annotation.type == "marker" and QLineF(widget_point, start).length() <= 22:
                return annotation
            if annotation.type == "arrow" and self._distance_to_segment(widget_point, start, end) <= 12:
                return annotation
            if annotation.type in RECTANGLE_TYPES and QRectF(start, end).normalized().adjusted(-7, -7, 7, 7).contains(widget_point):
                return annotation
        return None

    def _handle_for(self, annotation: Annotation, point: QPointF) -> str:
        widget_point = self._norm_to_widget(point.x(), point.y())
        start = self._norm_to_widget(annotation.x1, annotation.y1)
        end = self._norm_to_widget(annotation.x2, annotation.y2)
        if QLineF(widget_point, start).length() <= 12:
            return "start"
        if annotation.type != "marker" and QLineF(widget_point, end).length() <= 12:
            return "end"
        return "move"

    def _commit(self, before: dict[str, object], description: str) -> None:
        if not self.step:
            return
        self.step.normalize()
        after = self.step.visual_state()
        if before != after:
            self.visualEditCommitted.emit(before, after, description)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.step or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        point = self._widget_to_norm(event.position())
        if point is None:
            return
        self.setFocus()
        before = self.step.visual_state()
        if self.mode == "select":
            annotation = self._hit_annotation(point)
            self.selected_id = annotation.id if annotation else None
            self.selectionChanged.emit(annotation is not None)
            if annotation:
                self._dragging = True
                self._drag_start = point
                self._drag_before = before
                self._drag_original = copy.deepcopy(annotation)
                self._drag_handle = self._handle_for(annotation, point)
            self.update()
            return
        if self.mode == "focus":
            self.step.focus_x, self.step.focus_y = point.x(), point.y()
            self.step.visual_reviewed = True
            self._commit(before, "Cambiar centro de zoom")
            return
        if self.mode == "marker":
            annotation = Annotation("marker", x1=point.x(), y1=point.y())
            self.step.annotations.append(annotation)
            self.step.visual_reviewed = True
            self.selected_id = annotation.id
            self.selectionChanged.emit(True)
            self._commit(before, "Agregar marcador")
            return

        self._dragging = True
        self._drag_start = point
        self._drag_before = before
        self.step.visual_reviewed = True
        if self.mode == "crop":
            self.step.crop = NormalizedRect(point.x(), point.y(), 0.001, 0.001)
        elif self.mode in DRAW_MODES:
            annotation = Annotation(
                DRAW_MODES[self.mode],
                x1=point.x(), y1=point.y(), x2=point.x(), y2=point.y()
            )
            self.step.annotations.append(annotation)
            self.selected_id = annotation.id
            self.selectionChanged.emit(True)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._dragging or not self.step:
            return super().mouseMoveEvent(event)
        point = self._widget_to_norm(event.position())
        if point is None:
            target = self._image_rect()
            point = QPointF(
                max(0.0, min(1.0, (event.position().x() - target.left()) / target.width())),
                max(0.0, min(1.0, (event.position().y() - target.top()) / target.height())),
            )
        if self.mode == "crop":
            self.step.crop = NormalizedRect(
                min(self._drag_start.x(), point.x()),
                min(self._drag_start.y(), point.y()),
                abs(point.x() - self._drag_start.x()),
                abs(point.y() - self._drag_start.y()),
            )
        elif self.mode in DRAW_MODES:
            annotation = self._selected_annotation()
            if annotation:
                annotation.x2, annotation.y2 = point.x(), point.y()
        elif self.mode == "select" and self._drag_original:
            annotation = self._selected_annotation()
            if not annotation:
                return
            original = self._drag_original
            if self._drag_handle == "start":
                annotation.x1, annotation.y1 = point.x(), point.y()
                if annotation.type == "marker":
                    annotation.x2, annotation.y2 = point.x(), point.y()
            elif self._drag_handle == "end":
                annotation.x2, annotation.y2 = point.x(), point.y()
            else:
                requested_x = point.x() - self._drag_start.x()
                requested_y = point.y() - self._drag_start.y()
                dx = max(-min(original.x1, original.x2), min(1 - max(original.x1, original.x2), requested_x))
                dy = max(-min(original.y1, original.y2), min(1 - max(original.y1, original.y2), requested_y))
                annotation.x1, annotation.y1 = original.x1 + dx, original.y1 + dy
                annotation.x2, annotation.y2 = original.x2 + dx, original.y2 + dy
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._dragging or not self.step or self._drag_before is None:
            return super().mouseReleaseEvent(event)
        before = self._drag_before
        description = "Editar anotación"
        if self.mode == "crop":
            description = "Cambiar recorte"
            if self.step.crop and (self.step.crop.width < 0.01 or self.step.crop.height < 0.01):
                self.step.apply_visual_state(before)
        elif self.mode in DRAW_MODES:
            annotation = self._selected_annotation()
            if annotation and annotation.type != "marker":
                if abs(annotation.x2 - annotation.x1) < 0.01 and abs(annotation.y2 - annotation.y1) < 0.01:
                    self.step.apply_visual_state(before)
                    self.selected_id = None
            description = {
                "arrow": "Agregar flecha",
                "rectangle": "Agregar rectángulo",
                "redaction_solid": "Ocultar con bloque sólido",
                "redaction_blur": "Ocultar con desenfoque",
            }.get(self.mode, description)
        self._dragging = False
        self._drag_original = None
        self._drag_before = None
        self._commit(before, description)

    def delete_selected(self) -> None:
        if not self.step or not self.selected_id:
            return
        before = self.step.visual_state()
        self.step.annotations = [a for a in self.step.annotations if a.id != self.selected_id]
        self.selected_id = None
        self.step.visual_reviewed = True
        self.selectionChanged.emit(False)
        self._commit(before, "Eliminar anotación")

    def clear_crop(self) -> None:
        if not self.step or self.step.crop is None:
            return
        before = self.step.visual_state()
        self.step.crop = None
        self.step.visual_reviewed = True
        self._commit(before, "Restablecer recorte")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.delete_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.selected_id = None
            self.selectionChanged.emit(False)
            self.update()
            return
        super().keyPressEvent(event)
