from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tutorial_app.ai_drafts import (
    InvalidDraftError,
    create_project_from_draft,
    inspect_project,
    natural_key,
    update_project_from_draft,
)
from tutorial_app.image_tools import normalize_to_png
from tutorial_app.models import Annotation, NormalizedRect, RichText, TextMark, TutorialProject, TutorialStep
from tutorial_app.project_io import load_project, save_project


def write_image(
    path: Path,
    color: str | tuple[int, int, int] = "white",
    format_name: str | None = None,
) -> None:
    Image.new("RGB", (80, 45), color).save(path, format=format_name)


def context() -> dict[str, object]:
    return {
        "platform": "Plataforma",
        "objective": "Crear un registro",
        "audience": "Personal operativo",
        "initial_state": "Sesión iniciada",
        "expected_result": "Registro guardado",
        "prerequisites": [],
        "terminology": [],
        "confirmed_transitions": [],
    }


def draft_for(names: list[str], *, approved: bool = True) -> dict[str, object]:
    return {
        "draft_version": 1,
        "operation": "create",
        "approved": approved,
        "context": context(),
        "tutorial": {
            "title": "Registrar información",
            "description": {"text": "Guía segura", "marks": [{"type": "bold", "start": 0, "end": 4}]},
            "branding": {"name": "Marca", "accent_color": "#2563eb", "logo": None},
        },
        "steps": [
            {
                "image": name,
                "title": f"Acción {index}",
                "instruction": {"text": f"Realiza el paso {index}.", "marks": []},
                "observation": "Interfaz visible",
                "doubts": [],
            }
            for index, name in enumerate(names, start=1)
        ],
        "unresolved_questions": [],
        "decisions": ["Orden confirmado"],
        "warnings": ["Revisar datos visibles"],
    }


