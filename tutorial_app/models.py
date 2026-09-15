from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4


ANNOTATION_TYPES = {
    "marker",
    "arrow",
    "rectangle",
    "redaction_solid",
    "redaction_blur",
}
RECTANGLE_TYPES = {"rectangle", "redaction_solid", "redaction_blur"}
DEFAULT_ACCENT_COLOR = "#ff7a00"
TEXT_MARK_TYPES = {"bold", "link"}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def normalize_color(value: str) -> str:
    value = str(value).strip().lower()
    return value if re.fullmatch(r"#[0-9a-f]{6}", value) else DEFAULT_ACCENT_COLOR


def normalize_link_url(value: str) -> str:
    """Normaliza enlaces creados por la UI y rechaza protocolos peligrosos."""

    value = str(value).strip()
    if not value:
        raise ValueError("La dirección del enlace está vacía.")
    if ":" not in value.split("/", 1)[0]:
        if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            value = f"mailto:{value}"
        else:
            value = f"https://{value}"
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https", "mailto"}:
        raise ValueError("Solo se permiten enlaces web (http/https) o de correo (mailto).")
    if scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError("El enlace web no contiene un dominio válido.")
    if scheme == "mailto" and not parsed.path:
        raise ValueError("El enlace de correo no contiene una dirección válida.")
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


@dataclass(slots=True)
class TextMark:
    type: str
    start: int
    end: int
    url: str | None = None

    def normalize(self, text_length: int) -> None:
        if self.type not in TEXT_MARK_TYPES:
            raise ValueError(f"Tipo de formato no compatible: {self.type}")
        self.start = max(0, min(text_length, int(self.start)))
        self.end = max(0, min(text_length, int(self.end)))
        if self.start > self.end:
            self.start, self.end = self.end, self.start
        if self.type == "link":
            self.url = normalize_link_url(self.url or "")
        else:
            self.url = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "type": self.type,
            "start": self.start,
            "end": self.end,
        }
        if self.type == "link":
            result["url"] = self.url
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "TextMark":
        return cls(
            type=str(raw.get("type", "")),
            start=int(raw.get("start", 0)),
            end=int(raw.get("end", 0)),
            url=str(raw.get("url", "")) if raw.get("url") is not None else None,
        )


@dataclass(slots=True)
class RichText:
    text: str = ""
    marks: list[TextMark] = field(default_factory=list)

    def normalize(self) -> None:
        self.text = str(self.text).replace("\r\n", "\n").replace("\r", "\n")
        normalized: list[TextMark] = []
        for mark in self.marks:
            mark.normalize(len(self.text))
            if mark.start < mark.end:
                normalized.append(mark)
        normalized.sort(key=lambda item: (item.type, item.url or "", item.start, item.end))
        merged: list[TextMark] = []
        for mark in normalized:
            if (
                merged
                and merged[-1].type == mark.type
                and merged[-1].url == mark.url
                and mark.start <= merged[-1].end
            ):
                merged[-1].end = max(merged[-1].end, mark.end)
            else:
                merged.append(mark)
        links = sorted((mark for mark in merged if mark.type == "link"), key=lambda item: item.start)
        if any(current.start < previous.end for previous, current in zip(links, links[1:])):
            raise ValueError("Los enlaces de un texto no pueden superponerse.")
        self.marks = merged

    def as_dict(self) -> dict[str, object]:
        self.normalize()
        return {"text": self.text, "marks": [mark.as_dict() for mark in self.marks]}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "RichText":
        raw_marks = raw.get("marks", [])
        if not isinstance(raw_marks, list):
            raise ValueError("La lista de formatos de texto es inválida.")
        if any(not isinstance(item, dict) for item in raw_marks):
            raise ValueError("Una marca de texto es inválida.")
        value = cls(
            text=str(raw.get("text", "")),
            marks=[TextMark.from_dict(item) for item in raw_marks],
        )
        value.normalize()
        return value


def ensure_rich_text(value: RichText | str) -> RichText:
    if isinstance(value, RichText):
        value.normalize()
        return value
    result = RichText(str(value))
    result.normalize()
    return result


