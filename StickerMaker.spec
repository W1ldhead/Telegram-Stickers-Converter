# Сборка: .venv\Scripts\pyinstaller StickerMaker.spec  →  dist\StickerMaker.exe
# -*- mode: python -*-

from pathlib import Path

root = Path(SPECPATH)
# ffmpeg, ffprobe и их библиотеки — в папку bin внутри exe
ffmpeg_files = [(str(p), "bin") for p in (root / "bin").iterdir()
                if p.suffix.lower() in (".exe", ".dll") and p.name.lower() != "ffplay.exe"]

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    datas=ffmpeg_files + [("assets/icon.png", "assets"), ("licenses", "licenses")],
    excludes=["tkinter", "unittest", "pydoc", "PIL"],
    noarchive=False,
)

# Лишнее: копии библиотек ffmpeg вне bin (PyInstaller тянет их как зависимости),
# программная отрисовка OpenGL, QML/Quick, PDF, сеть и шифрование — окну не нужны
_ffmpeg_dlls = {p.name.lower() for p in (root / "bin").glob("*.dll")}
_skip = ("opengl32sw", "qt6quick", "qt6qml", "qt6pdf", "qt6network", "qt6opengl",
         "qt6virtualkeyboard", "qt6svg", "libcrypto", "libssl", "qtnetwork", "qtopengl")


def _keep(entry):
    name = entry[0].replace("\\", "/").lower()
    base = name.rsplit("/", 1)[-1]
    if "/" not in name and base in _ffmpeg_dlls:
        return False
    if any(s in base for s in _skip):
        return False
    # Плагины Qt: оставляем только платформу windows и стили
    if "/plugins/" in name and not any(k in name for k in ("/platforms/qwindows", "/styles/")):
        return False
    if "/translations/" in name:
        return False
    return True


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if d[0].replace("\\", "/").lower().startswith(("bin/", "assets/", "licenses/")) or _keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StickerMaker",
    icon="assets/icon.ico",
    console=False,          # --windowed
    upx=False,
    runtime_tmpdir=None,
)
