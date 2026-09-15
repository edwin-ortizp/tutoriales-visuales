from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

from .models import Annotation, NormalizedRect, RECTANGLE_TYPES, normalize_color


class InvalidImageError(ValueError):
    pass


def _open_and_normalize(source: str | Path | bytes | Image.Image) -> Image.Image:
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        elif isinstance(source, bytes):
            image = Image.open(BytesIO(source))
        else:
            image = Image.open(source)
        image.load()
    except (OSError, UnidentifiedImageError) as exc:
        raise InvalidImageError("El archivo no contiene una imagen válida.") from exc
    image = ImageOps.exif_transpose(image)
    if image.width < 2 or image.height < 2:
        raise InvalidImageError("La imagen es demasiado pequeña.")
    return image.convert("RGB")


def normalize_to_png(source: str | Path | bytes | Image.Image) -> bytes:
    image = _open_and_normalize(source)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def image_size(image_png: bytes) -> tuple[int, int]:
    return _open_and_normalize(image_png).size


def _rect_pixels(
    annotation: Annotation, width: int, height: int
) -> tuple[int, int, int, int]:
    left = max(0, min(width - 1, round(min(annotation.x1, annotation.x2) * (width - 1))))
    top = max(0, min(height - 1, round(min(annotation.y1, annotation.y2) * (height - 1))))
    right = max(left + 1, min(width, round(max(annotation.x1, annotation.x2) * (width - 1)) + 1))
    bottom = max(top + 1, min(height, round(max(annotation.y1, annotation.y2) * (height - 1)) + 1))
    return left, top, right, bottom


def _apply_redactions(image: Image.Image, annotations: list[Annotation]) -> Image.Image:
    protected = image.copy()
    for annotation in annotations:
        if annotation.type not in {"redaction_solid", "redaction_blur"}:
            continue
        box = _rect_pixels(annotation, protected.width, protected.height)
        if annotation.type == "redaction_solid":
            # Margen mínimo para impedir que el remuestreo WebP mezcle píxeles
            # sensibles de los bordes con el bloque ya oculto.
            padding = max(2, round(max(protected.width, protected.height) * 0.002))
            safe_box = (
                max(0, box[0] - padding),
                max(0, box[1] - padding),
                min(protected.width, box[2] + padding),
                min(protected.height, box[3] + padding),
            )
            ImageDraw.Draw(protected).rectangle(safe_box, fill=(31, 41, 55))
        else:
            region = protected.crop(box)
            radius = max(8.0, min(region.width, region.height) * 0.12)
            # Dos pasadas evitan que texto de alto contraste siga siendo legible.
            region = region.filter(ImageFilter.GaussianBlur(radius=radius))
            region = region.filter(ImageFilter.GaussianBlur(radius=radius))
            protected.paste(region, box[:2])
    return protected


def _crop_bounds(image: Image.Image, crop: NormalizedRect | None) -> tuple[int, int, int, int]:
    if crop is None:
        return 0, 0, image.width, image.height
    crop.normalize()
    left = round(crop.x * (image.width - 1))
    top = round(crop.y * (image.height - 1))
    right = round((crop.x + crop.width) * (image.width - 1)) + 1
    bottom = round((crop.y + crop.height) * (image.height - 1)) + 1
    right = max(left + 1, min(image.width, right))
    bottom = max(top + 1, min(image.height, bottom))
    return left, top, right, bottom


def _view_bounds(
    image: Image.Image,
    crop: NormalizedRect | None,
    focus_x: float,
    focus_y: float,
    zoom: float,
) -> tuple[int, int, int, int]:
    crop_left, crop_top, crop_right, crop_bottom = _crop_bounds(image, crop)
    crop_width = crop_right - crop_left
    crop_height = crop_bottom - crop_top
    zoom = max(1.0, min(3.0, float(zoom)))
    view_width = max(1, round(crop_width / zoom))
    view_height = max(1, round(crop_height / zoom))
    focus_px = max(crop_left, min(crop_right - 1, focus_x * (image.width - 1)))
    focus_py = max(crop_top, min(crop_bottom - 1, focus_y * (image.height - 1)))
    left = round(focus_px - view_width / 2)
    top = round(focus_py - view_height / 2)
    left = max(crop_left, min(crop_right - view_width, left))
    top = max(crop_top, min(crop_bottom - view_height, top))
    return left, top, left + view_width, top + view_height


def view_box_normalized(
    image_png: bytes,
    crop: NormalizedRect | None,
    focus_x: float,
    focus_y: float,
    zoom: float,
) -> tuple[float, float, float, float]:
    image = _open_and_normalize(image_png)
    left, top, right, bottom = _view_bounds(image, crop, focus_x, focus_y, zoom)
    return (
        left / image.width,
        top / image.height,
        right / image.width,
        bottom / image.height,
    )