@dataclass(slots=True)
class NormalizedRect:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0

    def normalize(self) -> None:
        left, right = sorted((_clamp(self.x), _clamp(self.x + self.width)))
        top, bottom = sorted((_clamp(self.y), _clamp(self.y + self.height)))
        if right - left < 0.001:
            left = min(left, 0.999)
            right = left + 0.001
        if bottom - top < 0.001:
            top = min(top, 0.999)
            bottom = top + 0.001
        self.x, self.y = left, top
        self.width, self.height = right - left, bottom - top

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "NormalizedRect":
        rect = cls(
            x=float(raw.get("x", 0.0)),
            y=float(raw.get("y", 0.0)),
            width=float(raw.get("width", 1.0)),
            height=float(raw.get("height", 1.0)),
        )
        rect.normalize()
        return rect


@dataclass(slots=True)
class Annotation:
    type: str
    id: str = field(default_factory=lambda: uuid4().hex)
    x1: float = 0.5
    y1: float = 0.5
    x2: float = 0.5
    y2: float = 0.5

    def normalize(self) -> None:
        if self.type not in ANNOTATION_TYPES:
            raise ValueError(f"Tipo de anotación no compatible: {self.type}")
        self.x1 = _clamp(self.x1)
        self.y1 = _clamp(self.y1)
        self.x2 = _clamp(self.x2)
        self.y2 = _clamp(self.y2)
        if self.type == "marker":
            self.x2 = self.x1
            self.y2 = self.y1
        elif self.type in RECTANGLE_TYPES:
            left, right = sorted((self.x1, self.x2))
            top, bottom = sorted((self.y1, self.y2))
            self.x1, self.y1, self.x2, self.y2 = left, top, right, bottom

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "geometry": {
                "x1": self.x1,
                "y1": self.y1,
                "x2": self.x2,
                "y2": self.y2,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Annotation":
        geometry = raw.get("geometry", {})
        if not isinstance(geometry, dict):
            raise ValueError("La geometría de la anotación es inválida.")
        annotation = cls(
            id=str(raw.get("id") or uuid4().hex),
            type=str(raw.get("type", "")),
            x1=float(geometry.get("x1", 0.5)),
            y1=float(geometry.get("y1", 0.5)),
            x2=float(geometry.get("x2", 0.5)),
            y2=float(geometry.get("y2", 0.5)),
        )
        annotation.normalize()
        return annotation


@dataclass(slots=True)
class TutorialStep:
    """Un paso editable; image_png siempre conserva la captura original."""

    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    instruction: RichText | str = field(default_factory=RichText)
    image_png: bytes = b""
    focus_x: float = 0.5
    focus_y: float = 0.5
    zoom: float = 1.0
    crop: NormalizedRect | None = None
    annotations: list[Annotation] = field(default_factory=list)
    visual_reviewed: bool = False

    def normalize(self) -> None:
        self.instruction = ensure_rich_text(self.instruction)
        self.focus_x = _clamp(self.focus_x)
        self.focus_y = _clamp(self.focus_y)
        self.zoom = max(1.0, min(3.0, float(self.zoom)))
        if self.crop is not None:
            self.crop.normalize()
        valid_annotations: list[Annotation] = []
        for annotation in self.annotations:
            annotation.normalize()
            valid_annotations.append(annotation)
        self.annotations = valid_annotations

    def visual_state(self) -> dict[str, object]:
        return {
            "focus_x": self.focus_x,
            "focus_y": self.focus_y,
            "zoom": self.zoom,
            "crop": copy.deepcopy(self.crop),
            "annotations": copy.deepcopy(self.annotations),
            "visual_reviewed": self.visual_reviewed,
        }

    def apply_visual_state(self, state: dict[str, object]) -> None:
        self.focus_x = float(state["focus_x"])
        self.focus_y = float(state["focus_y"])
        self.zoom = float(state["zoom"])
        self.crop = copy.deepcopy(state.get("crop"))
        self.annotations = copy.deepcopy(state.get("annotations", []))
        self.visual_reviewed = bool(state.get("visual_reviewed", False))
        self.normalize()


@dataclass(slots=True)
class TutorialProject:
    schema_version: int = 3
    title: str = "Mi tutorial"
    description: RichText | str = field(default_factory=RichText)
    brand_name: str = ""
    accent_color: str = DEFAULT_ACCENT_COLOR
    logo_png: bytes | None = None
    steps: list[TutorialStep] = field(default_factory=list)

    def normalize(self) -> None:
        self.schema_version = 3
        self.description = ensure_rich_text(self.description)
        self.accent_color = normalize_color(self.accent_color)
        for step in self.steps:
            step.normalize()
