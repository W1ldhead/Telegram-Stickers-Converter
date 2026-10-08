"""Полная обработка одного файла: анализ → подгонка CRF под 256 КБ → проверка → сохранение."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import limits
from .encode import (
    CancelToken, EncodeError, Plan, base_fps, build_args, output_duration, run_ffmpeg,
)
from .probe import ProbeError, VideoInfo, probe, target_size
from .verify import check_sticker

ProgressFn = Callable[[float], None]
LogFn = Callable[[str], None]

# Столько проходов занимает двоичный поиск CRF 15–63 — для оценки прогресса
_PASSES_PER_SEARCH = 6


class ConvertError(Exception):
    def __init__(self, message: str, log_tail: str = ""):
        super().__init__(message)
        self.log_tail = log_tail


@dataclass
class Result:
    path: Path
    size: int
    crf: int
    fps: Fraction
    fps_reduced: bool       # частоту пришлось снизить ради размера
    width: int
    height: int


def output_path(src: Path, out_dir: Path) -> Path:
    """<имя>_sticker.webm, при совпадении _2, _3 …; существующие не трогаем."""
    stem = src.stem + limits.OUTPUT_SUFFIX
    candidate = out_dir / f"{stem}.webm"
    n = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_{n}.webm"
        n += 1
    return candidate


def check_writable(folder: Path) -> str | None:
    """Текст ошибки, если в папку нельзя писать."""
    if not folder.is_dir():
        return f"Папка не существует: {folder}"
    try:
        fd, name = tempfile.mkstemp(prefix=".stickermaker_", dir=folder)
        os.close(fd)
        os.remove(name)
    except OSError:
        return f"Нет прав на запись в папку: {folder}"
    return None


def fmt_fps(fps: Fraction) -> str:
    v = float(fps)
    return f"{v:.0f}" if abs(v - round(v)) < 0.01 else f"{v:.2f}"


def convert_file(
    src: str | Path,
    out_dir: str | Path,
    plan: Plan | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn | None = None,
    log: LogFn | None = None,
    info: VideoInfo | None = None,
) -> Result:
    """Бросает ConvertError (понятный текст) или encode.Cancelled."""
    src, out_dir = Path(src), Path(out_dir)
    plan = plan or Plan()
    say = log or (lambda _msg: None)

    if info is None:
        try:
            info = probe(src)
        except ProbeError as e:
            raise ConvertError(str(e)) from e
    problem = plan.validate(info)
    if problem:
        raise ConvertError(problem)

    duration = output_duration(info, plan)
    start_fps = base_fps(info)
    fps_steps = [start_fps] + [Fraction(f) for f in limits.FALLBACK_FPS if f < start_fps]

    tmp = Path(tempfile.mkdtemp(prefix="stickermaker_"))
    passes_done = 0

    def encode(crf: int, fps: Fraction) -> Path:
        nonlocal passes_done
        dst = tmp / f"crf{crf}_fps{fps.numerator}_{fps.denominator}.webm"
        args = build_args(info, plan, dst, crf, fps)

        def part(frac: float) -> None:
            if progress:
                progress(min(0.99, (passes_done + frac) / _PASSES_PER_SEARCH))

        try:
            run_ffmpeg(args, duration, cancel, part)
        except EncodeError as e:
            raise ConvertError("Ошибка ffmpeg", e.log_tail) from e
        passes_done += 1
        return dst

    try:
        best: tuple[int, Path, int, Fraction] | None = None   # crf, файл, размер, fps
        smallest = None                                         # лучший размер, если не влезло
        for fps in fps_steps:
            lo, hi, crf = limits.CRF_MIN, limits.CRF_MAX, limits.CRF_FIRST
            # Двоичный поиск наименьшего CRF, при котором файл в лимите
            while lo <= hi:
                path = encode(crf, fps)
                size = path.stat().st_size
                fits = size <= limits.TARGET_BYTES
                say(f"  CRF {crf}, {fmt_fps(fps)} fps → {size / 1024:.0f} КБ"
                    + ("" if fits else " (не влезает)"))
                if smallest is None or size < smallest:
                    smallest = size
                if fits:
                    best = (crf, path, size, fps)
                    hi = crf - 1
                else:
                    lo = crf + 1
                crf = (lo + hi) // 2
            if best:
                break

        if best is None:
            kb = (smallest or 0) / 1024
            raise ConvertError(f"Ошибка: не укладывается в 256 КБ (лучшее — {kb:.0f} КБ)")

        crf, path, size, fps = best
        problems = check_sticker(path, need_alpha=info.has_alpha)
        if problems:
            raise ConvertError("Ошибка: " + "; ".join(problems))

        out_dir.mkdir(parents=True, exist_ok=True)
        dst = output_path(src, out_dir)
        try:
            shutil.move(str(path), str(dst))
        except OSError as e:
            raise ConvertError(f"Не удалось сохранить файл: {e}") from e

        w, h = target_size(info.width, info.height)
        if progress:
            progress(1.0)
        return Result(dst, size, crf, fps, fps != start_fps, w, h)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
