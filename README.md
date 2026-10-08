# StickerMaker

Программа для Windows 10/11: перетащите видео в окно, нажмите «Конвертировать» и получите `.webm`, который принимает бот @Stickers. Программа сама уменьшает кадр до 512 px, обрезает или ускоряет видео до 3 с, убирает звук, сохраняет прозрачность и подбирает качество так, чтобы файл весил не больше 256 КБ.

Готовая программа — один файл `StickerMaker.exe`. Ставить Python и ffmpeg не нужно.

## Запуск из исходников

Нужен Python 3.11 или новее.

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python tools\get_ffmpeg.py
.venv\Scripts\python main.py
```

`tools\get_ffmpeg.py` скачивает в `bin\` сборку ffmpeg от BtbN (LGPL, shared, с libvpx-vp9). Сам ffmpeg в git не хранится.

Ядро работает и без окна:

```bat
python -m core видео.mp4 [ещё файлы] [-o папка] [--mode first|start|speed] [--start 4.5]
python -m core --info видео.mp4
```

## Сборка exe

Одна команда (после шагов из раздела выше):

```bat
.venv\Scripts\pyinstaller --noconfirm StickerMaker.spec
```

Результат появится в `dist\StickerMaker.exe` (около 90 МБ). Иконку можно перерисовать командой `.venv\Scripts\python tools\make_icon.py`.

## Проверки

```bat
python tests\make_samples.py              :: тестовые видео (нужен ffmpeg с libx264 в PATH)
python tests\acceptance.py                :: критерии приёмки для ядра
.venv\Scripts\python tests\ui_smoke.py    :: окно без показа на экране
```

## Структура

- `main.py` — запуск окна.
- `ui/` — окно (PySide6).
- `core/` — анализ (ffprobe), кодирование VP9, подгонка под 256 КБ, проверка результата. Ядро не зависит от интерфейса.
- `core/limits.py` — требования Telegram и параметры подгонки.
- `bin/` — ffmpeg.exe, ffprobe.exe и их библиотеки.
- `licenses/` — лицензия FFmpeg (LGPL).
