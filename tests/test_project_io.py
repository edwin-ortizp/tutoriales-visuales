from pathlib import Path
import json
import zipfile

import pytest
from PIL import Image

from tutorial_app.image_tools import normalize_to_png
from tutorial_app.models import (
    Annotation,
    NormalizedRect,
    RichText,
    TextMark,
    TutorialProject,
    TutorialStep,
)
from tutorial_app.project_io import InvalidProjectError, load_project, save_project


def sample_png(color: str) -> bytes:
    return normalize_to_png(Image.new("RGB", (320, 180), color))


def test_project_round_trip_preserves_unicode_images_and_order(tmp_path: Path) -> None:
    project = TutorialProject(
        title="Cómo crear una relación",
        description=RichText(
            "Guía rápida con tildes y ñ.",
            [TextMark("bold", 0, 4), TextMark("link", 5, 11, "https://example.com")],
        ),
        brand_name="Life Tracker",
        accent_color="#2563eb",
        logo_png=sample_png("orange"),
        steps=[
            TutorialStep(
                title="Abre Configuración",
                instruction=RichText(
                    "Selecciona la opción indicada.", [TextMark("bold", 0, 10)]
                ),
                image_png=sample_png("navy"),
                focus_x=0.12,
                focus_y=0.92,
                zoom=2.4,
                crop=NormalizedRect(0.05, 0.1, 0.8, 0.7),
                annotations=[
                    Annotation("arrow", x1=0.2, y1=0.3, x2=0.6, y2=0.5),
                    Annotation("redaction_solid", x1=0.7, y1=0.2, x2=0.8, y2=0.3),
                ],
                visual_reviewed=True,
            ),
            TutorialStep(
                title="Guarda",
                instruction="Confirma los cambios.",
                image_png=sample_png("white"),
                focus_x=0.85,
                focus_y=0.15,
                zoom=1.3,
            ),
        ],
    )

    original_bytes = project.steps[0].image_png
    target = save_project(tmp_path / "mi-guia", project)
    loaded = load_project(target)

    assert target.suffix == ".tutorial"
    assert project.steps[0].image_png == original_bytes
    assert loaded.schema_version == 3
    assert loaded.title == project.title
    assert loaded.description == project.description
    assert [mark.type for mark in loaded.description.marks] == ["bold", "link"]
    assert loaded.brand_name == "Life Tracker"
    assert loaded.accent_color == "#2563eb"
    assert loaded.logo_png == project.logo_png
    assert [step.title for step in loaded.steps] == [step.title for step in project.steps]
    assert loaded.steps[0].focus_x == pytest.approx(0.12)
    assert loaded.steps[0].focus_y == pytest.approx(0.92)
    assert loaded.steps[0].zoom == pytest.approx(2.4)
    assert loaded.steps[0].crop == NormalizedRect(0.05, 0.1, 0.8, 0.7)
    assert [item.type for item in loaded.steps[0].annotations] == ["arrow", "redaction_solid"]
    assert loaded.steps[0].visual_reviewed is True
    assert loaded.steps[0].image_png == original_bytes
    assert loaded.steps[0].image_png.startswith(b"\x89PNG")


def test_load_rejects_corrupt_project(tmp_path: Path) -> None:
    target = tmp_path / "roto.tutorial"
    target.write_bytes(b"esto no es un zip")
    with pytest.raises(InvalidProjectError):
        load_project(target)


def test_schema_1_is_migrated_with_explicit_marker(tmp_path: Path) -> None:
    target = tmp_path / "legacy.tutorial"
    image_png = sample_png("white")
    manifest = {
        "schema_version": 1,
        "title": "Proyecto anterior",
        "description": "",
        "steps": [
            {
                "id": "legacy-step",
                "position": 0,
                "title": "Abrir",
                "instruction": "Abre la opción.",
                "image": "images/legacy-step.png",
                "focus": {"x": 0.25, "y": 0.75},
                "zoom": 1.8,
            }
        ],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest).encode("utf-8"))
        archive.writestr("images/legacy-step.png", image_png)

    loaded = load_project(target)

    assert loaded.schema_version == 3
    assert loaded.steps[0].instruction.text == "Abre la opción."
    assert loaded.steps[0].image_png == image_png
    assert loaded.steps[0].visual_reviewed is True
    assert len(loaded.steps[0].annotations) == 1
    marker = loaded.steps[0].annotations[0]
    assert marker.type == "marker"
    assert marker.x1 == pytest.approx(0.25)
    assert marker.y1 == pytest.approx(0.75)


def test_schema_2_plain_text_is_migrated_to_schema_3(tmp_path: Path) -> None:
    target = tmp_path / "version-2.tutorial"
    image_png = sample_png("white")
    manifest = {
        "schema_version": 2,
        "title": "Proyecto versión 2",
        "description": "Descripción anterior",
        "branding": {"name": "Marca", "accent_color": "#2563eb", "logo": None},
        "steps": [
            {
                "id": "step-v2",
                "position": 0,
                "title": "Abrir",
                "instruction": "Texto anterior",
                "image": "images/step-v2.png",
                "focus": {"x": 0.5, "y": 0.5},
                "zoom": 1,
                "crop": None,
                "annotations": [],
                "visual_reviewed": True,
            }
        ],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest).encode("utf-8"))
        archive.writestr("images/step-v2.png", image_png)

    loaded = load_project(target)

    assert loaded.schema_version == 3
    assert loaded.description == RichText("Descripción anterior")
    assert loaded.steps[0].instruction == RichText("Texto anterior")


def test_schema_2_rejects_unknown_annotation_type(tmp_path: Path) -> None:
    target = tmp_path / "invalid-geometry.tutorial"
    image_png = sample_png("white")
    manifest = {
        "schema_version": 2,
        "title": "Inválido",
        "description": "",
        "branding": {"name": "", "accent_color": "#ff7a00", "logo": None},
        "steps": [
            {
                "id": "step",
                "position": 0,
                "title": "Paso",
                "instruction": "Texto",
                "image": "images/step.png",
                "focus": {"x": 0.5, "y": 0.5},
                "zoom": 1,
                "crop": None,
                "visual_reviewed": True,
                "annotations": [
                    {
                        "id": "bad",
                        "type": "tipo_desconocido",
                        "geometry": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                    }
                ],
            }
        ],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest).encode("utf-8"))
        archive.writestr("images/step.png", image_png)

    with pytest.raises(InvalidProjectError):
        load_project(target)
