from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from .image_tools import image_size
from .models import Annotation, NormalizedRect, RichText, TutorialProject, TutorialStep


class InvalidProjectError(ValueError):
    pass


def _step_manifest(step: TutorialStep, index: int) -> dict[str, object]:
    return {
        "id": step.id,
        "position": index,
        "title": step.title,
        "instruction": step.instruction.as_dict(),
        "image": f"images/{step.id}.png",
        "focus": {"x": step.focus_x, "y": step.focus_y},
        "zoom": step.zoom,
        "crop": step.crop.as_dict() if step.crop else None,
        "annotations": [annotation.as_dict() for annotation in step.annotations],
        "visual_reviewed": step.visual_reviewed,
    }


def _read_image(archive: zipfile.ZipFile, name: str) -> bytes:
    data = archive.read(name)
    image_size(data)  # valida la imagen sin volver a codificarla
    return data


def save_project(path: str | Path, project: TutorialProject) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".tutorial":
        target = target.with_suffix(".tutorial")
    target.parent.mkdir(parents=True, exist_ok=True)
    project.normalize()

    logo_path = "branding/logo.png" if project.logo_png else None
    manifest = {
        "schema_version": 3,
        "title": project.title,
        "description": project.description.as_dict(),
        "branding": {
            "name": project.brand_name,
            "accent_color": project.accent_color,
            "logo": logo_path,
        },
        "steps": [_step_manifest(step, index) for index, step in enumerate(project.steps)],
    }

    temp_file = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent, delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "project.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for step in project.steps:
                image_size(step.image_png)  # valida sin modificar los bytes originales
                archive.writestr(f"images/{step.id}.png", step.image_png)
            if project.logo_png:
                image_size(project.logo_png)
                archive.writestr("branding/logo.png", project.logo_png)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)
    return target


def _load_v1(manifest: dict[str, object], archive: zipfile.ZipFile) -> TutorialProject:
    """Migra el marcador implícito del esquema 1 a una anotación explícita."""

    project = TutorialProject(
        title=str(manifest.get("title", "")),
        description=RichText(str(manifest.get("description", ""))),
    )
    raw_steps = manifest.get("steps", [])
    if not isinstance(raw_steps, list):
        raise InvalidProjectError("La lista de pasos es inválida.")
    for raw in sorted(raw_steps, key=lambda item: item.get("position", 0)):
        focus = raw.get("focus", {})
        focus_x = float(focus.get("x", 0.5))
        focus_y = float(focus.get("y", 0.5))
        step = TutorialStep(
            id=str(raw["id"]),
            title=str(raw.get("title", "")),
            instruction=RichText(str(raw.get("instruction", ""))),
            image_png=_read_image(archive, str(raw["image"])),
            focus_x=focus_x,
            focus_y=focus_y,
            zoom=float(raw.get("zoom", 1.0)),
            annotations=[Annotation("marker", x1=focus_x, y1=focus_y)],
            visual_reviewed=True,
        )
        step.normalize()
        project.steps.append(step)
    return project


def _load_v2(manifest: dict[str, object], archive: zipfile.ZipFile) -> TutorialProject:
    branding = manifest.get("branding", {})
    if not isinstance(branding, dict):
        raise InvalidProjectError("La identidad visual del proyecto es inválida.")
    logo_name = branding.get("logo")
    logo_png = _read_image(archive, str(logo_name)) if logo_name else None
    project = TutorialProject(
        title=str(manifest.get("title", "")),
        description=RichText(str(manifest.get("description", ""))),
        brand_name=str(branding.get("name", "")),
        accent_color=str(branding.get("accent_color", "#ff7a00")),
        logo_png=logo_png,
    )
    raw_steps = manifest.get("steps", [])
    if not isinstance(raw_steps, list):
        raise InvalidProjectError("La lista de pasos es inválida.")
    for raw in sorted(raw_steps, key=lambda item: item.get("position", 0)):
        focus = raw.get("focus", {})
        raw_crop = raw.get("crop")
        raw_annotations = raw.get("annotations", [])
        if not isinstance(focus, dict) or not isinstance(raw_annotations, list):
            raise InvalidProjectError("Los datos visuales de un paso son inválidos.")
        crop = NormalizedRect.from_dict(raw_crop) if isinstance(raw_crop, dict) else None
        annotations = [Annotation.from_dict(item) for item in raw_annotations]
        step = TutorialStep(
            id=str(raw["id"]),
            title=str(raw.get("title", "")),
            instruction=RichText(str(raw.get("instruction", ""))),
            image_png=_read_image(archive, str(raw["image"])),
            focus_x=float(focus.get("x", 0.5)),
            focus_y=float(focus.get("y", 0.5)),
            zoom=float(raw.get("zoom", 1.0)),
            crop=crop,
            annotations=annotations,
            visual_reviewed=bool(raw.get("visual_reviewed", False)),
        )
        step.normalize()
        project.steps.append(step)
    project.normalize()
    return project


def _load_v3(manifest: dict[str, object], archive: zipfile.ZipFile) -> TutorialProject:
    branding = manifest.get("branding", {})
    description = manifest.get("description", {})
    if not isinstance(branding, dict) or not isinstance(description, dict):
        raise InvalidProjectError("Los datos del proyecto son inválidos.")
    logo_name = branding.get("logo")
    logo_png = _read_image(archive, str(logo_name)) if logo_name else None
    project = TutorialProject(
        title=str(manifest.get("title", "")),
        description=RichText.from_dict(description),
        brand_name=str(branding.get("name", "")),
        accent_color=str(branding.get("accent_color", "#ff7a00")),
        logo_png=logo_png,
    )
    raw_steps = manifest.get("steps", [])
    if not isinstance(raw_steps, list):
        raise InvalidProjectError("La lista de pasos es inválida.")
    for raw in sorted(raw_steps, key=lambda item: item.get("position", 0)):
        focus = raw.get("focus", {})
        raw_crop = raw.get("crop")
        raw_annotations = raw.get("annotations", [])
        instruction = raw.get("instruction", {})
        if (
            not isinstance(focus, dict)
            or not isinstance(raw_annotations, list)
            or not isinstance(instruction, dict)
        ):
            raise InvalidProjectError("Los datos de un paso son inválidos.")
        crop = NormalizedRect.from_dict(raw_crop) if isinstance(raw_crop, dict) else None
        annotations = [Annotation.from_dict(item) for item in raw_annotations]
        step = TutorialStep(
            id=str(raw["id"]),
            title=str(raw.get("title", "")),
            instruction=RichText.from_dict(instruction),
            image_png=_read_image(archive, str(raw["image"])),
            focus_x=float(focus.get("x", 0.5)),
            focus_y=float(focus.get("y", 0.5)),
            zoom=float(raw.get("zoom", 1.0)),
            crop=crop,
            annotations=annotations,
            visual_reviewed=bool(raw.get("visual_reviewed", False)),
        )
        step.normalize()
        project.steps.append(step)
    project.normalize()
    return project


def load_project(path: str | Path) -> TutorialProject:
    source = Path(path)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            manifest = json.loads(archive.read("project.json").decode("utf-8"))
            version = manifest.get("schema_version")
            if version == 1:
                return _load_v1(manifest, archive)
            if version == 2:
                return _load_v2(manifest, archive)
            if version == 3:
                return _load_v3(manifest, archive)
            raise InvalidProjectError("La versión del proyecto no es compatible.")
    except InvalidProjectError:
        raise
    except (
        KeyError,
        OSError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidProjectError("El archivo no es un proyecto .tutorial válido.") from exc
