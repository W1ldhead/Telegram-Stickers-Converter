"""Поиск ffmpeg/ffprobe и запуск процессов без консольного окна."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# На Windows прячем консольное окно дочерних процессов
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ToolsMissing(Exception):
    pass


def base_dir() -> Path:
    """Папка программы: распакованный exe (PyInstaller) или корень исходников."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def tool_path(name: str) -> Path:
    exe = name + (".exe" if os.name == "nt" else "")
    return base_dir() / "bin" / exe


def check_tools() -> None:
    """Бросает ToolsMissing, если ffmpeg или ffprobe нет в bin/."""
    missing = [n for n in ("ffmpeg", "ffprobe") if not tool_path(n).is_file()]
    if missing:
        names = ", ".join(n + ".exe" for n in missing)
        raise ToolsMissing(f"Не найдены {names} в папке {base_dir() / 'bin'}")


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Короткий вызов (ffprobe): ждём завершения, вывод целиком."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def popen(args: list[str]) -> subprocess.Popen[str]:
    """Долгий вызов (ffmpeg): прогресс в stdout, журнал в stderr."""
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
