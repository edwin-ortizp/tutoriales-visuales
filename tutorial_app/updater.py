from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.parse import quote

from . import __version__
from .versioning import release_version, version_key

REPOSITORY = "edwin-ortizp/tutoriales-visuales"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES = f"https://github.com/{REPOSITORY}/releases/latest"


def update_directory() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Tutoriales Visuales" / "updates"


def distribution() -> str:
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return "source"
    try:
        marker = json.loads((Path(sys.executable).parent / "installation.json").read_text(encoding="utf-8"))
        if marker == {"distribution": "installed", "scope": "current-user"}:
            return "installed"
    except (OSError, ValueError):
        pass
    return "portable"


def request(url: str):
    parsed = urlparse(url)
    allowed = parsed.scheme == "https" and (
        url == API or (parsed.netloc == "github.com" and parsed.path.startswith(f"/{REPOSITORY}/releases/download/"))
    )
    if not allowed:
        raise ValueError("Dirección de actualización no permitida")
    return urlopen(Request(url, headers={"User-Agent": f"TutorialesVisuales/{__version__}", "Accept": "application/vnd.github+json"}), timeout=30)


def read_json(url: str) -> dict:
    with request(url) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Metadatos demasiado grandes")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Metadatos inválidos")
    return value


def find_update() -> dict | None:
    release = read_json(API)
    if release.get("draft") or release.get("prerelease"):
        return None
    version = release_version(release["tag_name"])
    if version_key(version) <= version_key(__version__):
        return None
    assets = {asset["name"]: asset for asset in release["assets"]}
    prefix = f"https://github.com/{REPOSITORY}/releases/download/{quote(release['tag_name'], safe='')}/"
    def asset_url(name):
        url = assets[name]["browser_download_url"]
        if url != prefix + quote(name, safe=""):
            raise ValueError("El archivo no pertenece a la release consultada")
        return url
    manifest = read_json(asset_url("release-manifest.json"))
    if (manifest.get("version") != version or manifest.get("architecture") != "x64"
            or manifest.get("product") != "Tutoriales Visuales"
            or manifest.get("installation_scope") != "current-user"):
        raise ValueError("Manifiesto incompatible")
    name = f"tutoriales-visuales-setup-{version}.exe"
    artifact = next(item for item in manifest["artifacts"] if item["name"] == name)
    if type(artifact["bytes"]) is not int or not 0 < artifact["bytes"] <= 2 * 1024**3:
        raise ValueError("Tamaño inválido")
    if not re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"]):
        raise ValueError("SHA-256 inválido")
    if assets[name]["size"] != artifact["bytes"]:
        raise ValueError("Tamaño inconsistente")
    return dict(artifact, version=version, url=asset_url(name))


def download_update(info: dict, progress=lambda value: None) -> Path:
    folder = update_directory()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info["name"]
    partial = target.with_suffix(".partial")
    digest = hashlib.sha256()
    count = 0
    try:
        with request(info["url"]) as response, partial.open("wb") as output:
            while chunk := response.read(256 * 1024):
                count += len(chunk)
                if count > info["bytes"]:
                    raise ValueError("Descarga mayor de lo esperado")
                output.write(chunk)
                digest.update(chunk)
                progress(int(count * 100 / info["bytes"]))
        if count != info["bytes"] or digest.hexdigest() != info["sha256"]:
            raise ValueError("La descarga no supera la verificación SHA-256/tamaño")
        partial.replace(target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def launch_update(installer: Path, info: dict, project: Path | None) -> None:
    # Verificar otra vez justo antes de entregar el instalador al ayudante.
    with installer.open("rb") as downloaded:
        digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
    if installer.stat().st_size != info["bytes"] or digest != info["sha256"]:
        raise ValueError("El instalador cambió después de descargarse")
    folder = update_directory()
    from .resources import resource_path
    helper = folder / "update-helper.ps1"
    shutil.copyfile(resource_path("packaging/update-helper.ps1"), helper)
    job = folder / "update-job.json"
    job.write_text(json.dumps({"pid": os.getpid(), "installer": str(installer),
        "sha256": info["sha256"], "exe": sys.executable,
        "directory": str(Path(sys.executable).parent), "project": str(project) if project else "",
        "result": str(folder / "result.json"), "log": str(folder / "install.log")}), encoding="utf-8")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper), "-JobPath", str(job)], creationflags=subprocess.CREATE_NO_WINDOW)
