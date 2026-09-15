import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tutorial_app import __version__
from tutorial_app.app import parse_arguments, run_smoke_test
from tutorial_app.single_instance import SingleInstanceController


ROOT = Path(__file__).resolve().parent.parent


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_public_cli_arguments_and_smoke_test() -> None:
    parsed = parse_arguments(["ejemplo.tutorial"])
    assert parsed.project == "ejemplo.tutorial"
    assert run_smoke_test() == 0

    version = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    smoke = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--smoke-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert version.returncode == 0
    assert f"Tutoriales Visuales {__version__}" in version.stdout
    assert smoke.returncode == 0
    assert "smoke test OK" in smoke.stdout


def test_second_instance_forwards_command_to_primary() -> None:
    application = app()
    unique = uuid4().hex
    primary = SingleInstanceController(
        server_name=f"TutorialesVisuales-Test-{unique}", mutex_name=f"TutorialesVisuales.Test.{unique}"
    )
    received: list[dict[str, object]] = []
    primary.commandReceived.connect(received.append)
    try:
        assert primary.initialize({"action": "activate"}) is True
        client_code = (
            "import sys; "
            "from tutorial_app.single_instance import SingleInstanceController; "
            "client=SingleInstanceController(server_name=sys.argv[1],mutex_name=sys.argv[2]); "
            "result=client.initialize({'action':'open','path':'C:/demo.tutorial'}); "
            "print('primary' if result else 'secondary'); client.close()"
        )
        worker = subprocess.Popen(
            [
                sys.executable,
                "-c",
                client_code,
                f"TutorialesVisuales-Test-{unique}",
                f"TutorialesVisuales.Test.{unique}",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5.0
        while worker.poll() is None and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)
        stdout, stderr = worker.communicate(timeout=1)
        deadline = time.monotonic() + 1.0
        while not received and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)
        assert worker.returncode == 0, stderr
        assert "secondary" in stdout
        assert received == [{"action": "open", "path": "C:/demo.tutorial"}]
    finally:
        primary.close()
