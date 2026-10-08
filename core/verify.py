"""Проверка готового файла по требованиям Telegram."""

from __future__ import annotations

from pathlib import Path

from . import limits
from .probe import ProbeError, probe


def check_sticker(path: Path, need_alpha: bool = False) -> list[str]:
    """Список нарушений (пустой — всё в порядке)."""
    try:
        info = probe(path)
    except ProbeError:
        return ["готовый файл не читается"]

    problems = []
    if "webm" not in info.format_name.split(","):
        problems.append(f"контейнер {info.format_name}, а нужен WebM")
    if info.codec != "vp9":
        problems.append(f"кодек {info.codec}, а нужен VP9")
    side = limits.SIDE
    if max(info.width, info.height) != side or min(info.width, info.height) > side:
        problems.append(f"размер {info.width}×{info.height}, а нужна сторона {side}")
    if info.duration > limits.MAX_DURATION:
        problems.append(f"длительность {info.duration:.2f} с больше {limits.MAX_DURATION:g} с")
    if info.fps_float > limits.MAX_FPS + 0.01:
        problems.append(f"{info.fps_float:.2f} кадров/с больше {limits.MAX_FPS}")
    if info.has_audio:
        problems.append("есть звук")
    size = path.stat().st_size
    if size > limits.MAX_BYTES:
        problems.append(f"размер {size // 1024} КБ больше {limits.MAX_BYTES // 1024} КБ")
    if need_alpha and not info.has_alpha:
        problems.append("пропала прозрачность")
    return problems
