"""Запуск ядра из командной строки: python -m core видео.mp4 [ещё файлы] [-o папка]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import limits
from .convert import ConvertError, check_writable, convert_file, fmt_fps
from .encode import MODES, Plan
from .probe import ProbeError, probe, target_size
from .tools import ToolsMissing, check_tools


def main(argv: list[str] | None = None) -> int:
    # Консоль Windows: печатаем по-русски без ошибок кодировки
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="python -m core", description="Видео → стикер Telegram (.webm)")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("-o", "--out", type=Path, help="папка сохранения (по умолчанию — папка исходника)")
    p.add_argument("--mode", choices=MODES, default="first",
                   help="для видео длиннее 3 с: first — первые 3 с, start — с момента --start, speed — ускорить")
    p.add_argument("--start", type=float, default=0.0, help="начало в секундах для --mode start")
    p.add_argument("--info", action="store_true", help="только показать параметры файлов")
    a = p.parse_args(argv)

    try:
        check_tools()
    except ToolsMissing as e:
        print(e, file=sys.stderr)
        return 2

    plan = Plan(a.mode, a.start)
    failed = 0
    for src in a.files:
        print(f"{src.name}")
        try:
            info = probe(src)
        except ProbeError as e:
            print(f"  {e}")
            failed += 1
            continue
        w, h = target_size(info.width, info.height)
        print(f"  {info.duration:.2f} с, {fmt_fps(info.fps)} fps{' (переменная)' if info.vfr else ''}, "
              f"{info.codec}/{info.pix_fmt}, {'прозрачность, ' if info.has_alpha else ''}"
              f"{'звук, ' if info.has_audio else ''}{info.width}×{info.height} → {w}×{h}"
              + (f", поворот {info.rotation}°" if info.rotation else ""))
        if a.info:
            continue

        out_dir = a.out or src.parent
        err = check_writable(out_dir)
        if err:
            print(f"  {err}")
            failed += 1
            continue
        try:
            r = convert_file(src, out_dir, plan, log=print, info=info)
        except ConvertError as e:
            print(f"  {e}")
            if e.log_tail:
                print("  " + e.log_tail.replace("\n", "\n  "))
            failed += 1
            continue
        extra = f", {fmt_fps(r.fps)} fps" if r.fps_reduced else ""
        print(f"  Готово, {r.size / 1024:.0f} КБ{extra} (CRF {r.crf}) → {r.path}")
        if r.size > limits.MAX_BYTES:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
