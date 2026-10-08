"""Создаёт тестовые видео для критериев приёмки в tests/samples (генераторы ffmpeg)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.tools import tool_path  # noqa: E402

OUT = ROOT / "tests" / "samples"
FF = str(tool_path("ffmpeg"))


def ff(*args: str) -> None:
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def lavfi(src: str) -> list[str]:
    return ["-f", "lavfi", "-i", src]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]

    # 1. mp4 1920×1080, 10 с, со звуком
    ff(*lavfi("testsrc2=s=1920x1080:r=30:d=10"), *lavfi("sine=f=440:d=10"),
       *h264, "-c:a", "aac", "-shortest", str(OUT / "hd_10s_audio.mp4"))

    # 2. Телефон: 1920×1080 с поворотом 90° в метаданных
    tmp = OUT / "_landscape.mp4"
    ff(*lavfi("testsrc2=s=1920x1080:r=30:d=2"), *h264, str(tmp))
    ff("-display_rotation", "90", "-i", str(tmp), "-c", "copy", str(OUT / "phone_rotated.mp4"))
    tmp.unlink()

    # 3. Маленькое 300×200
    ff(*lavfi("testsrc2=s=300x200:r=25:d=2"), *h264, str(OUT / "small_300x200.mp4"))

    # 4. 60 fps
    ff(*lavfi("testsrc2=s=1280x720:r=60:d=2"), *h264, str(OUT / "fps60.mp4"))

    # 5. ProRes 4444 с полупрозрачным фоном
    ff(*lavfi("testsrc2=s=1280x720:r=30:d=2,format=rgba,colorchannelmixer=aa=0.4"),
       "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
       str(OUT / "prores4444_alpha.mov"))

    # 6. WebM VP9 с альфой на входе
    ff(*lavfi("testsrc2=s=640x640:r=30:d=2,format=rgba,colorchannelmixer=aa=0.4"),
       "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "1M", str(OUT / "vp9_alpha.webm"))

    # 7. Динамичное: шум, при CRF 30 больше 256 КБ
    ff(*lavfi("testsrc2=s=1280x720:r=30:d=3,noise=alls=40:allf=t+u"), *h264, "-crf", "10",
       str(OUT / "dynamic_noise.mp4"))

    # 8. Битый файл
    (OUT / "broken.mp4").write_bytes(os.urandom(50_000))

    # 9. Кириллица, пробелы и скобки в пути
    cyr = OUT / "тест папка (1)"
    cyr.mkdir(exist_ok=True)
    ff(*lavfi("testsrc2=s=800x600:r=24:d=2"), *h264, str(cyr / "видео пример (копия).mp4"))

    # 10. GIF и переменная частота кадров
    ff(*lavfi("testsrc2=s=480x270:r=15:d=2"), str(OUT / "anim.gif"))
    ff(*lavfi("testsrc2=s=480x270:r=15:d=2"), "-vf",
       "format=rgba,colorkey=0x000000:0.3,split[a][b];[a]palettegen=reserve_transparent=1[p];"
       "[b][p]paletteuse=alpha_threshold=128", str(OUT / "anim_transparent.gif"))
    ff(*lavfi("testsrc2=s=1280x720:r=30:d=4"), "-vf", "setpts='PTS+0.02*sin(N)/TB'",
       "-fps_mode", "vfr", *h264, str(OUT / "vfr.mp4"))

    print("Готово:", OUT)


if __name__ == "__main__":
    main()
