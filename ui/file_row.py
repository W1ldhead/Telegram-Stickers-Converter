"""Строка списка файлов: параметры, режим для длинного видео, статус, удаление."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from core import limits
from core.encode import MODE_FIRST, MODE_SPEED, MODE_START, Plan
from core.convert import fmt_fps
from core.probe import VideoInfo, target_size

# Состояния строки
PROBING = "probing"
QUEUED = "queued"
PROCESSING = "processing"
DONE = "done"
ERROR = "error"
UNREADABLE = "unreadable"

_MODES = [
    (MODE_FIRST, "Первые 3 секунды"),
    (MODE_START, "Начать с … с"),
    (MODE_SPEED, "Ускорить до 3 секунд"),
]

_COLORS = {DONE: "#2e9d4a", ERROR: "#e53935", UNREADABLE: "#e53935", PROCESSING: "#3d8bfd"}


def num(x: float, digits: int = 1) -> str:
    """Число с запятой: 3,2."""
    return f"{x:.{digits}f}".replace(".", ",")


class FileRow(QFrame):
    remove_requested = Signal(object)    # self
    changed = Signal()                   # поменялся режим или начало

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.info: VideoInfo | None = None
        self.state = PROBING
        self.setObjectName("fileRow")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.name = QLabel(path.name)
        self.name.setStyleSheet("font-weight: 600;")
        self.name.setToolTip(str(path))
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.details = QLabel("Анализ…")
        self.details.setStyleSheet("color: #8a94a0;")
        self.details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status.setMinimumWidth(170)

        self.remove_btn = QToolButton()
        self.remove_btn.setText("✕")
        self.remove_btn.setToolTip("Убрать из списка")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        # Выбор для видео длиннее 3 с
        self.mode = QComboBox()
        for key, text in _MODES:
            self.mode.addItem(text, key)
        self.start = QDoubleSpinBox()
        self.start.setDecimals(1)
        self.start.setSingleStep(0.5)
        self.start.setSuffix(" с")
        self.start.setMaximum(1e6)
        self.start_label = QLabel("Начать с")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.start.valueChanged.connect(self._start_changed)

        self.long_box = QWidget()
        lb = QHBoxLayout(self.long_box)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.addWidget(QLabel("Длиннее 3 с:"))
        lb.addWidget(self.mode)
        lb.addWidget(self.start_label)
        lb.addWidget(self.start)
        lb.addStretch(1)
        self.long_box.hide()

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.name)
        text.addWidget(self.details)
        text.addWidget(self.long_box)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 6, 6)
        row.addLayout(text, 1)
        row.addWidget(self.status)
        row.addWidget(self.remove_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._mode_changed()

    # --- данные ---

    def set_info(self, info: VideoInfo) -> None:
        self.info = info
        w, h = target_size(info.width, info.height)
        parts = [f"{num(info.duration)} с", f"{fmt_fps(info.fps).replace('.', ',')} fps"]
        if info.has_alpha:
            parts.append("прозрачность")
        parts.append(f"{info.width}×{info.height} → {w}×{h}")
        self.details.setText(" · ".join(parts))
        if info.duration > limits.TARGET_DURATION:
            self.start.setMaximum(max(0.0, info.duration))
            self.long_box.show()
        self.set_state(QUEUED)
        self._validate()

    def set_unreadable(self, message: str) -> None:
        self.details.setText("")
        self.set_state(UNREADABLE, message)

    def plan(self) -> Plan:
        return Plan(self.mode.currentData(), self.start.value())

    def start_invalid(self) -> bool:
        """«Начать с» не раньше конца видео — файл не конвертируется."""
        if self.info is None or not self.is_long():
            return False
        return self.plan().validate(self.info) is not None

    def is_long(self) -> bool:
        return self.info is not None and self.info.duration > limits.TARGET_DURATION

    # --- вид ---

    def set_state(self, state: str, text: str = "", tooltip: str = "") -> None:
        self.state = state
        default = {
            PROBING: "Анализ…", QUEUED: "В очереди", PROCESSING: "Обработка",
            DONE: "Готово", ERROR: "Ошибка", UNREADABLE: "Не удалось прочитать файл",
        }[state]
        self.status.setText(text or default)
        self.status.setToolTip(tooltip)
        color = _COLORS.get(state)
        self.status.setStyleSheet(f"color: {color};" if color else "")

    def set_progress(self, frac: float) -> None:
        self.status.setText(f"Обработка {int(frac * 100)}%")

    def set_editable(self, on: bool) -> None:
        self.remove_btn.setEnabled(on)
        self.mode.setEnabled(on)
        self.start.setEnabled(on)

    def _mode_changed(self) -> None:
        on = self.mode.currentData() == MODE_START
        self.start.setVisible(on)
        self.start_label.setVisible(on)
        self._options_changed()

    def _start_changed(self) -> None:
        self._options_changed()

    def _options_changed(self) -> None:
        # Новые настройки — готовый файл можно сделать заново
        if self.state in (DONE, ERROR):
            self.set_state(QUEUED)
        self._validate()
        self.changed.emit()

    def _validate(self) -> None:
        bad = self.start_invalid()
        self.start.setStyleSheet("border: 2px solid #e53935;" if bad else "")
        self.start.setToolTip("Начало дальше конца видео" if bad else "")
