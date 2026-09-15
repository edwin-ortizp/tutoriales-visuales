from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .image_tools import InvalidImageError, normalize_to_png
from .models import RichText, TutorialProject, TutorialStep, normalize_color
from .project_io import load_project, save_project


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
REQUIRED_CONTEXT = ("platform", "objective", "audience", "initial_state", "expected_result")


class InvalidDraftError(ValueError):
    pass


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))


def _read_json(path: str | Path) -> dict[str, object]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidDraftError("El borrador no contiene JSON válido.") from exc
    if not isinstance(raw, dict):
        raise InvalidDraftError("La raíz del borrador debe ser un objeto JSON.")
    if raw.get("draft_version") != 1:
        raise InvalidDraftError("La versión del borrador no es compatible.")
    return raw


def _write_json_atomic(path: str | Path, value: dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent, delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _require_approved(draft: dict[str, object]) -> None:
    if draft.get("approved") is not True:
        raise InvalidDraftError(
            "El borrador todavía no está aprobado. Revísalo y establece approved en true."
        )
    doubts = draft.get("unresolved_questions", [])
    if not isinstance(doubts, list) or doubts:
        raise InvalidDraftError("El borrador conserva preguntas sin resolver.")


def _require_operation(draft: dict[str, object], expected: str) -> None:
    operation = draft.get("operation")
    if operation != expected:
        raise InvalidDraftError(
            f"Este comando requiere un borrador con operation={expected!r}; "
            f"se recibió {operation!r}."
        )


def _context(draft: dict[str, object]) -> dict[str, object]:
    context = draft.get("context")
    if not isinstance(context, dict):
        raise InvalidDraftError("Falta el contexto estructurado del tutorial.")
    missing = [key for key in REQUIRED_CONTEXT if not str(context.get(key, "")).strip()]
    if missing:
        raise InvalidDraftError(f"Falta contexto obligatorio: {', '.join(missing)}.")
    return context


def _tutorial_data(draft: dict[str, object]) -> dict[str, object]:
    tutorial = draft.get("tutorial")
    if not isinstance(tutorial, dict):
        raise InvalidDraftError("Faltan los datos del tutorial.")
    if not str(tutorial.get("title", "")).strip():
        raise InvalidDraftError("El tutorial debe tener título.")
    return tutorial


def _rich_text(raw: object, field: str) -> RichText:
    if isinstance(raw, str):
        return RichText(raw)
    if not isinstance(raw, dict):
        raise InvalidDraftError(f"{field} debe ser texto enriquecido estructurado.")
    try:
        return RichText.from_dict(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidDraftError(f"{field} contiene formato o enlaces inválidos.") from exc


def _steps(draft: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = draft.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise InvalidDraftError("El borrador debe contener al menos un paso.")
    if any(not isinstance(item, dict) for item in raw_steps):
        raise InvalidDraftError("Todos los pasos deben ser objetos JSON.")
    for index, step in enumerate(raw_steps, start=1):
        if not str(step.get("title", "")).strip():
            raise InvalidDraftError(f"El paso {index} no tiene título.")
        if not str(_rich_text(step.get("instruction", {}), f"Instrucción del paso {index}").text).strip():
            raise InvalidDraftError(f"El paso {index} no tiene instrucción.")
        doubts = step.get("doubts", [])
        if not isinstance(doubts, list) or doubts:
            raise InvalidDraftError(f"El paso {index} conserva dudas sin resolver.")
    return raw_steps


def _safe_image_path(directory: Path, name: object) -> Path:
    text = str(name)
    if Path(text).name != text or not text:
        raise InvalidDraftError(f"Nombre de imagen inseguro: {text!r}.")
    candidate = (directory / text).resolve()
    if candidate.parent != directory.resolve():
        raise InvalidDraftError(f"La imagen sale de la carpeta permitida: {text}.")
    if candidate.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise InvalidDraftError(f"Formato de imagen no compatible: {text}.")
    if not candidate.is_file():
        raise InvalidDraftError(f"No existe la imagen: {text}.")
    return candidate


def _validate_create_images(directory: Path, raw_steps: list[dict[str, object]]) -> list[Path]:
    paths = [_safe_image_path(directory, step.get("image", "")) for step in raw_steps]
    names = [path.name.casefold() for path in paths]
    if len(names) != len(set(names)):
        raise InvalidDraftError("Una imagen aparece más de una vez en el borrador.")
    expected = sorted(paths, key=lambda item: natural_key(item.name))
    if paths != expected:
        raise InvalidDraftError("Los pasos no respetan el orden natural de los nombres de imagen.")
    hashes: dict[str, str] = {}
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            raise InvalidDraftError(
                f"Las imágenes {hashes[digest]} y {path.name} tienen contenido duplicado."
            )
        hashes[digest] = path.name
    available = {
        item.name.casefold()
        for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    }
    if set(names) != available:
        missing = sorted(available - set(names))
        extra = sorted(set(names) - available)
        details = []
        if missing:
            details.append(f"sin usar: {', '.join(missing)}")
        if extra:
            details.append(f"no disponibles: {', '.join(extra)}")
        raise InvalidDraftError("La lista de imágenes no coincide con la carpeta (" + "; ".join(details) + ").")
    return paths


def _branding(tutorial: dict[str, object], base: Path) -> tuple[str, str, bytes | None]:
    raw = tutorial.get("branding", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise InvalidDraftError("La identidad visual es inválida.")
    logo_png = None
    logo_name = raw.get("logo")
    if logo_name:
        logo = _safe_image_path(base, logo_name)
        try:
            logo_png = normalize_to_png(logo)
        except InvalidImageError as exc:
            raise InvalidDraftError(f"El logo no es válido: {logo.name}.") from exc
    return str(raw.get("name", "")), normalize_color(str(raw.get("accent_color", ""))), logo_png


def _report(
    operation: str,
    output: Path,
    draft: dict[str, object],
    images: list[str],
    source: Path | None = None,
) -> dict[str, object]:
    return {
        "report_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "source_project": str(source) if source else None,
        "output_project": str(output),
        "images": images,
        "decisions": draft.get("decisions", []),
        "warnings": draft.get("warnings", []),
        "visual_review_required": True,
    }


def create_project_from_draft(
    images_dir: str | Path,
    draft_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    draft = _read_json(draft_path)
    _require_operation(draft, "create")
    _require_approved(draft)
    _context(draft)
    tutorial = _tutorial_data(draft)
    raw_steps = _steps(draft)
    directory = Path(images_dir).resolve()
    if not directory.is_dir():
        raise InvalidDraftError("La carpeta de imágenes no existe.")
    image_paths = _validate_create_images(directory, raw_steps)
    target = Path(output_path)
    if target.suffix.lower() != ".tutorial":
        target = target.with_suffix(".tutorial")
    if target.exists() and not overwrite:
        raise InvalidDraftError("El archivo de salida ya existe; usa --overwrite para reemplazarlo.")
    brand_name, accent_color, logo_png = _branding(tutorial, Path(draft_path).resolve().parent)
    project = TutorialProject(
        title=str(tutorial["title"]),
        description=_rich_text(tutorial.get("description", {}), "Descripción"),
        brand_name=brand_name,
        accent_color=accent_color,
        logo_png=logo_png,
    )
    try:
        for raw, image_path in zip(raw_steps, image_paths):
            project.steps.append(
                TutorialStep(
                    title=str(raw["title"]),
                    instruction=_rich_text(raw["instruction"], "Instrucción"),
                    image_png=normalize_to_png(image_path),
                    focus_x=0.5,
                    focus_y=0.5,
                    zoom=1.0,
                    crop=None,
                    annotations=[],
                    visual_reviewed=False,
                )
            )
    except InvalidImageError as exc:
        raise InvalidDraftError("Una captura no contiene una imagen válida.") from exc
    saved = save_project(target, project)
    report_path = saved.with_suffix(".report.json")
    _write_json_atomic(
        report_path,
        _report("create", saved.resolve(), draft, [item.name for item in image_paths]),
    )
    return saved, report_path


def inspect_project(project_path: str | Path, output_path: str | Path) -> Path:
    source = Path(project_path).resolve()
    project = load_project(source)
    draft = {
        "draft_version": 1,
        "operation": "update",
        "approved": False,
        "source_project": str(source),
        "context": {key: "" for key in REQUIRED_CONTEXT},
        "tutorial": {
            "title": project.title,
            "description": project.description.as_dict(),
            "branding": {
                "name": project.brand_name,
                "accent_color": project.accent_color,
                "logo": None,
            },
        },
        "steps": [
            {
                "id": step.id,
                "title": step.title,
                "instruction": step.instruction.as_dict(),
                "observation": "",
                "doubts": [],
            }
            for step in project.steps
        ],
        "unresolved_questions": [],
        "decisions": [],
        "warnings": ["Completar el contexto y revisar el contenido antes de aprobar."],
    }
    return _write_json_atomic(output_path, draft)


def update_project_from_draft(
    project_path: str | Path,
    draft_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    source = Path(project_path).resolve()
    draft = _read_json(draft_path)
    _require_operation(draft, "update")
    _require_approved(draft)
    _context(draft)
    tutorial = _tutorial_data(draft)
    raw_steps = _steps(draft)
    project = load_project(source)
    by_id = {step.id: step for step in project.steps}
    ids = [str(raw.get("id", "")) for raw in raw_steps]
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise InvalidDraftError("La edición debe conservar exactamente los IDs de pasos existentes.")
    target = Path(output_path) if output_path else source.with_name(f"{source.stem}-editado.tutorial")
    if target.suffix.lower() != ".tutorial":
        target = target.with_suffix(".tutorial")
    if target.resolve() == source and not overwrite:
        raise InvalidDraftError("Para reemplazar el proyecto original debes usar --overwrite.")
    if target.exists() and not overwrite:
        raise InvalidDraftError("El archivo de salida ya existe; usa --overwrite para reemplazarlo.")
    updated = deepcopy(project)
    updated.title = str(tutorial["title"])
    updated.description = _rich_text(tutorial.get("description", {}), "Descripción")
    raw_branding = tutorial.get("branding", {})
    if isinstance(raw_branding, dict):
        updated.brand_name = str(raw_branding.get("name", updated.brand_name))
        updated.accent_color = normalize_color(
            str(raw_branding.get("accent_color", updated.accent_color))
        )
    preserved = {step.id: step for step in updated.steps}
    reordered: list[TutorialStep] = []
    for raw in raw_steps:
        step = preserved[str(raw["id"])]
        step.title = str(raw["title"])
        step.instruction = _rich_text(raw["instruction"], "Instrucción")
        reordered.append(step)
    updated.steps = reordered
    saved = save_project(target, updated)
    report_path = saved.with_suffix(".report.json")
    _write_json_atomic(
        report_path,
        _report("update", saved.resolve(), draft, [], source=source),
    )
    return saved, report_path
