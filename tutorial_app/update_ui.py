from __future__ import annotations

import json
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QMessageBox, QPushButton

from . import updater


class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class Worker(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.done.emit(self.operation(self.signals.progress.emit))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.busy = False
        self.info = None
        self.installer = None
        self.manual = False
        self.worker = None
        self.button = QPushButton("Actualizar y reiniciar", window)
        self.button.clicked.connect(self.offer_install)
        self.button.hide()
        window.statusBar().addPermanentWidget(self.button)
        action = QAction("Buscar actualizaciones", window)
        action.triggered.connect(lambda: self.check(True))
        window.menuBar().addMenu("&Ayuda").addAction(action)
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        if updater.distribution() != "source":
            self.timer.start()
            QTimer.singleShot(5000, self.check)
            QTimer.singleShot(1000, self.show_result)

    def show_result(self):
        path = updater.update_directory() / "result.json"
        if path.exists():
            try:
                result = json.loads(path.read_text(encoding="utf-8-sig"))
                path.unlink()
                if result["success"]:
                    self.window.statusBar().showMessage(result["message"], 15000)
                else:
                    QMessageBox.warning(self.window, "Actualización", result["message"])
            except (OSError, ValueError, KeyError):
                pass

    def run_worker(self, operation, done):
        self.busy = True
        self.worker = Worker(operation)
        self.worker.signals.done.connect(done)
        self.worker.signals.failed.connect(self.failed)
        self.worker.signals.progress.connect(self.progress)
        QThreadPool.globalInstance().start(self.worker)

    def progress(self, value):
        self.window.statusBar().showMessage(f"Descargando actualización: {value}%")

    def check(self, manual=False):
        if self.busy:
            if manual:
                self.window.statusBar().showMessage("Ya se está buscando o descargando una actualización.", 5000)
            return
        self.manual = manual
        if self.installer:
            self.offer_install()
            return
        self.run_worker(lambda _: updater.find_update(), self.found)

    def found(self, info):
        self.busy = False
        if info is None:
            if self.manual:
                QMessageBox.information(self.window, "Actualizaciones", "Ya tienes la última versión estable.")
            return
        self.info = info
        if updater.distribution() != "installed":
            box = QMessageBox(self.window)
            box.setWindowTitle("Nueva versión disponible")
            box.setText(f"Está disponible v.{info['version']}. Puedes descargarla desde GitHub.")
            download = box.addButton("Descargar versión", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == download:
                QDesktopServices.openUrl(QUrl(updater.RELEASES))
            return
        self.run_worker(lambda progress: updater.download_update(info, progress), self.downloaded)

    def downloaded(self, path):
        self.busy = False
        self.installer = path
        self.button.show()
        self.offer_install()

    def failed(self, message):
        self.busy = False
        self.window.statusBar().showMessage(f"No se pudo comprobar o descargar la actualización: {message}", 10000)
        if self.manual:
            QMessageBox.warning(self.window, "Actualizaciones", message)

    def offer_install(self):
        if not self.installer:
            return
        box = QMessageBox(self.window)
        box.setWindowTitle("Actualización lista")
        box.setText(f"v.{self.info['version']} está lista. Podrás guardar los cambios antes de reiniciar.")
        install = box.addButton("Actualizar y reiniciar", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == install:
            self.window._pending_update = (self.installer, self.info)
            self.window.close()
