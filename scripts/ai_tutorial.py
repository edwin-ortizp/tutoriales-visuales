from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tutorial_app.ai_drafts import (  # noqa: E402
    InvalidDraftError,
    create_project_from_draft,
    inspect_project,
    update_project_from_draft,
)
from tutorial_app.project_io import InvalidProjectError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Genera proyectos .tutorial desde borradores aprobados."
    )
    commands = result.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Crear desde imágenes y un borrador aprobado")
    create.add_argument("--images", required=True, type=Path)
    create.add_argument("--draft", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--overwrite", action="store_true")

    inspect = commands.add_parser("inspect", help="Extraer un proyecto a un borrador editable")
    inspect.add_argument("--project", required=True, type=Path)
    inspect.add_argument("--output", required=True, type=Path)

    update = commands.add_parser("update", help="Aplicar un borrador aprobado a una copia")
    update.add_argument("--project", required=True, type=Path)
    update.add_argument("--draft", required=True, type=Path)
    update.add_argument("--output", type=Path)
    update.add_argument("--overwrite", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "create":
            project, report = create_project_from_draft(
                arguments.images,
                arguments.draft,
                arguments.output,
                overwrite=arguments.overwrite,
            )
            print(f"Proyecto: {project.resolve()}")
            print(f"Reporte: {report.resolve()}")
        elif arguments.command == "inspect":
            draft = inspect_project(arguments.project, arguments.output)
            print(f"Borrador: {draft.resolve()}")
        else:
            project, report = update_project_from_draft(
                arguments.project,
                arguments.draft,
                arguments.output,
                overwrite=arguments.overwrite,
            )
            print(f"Proyecto: {project.resolve()}")
            print(f"Reporte: {report.resolve()}")
        return 0
    except (InvalidDraftError, InvalidProjectError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
