"""Скачивает ffmpeg (BtbN, LGPL, shared) в bin/ и проверяет наличие libvpx-vp9."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
       "ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip")


def main() -> int:
    bin_dir = ROOT / "bin"
    bin_dir.mkdir(exist_ok=True)
    print("Скачиваю", URL)
    data = urllib.request.urlopen(URL).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = name.rsplit("/", 1)[-1]
            if "/bin/" in name and base and base != "ffplay.exe":
                with z.open(name) as src, open(bin_dir / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif base == "LICENSE.txt":
                (ROOT / "licenses").mkdir(exist_ok=True)
                (ROOT / "licenses" / "FFmpeg-LGPL.txt").write_bytes(z.read(name))
    out = subprocess.run([str(bin_dir / "ffmpeg.exe"), "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    if "libvpx-vp9" not in out:
        print("В сборке нет libvpx-vp9!")
        return 1
    print("Готово: bin/ffmpeg.exe, bin/ffprobe.exe (libvpx-vp9 есть)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