def annotation_is_visible(
    annotation: Annotation, view_box: tuple[float, float, float, float]
) -> bool:
    left, top, right, bottom = view_box
    if annotation.type == "marker":
        return left <= annotation.x1 <= right and top <= annotation.y1 <= bottom
    ann_left = min(annotation.x1, annotation.x2)
    ann_top = min(annotation.y1, annotation.y2)
    ann_right = max(annotation.x1, annotation.x2)
    ann_bottom = max(annotation.y1, annotation.y2)
    return not (
        ann_right < left or ann_left > right or ann_bottom < top or ann_top > bottom
    )


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = normalize_color(value)
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _transform_point(
    x: float,
    y: float,
    image_width: int,
    image_height: int,
    view: tuple[int, int, int, int],
    output_size: tuple[int, int],
) -> tuple[float, float]:
    left, top, right, bottom = view
    output_width, output_height = output_size
    px = x * (image_width - 1)
    py = y * (image_height - 1)
    return (
        (px - left) * output_width / (right - left),
        (py - top) * output_height / (bottom - top),
    )


def _draw_marker(draw: ImageDraw.ImageDraw, x: float, y: float, width: int, accent) -> None:
    radius = max(12, min(26, round(width / 55)))
    shadow = radius + 4
    draw.ellipse((x - shadow, y - shadow, x + shadow, y + shadow), fill=(0, 0, 0, 60))
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(*accent, 72),
        outline=(*accent, 255),
        width=max(4, radius // 4),
    )
    inner = max(3, radius // 5)
    draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=(255, 255, 255, 245))


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    width: int,
    accent,
) -> None:
    thickness = max(5, min(12, round(width / 140)))
    draw.line((start, end), fill=(0, 0, 0, 70), width=thickness + 5)
    draw.line((start, end), fill=(*accent, 255), width=thickness)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = max(18, thickness * 3)
    spread = math.pi / 6
    p1 = (end[0] - head * math.cos(angle - spread), end[1] - head * math.sin(angle - spread))
    p2 = (end[0] - head * math.cos(angle + spread), end[1] - head * math.sin(angle + spread))
    draw.polygon((end, p1, p2), fill=(*accent, 255))


def _draw_annotations(
    rendered: Image.Image,
    annotations: list[Annotation],
    image_size: tuple[int, int],
    view: tuple[int, int, int, int],
    accent_color: str,
) -> None:
    draw = ImageDraw.Draw(rendered, "RGBA")
    accent = _hex_rgb(accent_color)
    image_width, image_height = image_size
    output_size = rendered.size
    for annotation in annotations:
        if annotation.type in {"redaction_solid", "redaction_blur"}:
            continue
        start = _transform_point(
            annotation.x1, annotation.y1, image_width, image_height, view, output_size
        )
        end = _transform_point(
            annotation.x2, annotation.y2, image_width, image_height, view, output_size
        )
        if annotation.type == "marker":
            _draw_marker(draw, start[0], start[1], rendered.width, accent)
        elif annotation.type == "arrow":
            _draw_arrow(draw, start, end, rendered.width, accent)
        elif annotation.type == "rectangle":
            left, right = sorted((start[0], end[0]))
            top, bottom = sorted((start[1], end[1]))
            thickness = max(4, min(10, round(rendered.width / 180)))
            draw.rectangle(
                (left, top, right, bottom),
                fill=(*accent, 35),
                outline=(*accent, 255),
                width=thickness,
            )


def render_step_image(
    image_png: bytes,
    focus_x: float,
    focus_y: float,
    zoom: float,
    *,
    crop: NormalizedRect | None = None,
    annotations: list[Annotation] | None = None,
    accent_color: str = "#ff7a00",
    max_width: int = 1600,
) -> bytes:
    """Renderiza sin alterar el PNG original: privacidad, recorte, zoom y anotaciones."""

    image = _open_and_normalize(image_png)
    # None conserva la compatibilidad de la API 0.1; [] significa sin anotaciones.
    if annotations is None:
        annotations = [Annotation("marker", x1=focus_x, y1=focus_y)]
    annotations = list(annotations)
    protected = _apply_redactions(image, annotations)
    view = _view_bounds(protected, crop, focus_x, focus_y, zoom)
    viewed = protected.crop(view)
    crop_box = _crop_bounds(protected, crop)
    target_width = min(max_width, max(1, crop_box[2] - crop_box[0]))
    target_height = max(
        1,
        round(target_width * (crop_box[3] - crop_box[1]) / (crop_box[2] - crop_box[0])),
    )
    rendered = viewed.resize((target_width, target_height), Image.Resampling.LANCZOS)
    _draw_annotations(rendered, annotations, image.size, view, accent_color)

    output = BytesIO()
    rendered.save(output, format="WEBP", quality=88, method=6)
    return output.getvalue()
