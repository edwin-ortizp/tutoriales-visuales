import hashlib
from io import BytesIO
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tutorial_app import updater
from tutorial_app.versioning import version_key, release_version


@pytest.mark.parametrize("invalid", ["2026.02.30", "2026.10.09.1", "2026.10.09.0", "2026.1.09", "2026.10.09.65536"])
def test_invalid_calendar(invalid):
    with pytest.raises(ValueError):
        version_key(invalid)


def test_version_order():
    values = ["0.6.0", "2026.10.09", "2026.10.09.2", "2026.10.09.10", "2026.10.10"]
    assert list(map(version_key, values)) == sorted(map(version_key, values))
    assert version_key("2026.10.09") == (2026, 10, 9, 1)
    assert release_version("v.2026.10.09.2") == "2026.10.09.2"
    with pytest.raises(ValueError):
        release_version("v2026.10.09")


def metadata():
    artifact = {"name": "tutoriales-visuales-setup-2026.10.10.exe", "bytes": 4, "sha256": hashlib.sha256(b"test").hexdigest()}
    prefix = f"https://github.com/{updater.REPOSITORY}/releases/download/v.2026.10.10/"
    release = {"tag_name": "v.2026.10.10", "draft": False, "prerelease": False,
        "assets": [{"name": "release-manifest.json", "browser_download_url": prefix + "release-manifest.json"},
            dict(artifact, size=4, browser_download_url=prefix + artifact["name"])]}
    manifest = {"product": "Tutoriales Visuales", "version": "2026.10.10", "architecture": "x64", "installation_scope": "current-user", "artifacts": [artifact]}
    return release, manifest


def test_find_and_validate(monkeypatch):
    release, manifest = metadata()
    monkeypatch.setattr(updater, "read_json", lambda url: release if url == updater.API else manifest)
    assert updater.find_update()["version"] == "2026.10.10"
    manifest["version"] = "2026.10.11"
    with pytest.raises(ValueError):
        updater.find_update()


@pytest.mark.parametrize("kind", ["draft", "prerelease", "same", "older", "missing", "size", "hash", "network"])
def test_release_failures(monkeypatch, kind):
    release, manifest = metadata()
    if kind in ("draft", "prerelease"):
        release[kind] = True
    if kind in ("same", "older"):
        release["tag_name"] = "v.2026.10.09" if kind == "same" else "v.2026.10.08"
    if kind == "missing":
        release["assets"] = []
    if kind == "size":
        manifest["artifacts"][0]["bytes"] = 8
    if kind == "hash":
        manifest["artifacts"][0]["sha256"] = "invalid"
    def read(url):
        if kind == "network":
            raise OSError("offline")
        return release if url == updater.API else manifest
    monkeypatch.setattr(updater, "read_json", read)
    if kind in ("draft", "prerelease", "same", "older"):
        assert updater.find_update() is None
    else:
        with pytest.raises((KeyError, ValueError, OSError)):
            updater.find_update()


@pytest.mark.parametrize("data", [b"test", b"tes", b"fail", b"too long"])
def test_download_integrity(tmp_path, monkeypatch, data):
    monkeypatch.setattr(updater, "update_directory", lambda: tmp_path)
    monkeypatch.setattr(updater, "request", lambda url: BytesIO(data))
    info = dict(metadata()[1]["artifacts"][0], url="installer")
    if data == b"test":
        assert updater.download_update(info).read_bytes() == data
    else:
        with pytest.raises(ValueError):
            updater.download_update(info)
        assert not list(tmp_path.glob("*.exe"))
    assert not list(tmp_path.glob("*.partial"))


def test_unsafe_download_url():
    with pytest.raises(ValueError):
        updater.request("https://example.com/setup.exe")


def test_distribution_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(tmp_path / "TutorialesVisuales.exe"))
    monkeypatch.setattr(updater.sys, "platform", "win32")
    assert updater.distribution() == "portable"
    marker = tmp_path / "installation.json"
    marker.write_text('{"distribution":"installed","scope":"current-user"}')
    assert updater.distribution() == "installed"
    marker.write_text("invalid")
    assert updater.distribution() == "portable"


def test_foreign_release_asset_rejected(monkeypatch):
    release, manifest = metadata()
    release["assets"][0]["browser_download_url"] = "https://example.com/manifest.json"
    monkeypatch.setattr(updater, "read_json", lambda url: release if url == updater.API else manifest)
    with pytest.raises(ValueError):
        updater.find_update()


@pytest.mark.parametrize("case", ["new", "duplicate", "second", "missing_previous"])
def test_publication_preflight(monkeypatch, case):
    from urllib.error import HTTPError
    from scripts import check_release_version as preflight
    monkeypatch.setattr(preflight, "__version__", "2026.10.09.2" if case in ("second", "missing_previous") else "2026.10.09")
    def response(request, timeout):
        url = request.full_url
        if "/releases/tags/" not in url:
            return BytesIO(json.dumps({"private": False}).encode())
        if case == "duplicate":
            return BytesIO(b"{}")
        if case == "second" and url.endswith("v.2026.10.09"):
            return BytesIO(b'{"published_at":"2026-10-09T12:00:00Z","draft":false,"prerelease":false}')
        raise HTTPError(url, 404, "missing", None, None)
    monkeypatch.setattr(preflight, "urlopen", response)
    if case in ("new", "second"):
        preflight.check()
    else:
        with pytest.raises((RuntimeError, HTTPError)):
            preflight.check()


@pytest.mark.parametrize("choice", ["save", "discard", "cancel"])
def test_update_respects_save_prompt(tmp_path, monkeypatch, choice):
    from tutorial_app.main_window import MainWindow
    application = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    selected = {"save": QMessageBox.StandardButton.Save, "discard": QMessageBox.StandardButton.Discard, "cancel": QMessageBox.StandardButton.Cancel}[choice]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: selected)
    calls = []
    monkeypatch.setattr(updater, "launch_update", lambda *args: calls.append(args))
    window = MainWindow()
    monkeypatch.setattr(window, "_save_project", lambda: True)
    window.show()
    window.dirty = True
    window._pending_update = (Path("installer.exe"), {})
    try:
        assert window.close() is (choice != "cancel")
        assert bool(calls) is (choice != "cancel")
        assert window._pending_update is None
    finally:
        window.dirty = False
        window.close()
        application.processEvents()
