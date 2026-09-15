from __future__ import annotations

import copy
import json
import os
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, QThreadPool, QTimer, Signal

from . import __version__
from .models import TutorialProject
from .project_io import InvalidProjectError, load_project, save_project


class InvalidRecoveryError(ValueError):
    pass


@dataclass(slots=True)
class RecoveryMetadata:
    captured_at_utc: str
    app_version: str
    source_path: str | None
    source_size: int | None
    source_mtime_ns: int | None

    @classmethod
    def capture(cls, source_path: Path | None) -> "RecoveryMetadata":
        size: int | None = None
        mtime_ns: int | None = None
        normalized_path: str | None = None
        if source_path is not None:
            normalized_path = str(source_path.resolve())
            try:
                stat = source_path.stat()
                size, mtime_ns = stat.st_size, stat.st_mtime_ns
            except OSError:
                pass
        return cls(
            captured_at_utc=datetime.now(timezone.utc).isoformat(),
            app_version=__version__,
            source_path=normalized_path,
            source_size=size,
            source_mtime_ns=mtime_ns,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "RecoveryMetadata":
        return cls(
            captured_at_utc=str(raw["captured_at_utc"]),
            app_version=str(raw.get("app_version", "")),
            source_path=str(raw["source_path"]) if raw.get("source_path") else None,
            source_size=int(raw["source_size"]) if raw.get("source_size") is not None else None,
            source_mtime_ns=(
                int(raw["source_mtime_ns"])
                if raw.get("source_mtime_ns") is not None
                else None
            ),
        )


@dataclass(slots=True)
class RecoveryInfo:
    project: TutorialProject
    metadata: RecoveryMetadata

    def source_is_unchanged(self) -> bool:
        if not self.metadata.source_path:
            return False
        try:
            stat = Path(self.metadata.source_path).stat()
        except OSError:
            return False
        return (
            self.metadata.source_size == stat.st_size
            and self.metadata.source_mtime_ns == stat.st_mtime_ns
        )


def recovery_directory() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Tutoriales Visuales" / "recovery"
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return Path(base) / "recovery"


def write_recovery_candidate(
    target: Path, project: TutorialProject, metadata: RecoveryMetadata
) -> Path:
    save_project(target, project)
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "recovery.json",
            json.dumps(asdict(metadata), ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return target


def read_recovery(path: Path) -> RecoveryInfo:
    try:
        project = load_project(path)
        with zipfile.ZipFile(path, "r") as archive:
            raw = json.loads(archive.read("recovery.json").decode("utf-8"))
        if not isinstance(raw, dict):
            raise InvalidRecoveryError("Los metadatos de recuperación son inválidos.")
        return RecoveryInfo(project, RecoveryMetadata.from_dict(raw))
    except InvalidRecoveryError:
        raise
    except (InvalidProjectError, KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise InvalidRecoveryError("La copia de recuperación no es válida.") from exc


class _RecoverySignals(QObject):
    finished = Signal(str, int, int, str)


class _RecoveryWriteJob(QRunnable):
    def __init__(
        self,
        candidate: Path,
        project: TutorialProject,
        metadata: RecoveryMetadata,
        generation: int,
        epoch: int,
    ) -> None:
        super().__init__()
        self.candidate = candidate
        self.project = project
        self.metadata = metadata
        self.generation = generation
        self.epoch = epoch
        self.signals = _RecoverySignals()

    def run(self) -> None:
        error = ""
        try:
            write_recovery_candidate(self.candidate, self.project, self.metadata)
        except Exception as exc:  # se informa al hilo principal sin cerrar el editor
            error = str(exc)
        self.signals.finished.emit(str(self.candidate), self.generation, self.epoch, error)


class RecoveryManager(QObject):
    writeFailed = Signal(str)
    recoveryWritten = Signal(str)

    def __init__(
        self,
        snapshot_provider: Callable[[], tuple[TutorialProject, Path | None]],
        parent: QObject | None = None,
        *,
        directory: Path | None = None,
        interval_ms: int = 10_000,
    ) -> None:
        super().__init__(parent)
        self.directory = directory or recovery_directory()
        self.active_path = self.directory / "active.tutorial"
        self.snapshot_provider = snapshot_provider
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._write_if_needed)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.generation = 0
        self.committed_generation = 0
        self.epoch = 0
        self.dirty = False
        self.writing = False
        self._jobs: set[_RecoveryWriteJob] = set()
        self._cleanup_candidates()

    def has_recovery(self) -> bool:
        return self.active_path.is_file()

    def inspect(self) -> RecoveryInfo:
        return read_recovery(self.active_path)

    def mark_dirty(self) -> None:
        self.dirty = True
        self.generation += 1
        if not self.timer.isActive():
            self.timer.start()

    def adopt_existing(self) -> None:
        self.dirty = True
        self.generation = 0
        self.committed_generation = 0
        self.timer.start()

    def clear(self) -> None:
        self.epoch += 1
        self.dirty = False
        self.generation = 0
        self.committed_generation = 0
        self.timer.stop()
        try:
            self.active_path.unlink(missing_ok=True)
        except OSError as exc:
            self.writeFailed.emit(f"No fue posible eliminar la recuperación: {exc}")

    def shutdown(self) -> None:
        self.clear()
        self.pool.waitForDone(5000)
        self._cleanup_candidates()

    def _write_if_needed(self) -> None:
        if not self.dirty or self.writing or self.generation == self.committed_generation:
            return
        try:
            project, source_path = self.snapshot_provider()
            snapshot = copy.deepcopy(project)
            metadata = RecoveryMetadata.capture(source_path)
            self.directory.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.writeFailed.emit(str(exc))
            return
        candidate = self.directory / f".candidate-{uuid4().hex}.tutorial"
        job = _RecoveryWriteJob(
            candidate, snapshot, metadata, self.generation, self.epoch
        )
        job.signals.finished.connect(self._write_finished)
        self._jobs.add(job)
        self.writing = True
        self.pool.start(job)

    def _write_finished(
        self, candidate_value: str, generation: int, epoch: int, error: str
    ) -> None:
        candidate = Path(candidate_value)
        self.writing = False
        self._jobs = {job for job in self._jobs if str(job.candidate) != candidate_value}
        if error:
            candidate.unlink(missing_ok=True)
            self.writeFailed.emit(error)
            return
        if epoch != self.epoch or not self.dirty:
            candidate.unlink(missing_ok=True)
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            os.replace(candidate, self.active_path)
        except OSError as exc:
            candidate.unlink(missing_ok=True)
            self.writeFailed.emit(str(exc))
            return
        self.committed_generation = generation
        self.recoveryWritten.emit(str(self.active_path))

    def _cleanup_candidates(self) -> None:
        if not self.directory.exists():
            return
        for candidate in self.directory.glob(".candidate-*.tutorial"):
            try:
                candidate.unlink()
            except OSError:
                pass
