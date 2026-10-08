"""Один проход ffmpeg: сборка аргументов, запуск, прогресс, отмена."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import limits
from .probe import VideoInfo
from .tools import popen, tool_path

# Режимы для видео длиннее 3 с
MODE_FIRST = "first"    # «Первые 3 секунды»
MODE_START = "start"    # «Начать с … с»
MODE_SPEED = "speed"    # «Ускорить до 3 секунд»
MODES = (MODE_FIRST, MODE_START, MODE_SPEED)

ProgressFn = Callable[[float], None]   # доля прохода 0..1


class Cancelled(Exception):
    pass


class EncodeError(Exception):
    def __init__(self, message: str, log_tail: str = ""):
        super().__init__(message)
        self.log_tail = log_tail


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass
class Plan:
    """Что делаем с файлом (не зависит от CRF)."""
    mode: str = MODE_FIRST
    start: float = 0.0          # для MODE_START, с

    def validate(self, info: VideoInfo) -> str | None:
        """Текст ошибки, если план нельзя выполнить для этого файла."""
        if self.mode not in MODES:
            return f"Неизвестный режим: {self.mode}"
        if self.mode == MODE_START and (self.start < 0 or self.start >= info.duration):
            return "Начало дальше конца видео"
        return None


def output_duration(info: VideoInfo, plan: Plan) -> float:
    if plan.mode == MODE_START:
        rest = info.duration - plan.start
    else:
        rest = info.duration
    return min(rest, limits.TARGET_DURATION)


def base_fps(info: VideoInfo) -> Fraction:
    """Выше 30 — до 30, иначе исходная."""
    return min(info.fps, Fraction(limits.MAX_FPS))


def build_args(
    info: VideoInfo, plan: Plan, dst: Path, crf: int, fps: Fraction
) -> list[str]:
    long = info.duration > limits.TARGET_DURATION
    args = [str(tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-y"]

    if long and plan.mode == MODE_START and plan.start > 0:
        args += ["-ss", f"{plan.start:.3f}"]
    # Для VP9 декодер задаём явно, иначе ffmpeg теряет альфу
    if info.codec == "vp9":
        args += ["-c:v", "libvpx-vp9"]
    args += ["-i", str(info.path)]

    filters = []
    if long and plan.mode == MODE_SPEED:
        filters.append(f"setpts=PTS*{limits.TARGET_DURATION}/{info.duration:.6f}")
    # fps после ускорения: приводит к постоянной частоте и не выше 30
    filters.append(f"fps={fps.numerator}/{fps.denominator}")
    filters.append(
        f"scale={limits.SIDE}:{limits.SIDE}"
        ":force_original_aspect_ratio=decrease:flags=lanczos"
    )

    pix_fmt = "yuva420p" if info.has_alpha else "yuv420p"
    args += [
        "-map", "0:v:0",
        "-t", f"{limits.TARGET_DURATION}",
        "-an", "-sn", "-dn",
        "-map_metadata", "-1",
        "-vf", ",".join(filters),
        "-c:v", "libvpx-vp9",
        "-crf", str(crf), "-b:v", "0",
        "-row-mt", "1",
        "-pix_fmt", pix_fmt,
        "-f", "webm",
        "-progress", "pipe:1", "-nostats",
        str(dst),
    ]
    return args


def run_ffmpeg(
    args: list[str],
    duration: float,
    cancel: CancelToken | None = None,
    progress: ProgressFn | None = None,
) -> None:
    """Запускает ffmpeg и ждёт. Бросает Cancelled или EncodeError."""
    try:
        proc = popen(args)
    except OSError as e:
        raise EncodeError("Не удалось запустить ffmpeg", str(e)) from e

    tail: deque[str] = deque(maxlen=12)

    def read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                tail.append(line)

    err_thread = threading.Thread(target=read_stderr, daemon=True)
    err_thread.start()

    # Отмена: отдельный сторож убивает процесс, не дожидаясь строк прогресса
    done = threading.Event()

    def watch_cancel() -> None:
        while not done.wait(0.1):
            if cancel is not None and cancel.cancelled:
                proc.kill()
                return

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if progress is None or not line.startswith("out_time_us="):
                continue
            try:
                us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if duration > 0:
                progress(max(0.0, min(1.0, us / 1e6 / duration)))
        proc.wait()
    finally:
        done.set()
        err_thread.join(timeout=2)

    if cancel is not None and cancel.cancelled:
        raise Cancelled()
    if proc.returncode != 0:
        raise EncodeError("Ошибка ffmpeg", "\n".join(tail))
    if progress is not None:
        progress(1.0)
