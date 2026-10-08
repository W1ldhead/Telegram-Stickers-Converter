"""Анализ видео через ffprobe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from . import limits
from .tools import run, tool_path


class ProbeError(Exception):
    pass


# Форматы пикселей с альфа-каналом (по названию: yuva*, rgba, bgra, gbrap, ya8 и т. п.)
_ALPHA_MARKERS = ("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya8", "ya16")


def pix_fmt_has_alpha(pix_fmt: str) -> bool:
    p = pix_fmt.lower()
    return any(m in p for m in _ALPHA_MARKERS)


@dataclass
class VideoInfo:
    path: Path
    width: int            # с учётом поворота
    height: int
    duration: float       # с
    fps: Fraction         # средняя частота кадров
    vfr: bool             # переменная частота кадров
    codec: str
    pix_fmt: str
    has_audio: bool
    has_alpha: bool
    rotation: int         # градусы из метаданных
    format_name: str
    size_bytes: int

    @property
    def fps_float(self) -> float:
        return float(self.fps)


def _fraction(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "N/A"):
        return None
    try:
        f = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def _float(text) -> float | None:
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                return int(round(float(sd["rotation"])))
            except (TypeError, ValueError):
                pass
    tags = {k.lower(): v for k, v in (stream.get("tags") or {}).items()}
    try:
        return int(tags.get("rotate", 0))
    except ValueError:
        return 0


def _gif_has_transparency(path: Path) -> bool:
    """Минимум альфа-канала по всем кадрам меньше 255 → есть прозрачность."""
    args = [
        str(tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-i", str(path),
        "-vf", "alphaextract,signalstats,metadata=print:key=lavfi.signalstats.YMIN:file=-",
        "-f", "null", "-",
    ]
    try:
        res = run(args, timeout=60)
    except Exception:  # noqa: BLE001 — не смогли проверить: считаем прозрачным, так надёжнее
        return True
    mins = [float(line.split("=", 1)[1]) for line in res.stdout.splitlines()
            if line.startswith("lavfi.signalstats.YMIN=")]
    return not mins or min(mins) < 255


def probe(path: str | Path) -> VideoInfo:
    path = Path(path)
    args = [
        str(tool_path("ffprobe")), "-v", "error",
        "-show_streams", "-show_format", "-of", "json", str(path),
    ]
    try:
        res = run(args, timeout=60)
    except Exception as e:  # noqa: BLE001 — любая ошибка запуска = файл не прочитан
        raise ProbeError("Не удалось прочитать файл") from e
    if res.returncode != 0:
        raise ProbeError("Не удалось прочитать файл")
    try:
        data = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as e:
        raise ProbeError("Не удалось прочитать файл") from e

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    # Первая настоящая видеодорожка (обложки mp3/mp4 — attached_pic — пропускаем)
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video"
         and not (s.get("disposition") or {}).get("attached_pic")),
        None,
    )
    if video is None or not video.get("width") or not video.get("height"):
        raise ProbeError("Не удалось прочитать файл")

    w, h = int(video["width"]), int(video["height"])
    rotation = _rotation(video)
    if abs(rotation) % 180 == 90:
        w, h = h, w

    duration = _float(fmt.get("duration")) or _float(video.get("duration"))
    if duration is None:
        raise ProbeError("Не удалось прочитать файл: неизвестна длительность")

    avg = _fraction(video.get("avg_frame_rate"))
    real = _fraction(video.get("r_frame_rate"))
    fps = avg or real
    if fps is None:
        raise ProbeError("Не удалось прочитать файл: неизвестна частота кадров")
    # Переменная частота: заявленная и средняя заметно расходятся
    vfr = bool(avg and real and abs(float(avg) - float(real)) > 0.01 * float(real))

    tags = {k.lower(): str(v) for k, v in (video.get("tags") or {}).items()}
    pix_fmt = video.get("pix_fmt") or ""
    # У WebM VP9 альфа хранится отдельно и видна только по тегу alpha_mode
    has_alpha = pix_fmt_has_alpha(pix_fmt) or tags.get("alpha_mode") == "1"
    # GIF всегда декодируется в bgra — смотрим, есть ли реально прозрачные пиксели
    if has_alpha and video.get("codec_name") == "gif":
        has_alpha = _gif_has_transparency(path)

    return VideoInfo(
        path=path,
        width=w,
        height=h,
        duration=duration,
        fps=fps,
        vfr=vfr,
        codec=video.get("codec_name") or "",
        pix_fmt=pix_fmt,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        has_alpha=has_alpha,
        rotation=rotation,
        format_name=fmt.get("format_name") or "",
        size_bytes=int(fmt.get("size") or path.stat().st_size),
    )


def target_size(width: int, height: int) -> tuple[int, int]:
    """Размер после scale=512:512:force_original_aspect_ratio=decrease (как считает ffmpeg)."""
    side = limits.SIDE
    if width >= height:
        return side, max(1, int(height * side / width + 0.5))
    return max(1, int(width * side / height + 0.5)), side
