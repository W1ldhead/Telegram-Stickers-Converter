"""Проверка окна без показа на экране: добавление, режимы, конвертация, отмена, закрытие.

Запуск: .venv\\Scripts\\python tests\\ui_smoke.py (после make_samples.py)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.encode import MODE_SPEED, MODE_START  # noqa: E402
from ui.file_row import DONE, ERROR, PROBING, QUEUED, UNREADABLE  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
OUT = ROOT / "tests" / "out_ui"
fails = 0


def check(ok: bool, text: str) -> None:
    global fails
    fails += not ok
    print(("OK   " if ok else "FAIL ") + text)


def wait(app: QApplication, cond, timeout: float = 300) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def ffmpeg_count() -> int:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"], capture_output=True, text=True).stdout
    return out.lower().count("ffmpeg.exe")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    QSettings("StickerMaker", "StickerMaker").setValue("out_dir", "")
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()

    files = ["hd_10s_audio.mp4", "broken.mp4", "small_300x200.mp4", "phone_rotated.mp4", "anim_transparent.gif"]
    w.add_files([SAMPLES / f for f in files] + [SAMPLES / "readme.txt"])
    w.add_files([SAMPLES / "fps60.mp4", SAMPLES / "fps60.mp4"])
    check(len(w.rows) == 6, f"добавлено 6 строк (дубль и не-видео пропущены): {len(w.rows)}")
    wait(app, lambda: all(r.state != PROBING for r in w.rows), 60)
    rows = {r.path.name: r for r in w.rows}
    check(rows["broken.mp4"].state == UNREADABLE, f"битый: {rows['broken.mp4'].status.text()}")
    hd = rows["hd_10s_audio.mp4"]
    check(hd.long_box.isVisible() and not rows["small_300x200.mp4"].long_box.isVisible(),
          "выбор режима только у длинного видео")
    check("1920×1080 → 512×288" in hd.details.text(), f"строка: {hd.details.text()}")
    check("1080×1920 → 288×512" in rows["phone_rotated.mp4"].details.text(), "поворот в строке")

    # «Начать с» дальше конца — подсветка и пропуск
    hd.mode.setCurrentIndex(hd.mode.findData(MODE_START))
    hd.start.setValue(10.0)
    check(hd.start_invalid() and "e53935" in hd.start.styleSheet(), "начало = конец → поле подсвечено")
    rows["fps60.mp4"].remove_btn.click()
    check(len(w.rows) == 5, "удаление из списка")

    w.out_edit.setText(str(OUT))
    w._start()
    check(w.thread is not None, "конвертация запущена")
    check(not w.drop.isEnabled() and not hd.remove_btn.isEnabled(), "во время работы список заблокирован")
    wait(app, lambda: w.thread is None)
    states = {n: (r.state, r.status.text()) for n, r in rows.items() if r in w.rows}
    print("    ", states)
    check(hd.state == QUEUED, "файл с неверным началом не конвертировался")
    check(sum(r.state == DONE for r in w.rows) == 3, "3 готовых")
    check(w.open_btn.isVisible() and w.last_folder == OUT, "кнопка «Открыть папку»")
    check(w.progress.value() == 1000, f"прогресс 100%: {w.progress.format()}")

    # Ускорение длинного файла
    hd.mode.setCurrentIndex(hd.mode.findData(MODE_SPEED))
    w._start()
    wait(app, lambda: w.thread is None)
    check(hd.state == DONE, f"ускорение: {hd.status.text()}")

    # Отмена: процесс остановлен, недописанного файла нет
    before = set(OUT.iterdir())
    hd.mode.setCurrentIndex(hd.mode.findData(MODE_START))
    hd.start.setValue(1.0)
    w._start()
    wait(app, lambda: ffmpeg_count() > 0, 30)
    w._cancel()
    wait(app, lambda: w.thread is None, 30)
    time.sleep(0.3)
    check(hd.state == QUEUED and set(OUT.iterdir()) == before and ffmpeg_count() == 0,
          f"отмена: статус «{hd.status.text()}», новых файлов {len(set(OUT.iterdir()) - before)}, ffmpeg {ffmpeg_count()}")

    # Закрытие окна во время конвертации
    w._start()
    wait(app, lambda: ffmpeg_count() > 0, 30)
    w.close()
    time.sleep(0.3)
    check(ffmpeg_count() == 0 and set(OUT.iterdir()) == before, "закрытие окна = отмена, ffmpeg не остался")

    # Тест не должен оставлять свою папку в настройках пользователя
    QSettings("StickerMaker", "StickerMaker").setValue("out_dir", "")
    print(f"\nОшибок: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
