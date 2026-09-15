from io import BytesIO

from PIL import Image

from tutorial_app.image_tools import (
    annotation_is_visible,
    normalize_to_png,
    render_step_image,
    view_box_normalized,
)
from tutorial_app.models import Annotation, NormalizedRect


def make_image(width: int = 1000, height: int = 600) -> bytes:
    image = Image.new("RGB", (width, height), "#dbeafe")
    for x in range(0, width, 100):
        for y in range(0, height, 100):
            color = "#93c5fd" if (x // 100 + y // 100) % 2 else "#eff6ff"
            for px in range(x, min(x + 100, width)):
                for py in range(y, min(y + 100, height)):
                    image.putpixel((px, py), ImageColor.getrgb(color))
    return normalize_to_png(image)


from PIL import ImageColor  # noqa: E402 - mantiene legible el helper


def test_render_preserves_viewport_ratio_and_returns_webp() -> None:
    rendered = render_step_image(make_image(), 0.5, 0.5, 2.0, max_width=800)
    with Image.open(BytesIO(rendered)) as image:
        assert image.format == "WEBP"
        assert image.size == (800, 480)


def test_render_handles_all_edges_without_changing_dimensions() -> None:
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        rendered = render_step_image(make_image(640, 360), x, y, 3.0)
        with Image.open(BytesIO(rendered)) as image:
            assert image.size == (640, 360)


def test_solid_redaction_replaces_pixels_and_preserves_original() -> None:
    original = normalize_to_png(Image.new("RGB", (600, 400), "white"))
    before = bytes(original)
    redaction = Annotation("redaction_solid", x1=0.3, y1=0.3, x2=0.7, y2=0.7)

    rendered = render_step_image(
        original, 0.5, 0.5, 1.0, annotations=[redaction], accent_color="#2563eb"
    )

    assert original == before
    with Image.open(BytesIO(rendered)).convert("RGB") as image:
        center = image.getpixel((image.width // 2, image.height // 2))
        assert all(channel < 80 for channel in center)


def test_crop_zoom_and_visibility_use_original_normalized_coordinates() -> None:
    original = make_image(1000, 600)
    crop = NormalizedRect(0.2, 0.2, 0.6, 0.6)
    view = view_box_normalized(original, crop, 0.5, 0.5, 2.0)

    assert annotation_is_visible(Annotation("marker", x1=0.5, y1=0.5), view)
    assert not annotation_is_visible(Annotation("marker", x1=0.05, y1=0.05), view)

    rendered = render_step_image(
        original,
        0.5,
        0.5,
        2.0,
        crop=crop,
        annotations=[Annotation("rectangle", x1=0.45, y1=0.45, x2=0.55, y2=0.55)],
    )
    with Image.open(BytesIO(rendered)) as image:
        assert image.size == (600, 360)


def test_blur_redaction_visibly_reduces_high_contrast_detail() -> None:
    image = Image.new("RGB", (400, 240), "white")
    for x in range(120, 280, 4):
        color = "black" if (x // 4) % 2 else "white"
        for px in range(x, min(x + 4, 280)):
            for py in range(80, 160):
                image.putpixel((px, py), ImageColor.getrgb(color))
    original = normalize_to_png(image)
    rendered = render_step_image(
        original,
        0.5,
        0.5,
        1.0,
        annotations=[Annotation("redaction_blur", x1=0.3, y1=0.33, x2=0.7, y2=0.67)],
    )

    with Image.open(BytesIO(rendered)).convert("L") as output:
        sample = output.crop((160, 100, 240, 140))
        low, high = sample.getextrema()
        assert high - low < 80