def write_draft(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("total", [1, 2, 8, 21])
def test_create_generates_schema_3_for_step_counts(tmp_path: Path, total: int) -> None:
    images = tmp_path / "images"
    images.mkdir()
    names = [f"{index:02d}.png" for index in range(1, total + 1)]
    for index, name in enumerate(names):
        write_image(
            images / name,
            (index % 256, (index * 37) % 256, (index * 83) % 256),
        )
    draft_path = tmp_path / "draft.json"
    write_draft(draft_path, draft_for(names))

    output, report = create_project_from_draft(images, draft_path, tmp_path / "result")
    loaded = load_project(output)

    assert output.suffix == ".tutorial"
    assert report.name == "result.report.json"
    assert loaded.schema_version == 3
    assert len(loaded.steps) == total
    assert all(step.zoom == 1.0 and step.focus_x == step.focus_y == 0.5 for step in loaded.steps)
    assert all(step.crop is None and step.annotations == [] for step in loaded.steps)
    assert all(step.visual_reviewed is False for step in loaded.steps)
    report_data = json.loads(report.read_text(encoding="utf-8"))
    assert report_data["images"] == names
    assert report_data["visual_review_required"] is True


def test_natural_order_accepts_1_2_10_and_normalizes_formats(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    names = ["1.jpg", "2.webp", "10.png"]
    write_image(images / names[0], "red", "JPEG")
    write_image(images / names[1], "green", "WEBP")
    write_image(images / names[2], "blue", "PNG")
    assert sorted(reversed(names), key=natural_key) == names
    draft_path = tmp_path / "draft.json"
    draft = draft_for(names)
    draft["steps"][0]["instruction"] = {
        "text": "Visita el portal",
        "marks": [{"type": "link", "start": 0, "end": 6, "url": "https://example.com"}],
    }
    write_draft(draft_path, draft)

    output, _ = create_project_from_draft(images, draft_path, tmp_path / "formats.tutorial")
    loaded = load_project(output)

    assert [step.title for step in loaded.steps] == ["Acción 1", "Acción 2", "Acción 3"]
    assert all(step.image_png.startswith(b"\x89PNG") for step in loaded.steps)
    assert loaded.steps[0].instruction.marks[0].url == "https://example.com"


def test_unapproved_or_uncertain_draft_creates_no_output(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    write_image(images / "01.png")
    draft_path = tmp_path / "draft.json"
    draft = draft_for(["01.png"], approved=False)
    write_draft(draft_path, draft)
    output = tmp_path / "blocked.tutorial"

    with pytest.raises(InvalidDraftError, match="no está aprobado"):
        create_project_from_draft(images, draft_path, output)
    assert not output.exists()
    assert not output.with_suffix(".report.json").exists()

    draft["approved"] = True
    draft["steps"][0]["doubts"] = ["No se distingue el botón"]
    write_draft(draft_path, draft)
    with pytest.raises(InvalidDraftError, match="conserva dudas"):
        create_project_from_draft(images, draft_path, output)
    assert not output.exists()


def test_create_rejects_duplicate_invalid_and_unsafe_inputs(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    write_image(images / "01.png", "red")
    (images / "02.png").write_bytes((images / "01.png").read_bytes())
    draft_path = tmp_path / "draft.json"
    draft = draft_for(["01.png", "02.png"])
    write_draft(draft_path, draft)
    with pytest.raises(InvalidDraftError, match="contenido duplicado"):
        create_project_from_draft(images, draft_path, tmp_path / "duplicate.tutorial")

    (images / "02.png").write_text("no es una imagen", encoding="utf-8")
    with pytest.raises(InvalidDraftError, match="imagen válida"):
        create_project_from_draft(images, draft_path, tmp_path / "invalid.tutorial")

    write_image(images / "02.png", "blue")
    draft["steps"][0]["instruction"] = {
        "text": "Abrir",
        "marks": [{"type": "link", "start": 0, "end": 5, "url": "javascript:alert(1)"}],
    }
    write_draft(draft_path, draft)
    with pytest.raises(InvalidDraftError, match="enlaces inválidos"):
        create_project_from_draft(images, draft_path, tmp_path / "unsafe.tutorial")


def test_inspect_and_update_preserve_images_ids_logo_and_visual_state(tmp_path: Path) -> None:
    first = TutorialStep(
        title="Primero",
        instruction=RichText("Uno", [TextMark("bold", 0, 3)]),
        image_png=normalize_to_png(Image.new("RGB", (100, 60), "red")),
        focus_x=0.2,
        focus_y=0.7,
        zoom=2.0,
        crop=NormalizedRect(0.1, 0.2, 0.7, 0.6),
        annotations=[Annotation("rectangle", x1=0.2, y1=0.2, x2=0.5, y2=0.6)],
        visual_reviewed=True,
    )
    second = TutorialStep(
        title="Segundo",
        instruction="Dos",
        image_png=normalize_to_png(Image.new("RGB", (100, 60), "blue")),
        visual_reviewed=True,
    )
    original = TutorialProject(
        title="Original",
        logo_png=normalize_to_png(Image.new("RGB", (30, 20), "orange")),
        steps=[first, second],
    )
    source = save_project(tmp_path / "original.tutorial", original)
    draft_path = inspect_project(source, tmp_path / "edit.json")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["approved"] = True
    draft["context"] = context()
    draft["tutorial"]["title"] = "Actualizado"
    draft["steps"].reverse()
    draft["steps"][0]["title"] = "Ahora primero"
    draft["warnings"] = []
    write_draft(draft_path, draft)

    output, report = update_project_from_draft(source, draft_path)
    loaded = load_project(output)

    assert output.name == "original-editado.tutorial"
    assert source.exists() and report.exists()
    assert loaded.title == "Actualizado"
    assert [step.id for step in loaded.steps] == [second.id, first.id]
    assert loaded.steps[1].image_png == first.image_png
    assert loaded.steps[1].visual_state() == first.visual_state()
    assert loaded.logo_png == original.logo_png


def test_update_rejects_changed_ids_and_does_not_overwrite_source(tmp_path: Path) -> None:
    project = TutorialProject(
        steps=[TutorialStep(title="Paso", instruction="Hazlo", image_png=normalize_to_png(Image.new("RGB", (20, 20))))]
    )
    source = save_project(tmp_path / "source.tutorial", project)
    original_bytes = source.read_bytes()
    draft_path = inspect_project(source, tmp_path / "draft.json")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["approved"] = True
    draft["context"] = context()
    draft["steps"][0]["id"] = "desconocido"
    write_draft(draft_path, draft)

    with pytest.raises(InvalidDraftError, match="conservar exactamente"):
        update_project_from_draft(source, draft_path)
    assert source.read_bytes() == original_bytes
