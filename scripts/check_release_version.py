"""Preflight obligatorio: repositorio público y etiqueta todavía no publicada."""
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutorial_app import __version__
from tutorial_app.versioning import version_key


def check():
    key = version_key(__version__)
    if key[0] == 0:
        raise RuntimeError("La publicación debe usar una versión calendario")
    base = "https://api.github.com/repos/edwin-ortizp/tutoriales-visuales"
    headers = {"User-Agent": "TutorialesVisuales-Release"}
    with urlopen(Request(base, headers=headers), timeout=30) as response:
        if json.load(response).get("private", True):
            raise RuntimeError("El actualizador requiere un repositorio público")
    try:
        with urlopen(Request(f"{base}/releases/tags/v.{__version__}", headers=headers), timeout=30):
            pass
    except HTTPError as exc:
        if exc.code == 404:
            if key[3] > 1:
                base_version = __version__.rsplit(".", 1)[0]
                previous = base_version if key[3] == 2 else f"{base_version}.{key[3] - 1}"
                with urlopen(Request(f"{base}/releases/tags/v.{previous}", headers=headers), timeout=30) as response:
                    prior = json.load(response)
                if prior.get("draft") or prior.get("prerelease") or not prior.get("published_at"):
                    raise RuntimeError("El consecutivo anterior debe estar publicado como release estable")
            return
        raise
    raise RuntimeError(f"La versión v.{__version__} ya fue publicada; incrementa la fecha o el consecutivo")


if __name__ == "__main__":
    check()
