"""Автопроверка критериев приёмки ядра (кроме загрузки в @Stickers и exe).

Запуск: python tests/make_samples.py, затем python tests/acceptance.py
"""

from __future__ import annotations

import shutil
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import limits  # noqa: E402
from core.convert import ConvertError, convert_file  # noqa: E402
from core.encode import MODE_SPEED, MODE_START, Plan  # noqa: E402
from core.probe import probe  # noqa: E402
from core.verify import check_sticker  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
OUT = ROOT / "tests" / "out_acceptance"
results: list[tuple[bool, str]] = []


def check(ok: bool, text: str) -> None:
    results.append((ok, text))
    print(("OK   " if ok else "FAIL ") + text)


def sticker(name: str, plan: Plan | None = None, src: Path | None = None):
    src = src or SAMPLES / name
    r = convert_file(src, OUT, plan)
    return r, probe(r.path)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    r, i = sticker("hd_10s_audio.mp4")
    check((i.width, i.height) == (512, 288) and i.duration <= 3 and not i.has_audio
          and i.codec == "vp9" and r.size <= limits.MAX_BYTES,
          f"mp4 1920×1080 10 с со звуком → {i.width}×{i.height}, {i.duration:.2f} с, "
          f"звук={i.has_audio}, {i.codec}, {r.size} Б")

    r, i = sticker("phone_rotated.mp4")
    check((i.width, i.height) == (288, 512), f"телефон с поворотом → {i.width}×{i.height}")

    r, i = sticker("small_300x200.mp4")
    check((i.width, i.height) == (512, 341), f"300×200 → {i.width}×{i.height}")

    r, i = sticker("fps60.mp4")
    check(i.fps == 30, f"60 fps → {float(i.fps):g} fps")

    for name in ("prores4444_alpha.mov", "vp9_alpha.webm", "anim_transparent.gif"):
        r, i = sticker(name)
        check(i.has_alpha, f"{name}: прозрачность сохранена ({i.pix_fmt}, alpha={i.has_alpha})")
    r, i = sticker("anim.gif")
    check(not i.has_alpha, "непрозрачный GIF → без альфы")

    # Три режима длинного видео
    src = SAMPLES / "hd_10s_audio.mp4"
    r, i = sticker("", Plan(), src)
    check(i.duration <= 3, f"первые 3 с → {i.duration:.2f} с")
    r, i = sticker("", Plan(MODE_START, 6.0), src)
    check(i.duration <= 3, f"с 6-й секунды → {i.duration:.2f} с")
    r, i = sticker("", Plan(MODE_START, 8.5), src)
    check(1.3 <= i.duration <= 1.6, f"с 8,5 с (до конца 1,5 с) → {i.duration:.2f} с")
    r, i = sticker("", Plan(MODE_SPEED), src)
    check(2.8 <= i.duration <= 3, f"ускорить 10 с → {i.duration:.2f} с, {float(i.fps):g} fps")
    try:
        convert_file(src, OUT, Plan(MODE_START, 12.0))
        check(False, "начало дальше конца должно давать ошибку")
    except ConvertError as e:
        check(True, f"начало дальше конца → «{e}»")

    r, i = sticker("dynamic_noise.mp4")
    check(r.crf > limits.CRF_FIRST and r.size <= limits.TARGET_BYTES,
          f"динамичное видео → CRF {r.crf}, {r.size} Б")

    # Пачка из 5 файлов с одним битым
    batch = ["fps60.mp4", "broken.mp4", "small_300x200.mp4", "phone_rotated.mp4", "anim.gif"]
    ok, errors = 0, []
    for n in batch:
        try:
            convert_file(SAMPLES / n, OUT)
            ok += 1
        except ConvertError as e:
            errors.append(f"{n}: {e}")
    check(ok == 4 and len(errors) == 1, f"пачка 5 файлов → готово {ok}, ошибки: {errors}")

    r, i = sticker("", src=SAMPLES / "тест папка (1)" / "видео пример (копия).mp4")
    check(r.path.exists(), f"кириллица и скобки → {r.path.name}")

    # Имена: повтор даёт _2, _3, старые файлы не трогаются
    names = sorted(p.name for p in OUT.glob("fps60_sticker*.webm"))
    check(names == ["fps60_sticker.webm", "fps60_sticker_2.webm"], f"имена без перезаписи → {names}")

    bad = {p.name: check_sticker(p) for p in OUT.glob("*.webm")}
    bad = {k: v for k, v in bad.items() if v}
    check(not bad, f"все {len(list(OUT.glob('*.webm')))} файлов проходят проверку Telegram {bad or ''}")

    failed = sum(1 for ok, _ in results if not ok)
    print(f"\nИтого: {len(results) - failed} OK, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
