"""Главное окно: перетаскивание, список файлов, папка сохранения, конвертация."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core import limits
from core.convert import Result, check_writable, fmt_fps
from ui.file_row import DONE, ERROR, PROCESSING, QUEUED, FileRow
from ui.workers import ConvertThread, Job, Prober

SETTINGS_OUT_DIR = "out_dir"


def _video_paths(urls_or_paths) -> list[Path]:
    """Только файлы с поддерживаемыми расширениями."""
    result = []
    for p in urls_or_paths:
        path = Path(p)
        if path.is_file() and path.suffix.lower() in limits.INPUT_EXTENSIONS:
            result.append(path)
    return result


class DropZone(QFrame):
    def __init__(self, on_add) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setStyleSheet(
            # Цвета из палитры системы — подходят и для светлой, и для тёмной темы
            "#dropZone { border: 2px dashed #8a94a0; border-radius: 10px;"
            " background: palette(alternate-base); }"
            "#dropZone[hover=\"true\"] { border-color: palette(highlight); }"
        )
        title = QLabel("Перетащите видео сюда")
        title.setStyleSheet("font-size: 16px; font-weight: 600; border: none; background: transparent;")
        hint = QLabel("mp4, mov, mkv, webm, avi, gif — можно несколько файлов")
        hint.setStyleSheet("color: #8a94a0; border: none; background: transparent;")
        button = QPushButton("Добавить файлы")
        button.clicked.connect(on_add)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 18, 16, 18)
        for w in (title, hint):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(w)
        lay.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)

    def set_hover(self, on: bool) -> None:
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StickerMaker — видео в стикер Telegram")
        self.resize(760, 640)
        self.setAcceptDrops(True)

        self.settings = QSettings("StickerMaker", "StickerMaker")
        self.rows: list[FileRow] = []
        self.thread: ConvertThread | None = None
        self.last_folder: Path | None = None
        self.total = 0
        self.finished_count = 0

        self.prober = Prober()
        self.prober.probed.connect(self._probed)
        self.prober.failed.connect(self._probe_failed)

        # Зона перетаскивания
        self.drop = DropZone(self._add_dialog)

        # Список файлов
        self.list_box = QWidget()
        self.list_lay = QVBoxLayout(self.list_box)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(6)
        self.empty = QLabel("Список пуст")
        self.empty.setStyleSheet("color: #8a94a0;")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_lay.addWidget(self.empty)
        self.list_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.list_box)

        # Папка сохранения
        self.out_edit = QLineEdit(self.settings.value(SETTINGS_OUT_DIR, "", str))
        self.out_edit.setPlaceholderText("Та же папка, что у исходника")
        self.out_edit.editingFinished.connect(self._save_out_dir)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Папка сохранения:"))
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(browse)

        # Кнопки и прогресс
        self.convert_btn = QPushButton("Конвертировать")
        self.convert_btn.setStyleSheet("font-weight: 600; padding: 6px 18px;")
        self.convert_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        self.open_btn = QPushButton("Открыть папку")
        self.open_btn.clicked.connect(self._open_folder)
        self.open_btn.hide()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFormat("")
        self.progress.setTextVisible(True)
        bottom = QHBoxLayout()
        bottom.addWidget(self.convert_btn)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(self.open_btn)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(self.drop)
        lay.addWidget(scroll, 1)
        lay.addLayout(out_row)
        lay.addLayout(bottom)
        self.setCentralWidget(central)
        self._update_buttons()

    # --- добавление файлов ---

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls() and not self._busy():
            e.acceptProposedAction()
            self.drop.set_hover(True)

    def dragLeaveEvent(self, e) -> None:
        self.drop.set_hover(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self.drop.set_hover(False)
        self.add_files(_video_paths(u.toLocalFile() for u in e.mimeData().urls()))

    def _add_dialog(self) -> None:
        if self._busy():
            return
        exts = " ".join("*" + x for x in limits.INPUT_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, "Добавить видео", "", f"Видео ({exts})")
        self.add_files(_video_paths(files))

    def add_files(self, paths: list[Path]) -> None:
        known = {r.path.resolve() for r in self.rows}
        for path in _video_paths(paths):
            if path.resolve() in known:
                continue
            known.add(path.resolve())
            row = FileRow(path)
            row.remove_requested.connect(self._remove_row)
            row.changed.connect(self._update_buttons)
            self.rows.append(row)
            self.list_lay.insertWidget(self.list_lay.count() - 1, row)
            self.prober.submit(row, path)
        self.open_btn.hide()
        self._update_buttons()

    def _probed(self, row: FileRow, info) -> None:
        if row in self.rows:
            row.set_info(info)
            self._update_buttons()

    def _probe_failed(self, row: FileRow, message: str) -> None:
        if row in self.rows:
            row.set_unreadable(message)
            self._update_buttons()

    def _remove_row(self, row: FileRow) -> None:
        if self._busy():
            return
        self.rows.remove(row)
        row.deleteLater()
        self._update_buttons()

    # --- папка сохранения ---

    def _browse(self) -> None:
        start = self.out_edit.text() or (str(self.rows[0].path.parent) if self.rows else "")
        folder = QFileDialog.getExistingDirectory(self, "Папка сохранения", start)
        if folder:
            self.out_edit.setText(str(Path(folder)))
            self._save_out_dir()

    def _save_out_dir(self) -> None:
        self.settings.setValue(SETTINGS_OUT_DIR, self.out_edit.text().strip())

    def _out_dir_for(self, src: Path) -> Path:
        text = self.out_edit.text().strip()
        return Path(text) if text else src.parent

    # --- конвертация ---

    def _busy(self) -> bool:
        return self.thread is not None

    def _ready_rows(self) -> list[FileRow]:
        return [r for r in self.rows if r.state == QUEUED and not r.start_invalid()]

    def _start(self) -> None:
        rows = self._ready_rows()
        if not rows:
            return
        # Права на запись проверяем до начала
        folders = {self._out_dir_for(r.path) for r in rows}
        problems = [p for p in (check_writable(f) for f in sorted(folders)) if p]
        if problems:
            QMessageBox.warning(self, "Нельзя сохранить", "\n".join(problems))
            return

        jobs = [Job(r, r.path, self._out_dir_for(r.path), r.plan(), r.info) for r in rows]
        self.total = len(jobs)
        self.finished_count = 0
        self.last_folder = None
        self.thread = ConvertThread(jobs)
        self.thread.file_started.connect(self._file_started)
        self.thread.file_progress.connect(self._file_progress)
        self.thread.file_done.connect(self._file_done)
        self.thread.file_failed.connect(self._file_failed)
        self.thread.file_cancelled.connect(self._file_cancelled)
        self.thread.finished.connect(self._thread_finished)
        for r in self.rows:
            r.set_editable(False)
        self.open_btn.hide()
        self._set_overall(0.0)
        self.thread.start()
        self._update_buttons()

    def _cancel(self) -> None:
        if self.thread:
            self.thread.cancel()
            self.cancel_btn.setEnabled(False)

    def _file_started(self, row: FileRow) -> None:
        row.set_state(PROCESSING)
        row.set_progress(0.0)

    def _file_progress(self, row: FileRow, frac: float) -> None:
        row.set_progress(frac)
        self._set_overall((self.finished_count + frac) / max(1, self.total))

    def _file_done(self, row: FileRow, r: Result) -> None:
        text = f"Готово, {r.size / 1024:.0f} КБ"
        if r.fps_reduced:
            text += f", {fmt_fps(r.fps)} fps"
        row.set_state(DONE, text, str(r.path))
        self.last_folder = r.path.parent
        self._file_finished()

    def _file_failed(self, row: FileRow, message: str, log_tail: str) -> None:
        if not message.startswith(("Ошибка", "Не удалось")):
            message = f"Ошибка: {message}"
        row.set_state(ERROR, message, log_tail or message)
        self._file_finished()

    def _file_cancelled(self, row: FileRow) -> None:
        row.set_state(QUEUED)

    def _file_finished(self) -> None:
        self.finished_count += 1
        self._set_overall(self.finished_count / max(1, self.total))

    def _thread_finished(self) -> None:
        thread, self.thread = self.thread, None
        if thread:
            thread.deleteLater()
        for r in self.rows:
            r.set_editable(True)
            if r.state == PROCESSING:
                r.set_state(QUEUED)
        done = sum(1 for r in self.rows if r.state == DONE)
        errors = sum(1 for r in self.rows if r.state == ERROR)
        self.progress.setFormat(f"Готово: {done}" + (f", ошибок: {errors}" if errors else ""))
        if self.last_folder:
            self.open_btn.show()
        self._update_buttons()

    def _set_overall(self, frac: float) -> None:
        self.progress.setValue(int(frac * 1000))
        self.progress.setFormat(f"{int(frac * 100)}%")

    def _open_folder(self) -> None:
        if self.last_folder and self.last_folder.is_dir():
            os.startfile(self.last_folder)  # type: ignore[attr-defined]

    def _update_buttons(self) -> None:
        busy = self._busy()
        self.convert_btn.setEnabled(not busy and bool(self._ready_rows()))
        self.cancel_btn.setEnabled(busy)
        self.drop.setEnabled(not busy)
        self.empty.setVisible(not self.rows)

    # --- закрытие окна = отмена ---

    def closeEvent(self, e: QCloseEvent) -> None:
        if self.thread:
            self.thread.cancel()
            self.thread.wait(10_000)
        self.prober.shutdown()
        self._save_out_dir()
        e.accept()
