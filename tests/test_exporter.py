import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from tutorial_app.exporter import build_html, collect_export_warnings, export_html
from tutorial_app.image_tools import normalize_to_png
from tutorial_app.models import Annotation, RichText, TextMark, TutorialProject, TutorialStep


def test_html_is_self_contained_offline_and_escapes_content(tmp_path: Path) -> None:
    image_png = normalize_to_png(Image.new("RGB", (800, 450), "#f3f4f6"))
    project = TutorialProject(
        title='Título <privado> & "seguro"',
        description="Primera línea\nSegunda línea",
        brand_name="Mi plataforma",
        accent_color="#2563eb",
        logo_png=normalize_to_png(Image.new("RGB", (120, 40), "orange")),
        steps=[
            TutorialStep(
                title="Pulsa <Guardar>",
                instruction="No escribas A&B aquí.",
                image_png=image_png,
                focus_x=0.1,
                focus_y=0.9,
                zoom=2.0,
                annotations=[Annotation("marker", x1=0.1, y1=0.9)],
                visual_reviewed=True,
            )
        ],
    )

    html = build_html(project)
    target = export_html(tmp_path / "guia", project)

    assert target.name == "guia.html"
    assert target.read_text(encoding="utf-8") == html
    assert "data:image/webp;base64," in html
    assert "http://" not in html
    assert "https://" not in html
    assert html.count("<script>") == 1
    assert "<script src=" not in html.lower()
    assert 'src="http' not in html.lower()
    assert "fetch(" not in html
    assert "localStorage" not in html
    assert "Título &lt;privado&gt; &amp; &quot;seguro&quot;" in html
    assert "Pulsa &lt;Guardar&gt;" in html
    assert "Primera línea<br>Segunda línea" in html
    assert "Mi plataforma" in html
    assert "--accent:#2563eb" in html
    assert "data:image/png;base64," in html
    assert base64.b64encode(image_png).decode("ascii") not in html

    encoded = html.split("data:image/webp;base64,", 1)[1].split('"', 1)[0]
    with Image.open(BytesIO(base64.b64decode(encoded))) as exported_image:
        assert exported_image.format == "WEBP"


def test_export_warnings_cover_instruction_review_and_hidden_annotation() -> None:
    image_png = normalize_to_png(Image.new("RGB", (500, 300), "white"))
    project = TutorialProject(
        steps=[
            TutorialStep(
                title="Paso incompleto",
                image_png=image_png,
                zoom=2.0,
                focus_x=0.5,
                focus_y=0.5,
                annotations=[Annotation("marker", x1=0.0, y1=0.0)],
            )
        ]
    )

    warnings = collect_export_warnings(project)

    assert any("no tiene instrucción" in item for item in warnings)
    assert any("revisión visual" in item for item in warnings)
    assert any("fuera del recorte o zoom" in item for item in warnings)


def test_rich_text_exports_only_safe_bold_and_links() -> None:
    image_png = normalize_to_png(Image.new("RGB", (320, 180), "white"))
    project = TutorialProject(
        description=RichText(
            "Visita el portal <seguro>",
            [TextMark("bold", 0, 6), TextMark("link", 10, 16, "https://example.com?a=1&b=2")],
        ),
        steps=[
            TutorialStep(
                instruction=RichText(
                    "Escribe a soporte@example.com <script>",
                    [TextMark("link", 10, 29, "mailto:soporte@example.com")],
                ),
                image_png=image_png,
                visual_reviewed=True,
            )
        ],
    )

    result = build_html(project)

    assert "<strong>Visita</strong>" in result
    assert 'href="https://example.com?a=1&amp;b=2"' in result
    assert 'target="_blank" rel="noopener noreferrer"' in result
    assert 'href="mailto:soporte@example.com"' in result
    assert "&lt;script&gt;" in result
    assert result.count("<script>") == 1


def tutorial_with_steps(total: int) -> TutorialProject:
    image_png = normalize_to_png(Image.new("RGB", (64, 36), "white"))
    return TutorialProject(
        title="Tutorial de navegación",
        steps=[
            TutorialStep(
                title=f"Acción número {index} con un título suficientemente descriptivo",
                instruction=RichText(f"Realiza el paso {index}."),
                image_png=image_png,
                visual_reviewed=True,
            )
            for index in range(1, total + 1)
        ],
    )


@pytest.mark.parametrize(
    ("total", "minutes"),
    [(0, None), (1, 1), (2, 1), (4, 1), (5, 2), (8, 2), (21, 6)],
)
def test_navigation_structure_handles_step_counts(total: int, minutes: int | None) -> None:
    result = build_html(tutorial_with_steps(total))
    word = "paso" if total == 1 else "pasos"

    assert f'<span class="metric-value">{total}</span><span class="metric-label">{word}</span>' in result
    assert result.count('class="step" id="paso-') == total
    assert result.count('class="index-number"') == total
    if total:
        assert f'<span class="metric-value">{minutes} min</span>' in result
        assert '<span class="metric-label">Tiempo estimado</span>' in result
        assert "Tutorial paso a paso" in result
        assert 'class="start-button" href="#paso-1"' in result
        assert "Comenzar tutorial" in result
        assert f"Ver los {total} {word}" in result
        assert f"Paso 1 de {total}" in result
        assert f"Paso {total} de {total}" in result
        assert result.count('class="rail-step-link"') == total
        assert 'class="reading-rail"' in result
        assert 'class="mobile-progress"' in result
        assert 'class="mobile-control mobile-previous is-disabled"' in result
        assert 'class="rail-top" href="#inicio"' in result
        assert "Tutorial completado" in result
        assert f"Has llegado al final de {total} {word}." in result
        assert result.count('role="progressbar"') == 2
        assert 'aria-live="polite"' in result
        assert result.count("<script>") == 1
    else:
        assert "Este tutorial aún no contiene pasos" in result
        assert "Tiempo estimado" not in result
        assert "Comenzar tutorial" not in result
        assert '<details class="tutorial-index">' not in result
        assert 'class="reading-rail"' not in result
        assert 'class="mobile-progress"' not in result
        assert "Tutorial completado" not in result
        assert "<script>" not in result


def test_navigation_script_is_static_offline_and_does_not_embed_user_content() -> None:
    project = tutorial_with_steps(2)
    project.title = '</script><script src="https://evil.example">'
    project.steps[0].title = 'Título </script><script>alert("x")</script>'

    result = build_html(project)
    script = result.split("<script>", 1)[1].split("</script>", 1)[0]

    assert result.count("<script>") == 1
    assert "Título" not in script
    assert "evil.example" not in script
    assert "IntersectionObserver" in script
    assert "requestAnimationFrame" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "eval(" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert '<script src="https://evil.example">' not in result
    assert "&lt;/script&gt;" in result


def test_navigation_has_accessible_anchors_reduced_motion_and_print_rules() -> None:
    result = build_html(tutorial_with_steps(2))

    assert 'href="#paso-1"' in result
    assert 'href="#paso-2"' in result
    assert 'href="#inicio"' in result
    assert 'id="paso-1" data-step-index="1" tabindex="-1"' in result
    assert 'aria-label="Índice del tutorial"' in result
    assert 'aria-label="Progreso y navegación del tutorial"' in result
    assert 'aria-current", "step"' in result
    assert 'width:44px; height:44px' in result
    assert "env(safe-area-inset-bottom)" in result
    assert "@media (max-width:1199px)" in result
    assert "@media (min-width:1200px)" in result
    assert "prefers-reduced-motion:reduce" in result
    assert "@media print" in result
    assert ".hero-actions,.reading-rail,.rail-tooltip,.mobile-progress,.back-top" in result
    assert "scroll-margin-top" in result


@pytest.mark.parametrize(
    ("color", "expected_text"),
    [("#111827", "#ffffff"), ("#fef08a", "#101828")],
)
def test_brand_controls_choose_contrasting_text(color: str, expected_text: str) -> None:
    project = tutorial_with_steps(1)
    project.accent_color = color

    result = build_html(project)

    assert f"--accent:{color}" in result
    assert f"--accent-ink:{expected_text}" in result
